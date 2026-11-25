# Design Note — Marketing Compliance Pre-Review Agent

## 1. Architecture and why

```
Streamlit UI (role switcher)
   │
WorkflowService ── state machine, role checks, gate ── AuditLog (append-only, hash-chained)
   │                                                        │
Reviewer ── prompt (reference + taxonomy) ── LLM client ── SQLite (SQLAlchemy)
   │            versioned                    gemini | ollama | openai | azure_openai | replay
Validator ── codes, citations, quotes, de-duplication, confidence flags
```

- **One grounded LLM call per piece, no RAG.** The curated reference (~3.4k tokens) and all 15 issue codes fit
  in the prompt, so the model sees every relevant rule every time. Retrieval would add a failure mode (missing
  the right chunk) without benefit at this size. Full eCFR text would justify retrieval later.
- **The model proposes, code disposes.** The prompt makes the model classify the piece (product, consumer vs
  business, channel, prescreened), decide which rule areas *apply*, then check each one. Deterministic code then:
  drops codes outside the taxonomy, takes the citation from the taxonomy (never the model), verifies that
  `offending_text` actually appears in the ad (otherwise nulls it and lowers confidence), merges duplicate codes,
  and flags confidence < 0.6 as *needs human judgment*.
- **Precision by applicability, not by suppression.** Most false alarms in this domain are rules applied to the
  wrong product or channel (CAN-SPAM on a postcard, "Member FDIC" on a loan ad, EHL on an auto loan). The prompt
  states these applicability rules generally; nothing refers to specific ads (a test enforces this).
- **Provider-agnostic by configuration.** Every provider is reached through the OpenAI-compatible API, so moving
  from the local Gemini free tier to Azure OpenAI is an `.env` change. A **replay** provider serves recorded
  responses, so reviewers, tests and CI run with no key.
- **LLM choice:** development used **Gemini 3.6 Flash** (free tier, ~4–6 s per review, JSON mode, OpenAI-compatible
  endpoint). Newer Gemini models returned 503 (overloaded) during development. Production target: **Azure OpenAI**
  for enterprise data terms, private networking and regional residency.

## 2. Workflow state model and audit trail

`SUBMITTED → AI_REVIEWED → PENDING_COMPLIANCE → APPROVED | RETURNED | REJECTED`; resubmission from
`AI_REVIEWED` or `RETURNED` creates a new version and returns to `SUBMITTED`, triggering a new AI review.
If the AI call fails, the piece stays in `SUBMITTED` with the error recorded and a retry action.

- **Gate:** a high finding passes only if *disputed with a reason*. *Accepted* means "I'll fix it", so it blocks
  until a resubmission no longer triggers it. Medium/low findings never block.
- **Comments:** dispute requires a reason; Return and Reject require a comment (Reject is our addition).
- **Roles** are enforced in the service layer, not the UI: Marketing cannot decide or rate findings;
  Compliance cannot edit, submit or respond.
- **Versions** are immutable rows; diffs are computed with `difflib`. Marketing responses and Compliance feedback
  are append-only rows (latest wins), so changes of mind are preserved.
- **Audit trail:** every action writes an event (who, role, action, submission, version, from→to status,
  details, model, prompt version) in the same transaction as the change. It is append-only at two levels
  (ORM guard + SQLite triggers) and **SHA-256 hash-chained**, so any edit made around those guards is detected
  (`verify_chain`, shown in the UI sidebar). The end-to-end test reconstructs a full approval story from the log alone.

## 3. Evaluation

Results on AD-01 to AD-04: **precision 100% (6/6), recall 100% (6/6)**; AD-04 returns clean. Raw findings for all
12 ads are in `eval/results/findings_all_12.json`; see `eval/results/eval_report.md` for the per-ad table.
The recorded responses are replayed by the test suite, so any code change that lowers these scores fails CI.

**Stability check incomplete:** a 3-run repeat was started, but the Gemini free tier began returning HTTP 429
(rate/daily quota) partway through, so failed calls could not be separated from genuine answer changes. The runner
now records every run and reports errors separately (`--runs 3 --delay 6`); it should be re-run when quota resets.
Spot checks (AD-01 and AD-04 reviewed twice) returned identical codes.

Honest caveats: 4 labelled ads (6 planted issues) is a tiny sample, so 100% does not establish real-world accuracy.
The prompt was written from the regulation reference before tuning, and the first run already matched the key;
no ad-specific changes were made. The hidden set (AD-05..12) is the better test.

## 4. Known failure modes and how to detect them in production

| Failure mode | Detection |
| --- | --- |
| Rule applied where it doesn't apply (false alarm) | Compliance "incorrect" rate per issue code; dispute rate |
| Missed issue (false negative) | Compliance adds issues the AI missed (add a field); periodic sampled re-review |
| Invented quotes or citations | Validator already nulls unverifiable quotes; log the rate of `validation_notes` |
| Non-determinism between runs | Temperature 0 + stability runs; monitor same-text reviews disagreeing |
| Model/provider outage or rate limits | Retries with backoff; piece stays SUBMITTED; alert on `ai_review_failed` events |
| Silent model change by the provider | Pin model versions; re-run the eval suite on any change; replay regression test |
| Reference out of date | Taxonomy/reference version recorded per review; owner + change process (below) |

## 5. Cost and latency per review

- **Tokens:** ~3.6k input (system prompt ~3.4k + ad) and ~350 output on average.
- **Latency:** ~4–6 s per review observed with Gemini 3.6 Flash.
- **Cost:** $0 on the Gemini free tier used for development. On a paid Azure OpenAI model, cost per review is
  3.6k × input price + 0.35k × output price; for current small/fast models that is a fraction of a cent, and for
  frontier models low single-digit cents. Because the ~3.4k-token system prompt is identical across reviews,
  prompt caching would cut input cost further.

## 6. Staying current when a regulation changes

The rules live in data, not code: `reference.md` and `issue_taxonomy.json`. A change means: update the reference
(or pull new eCFR text), bump the taxonomy and `PROMPT_VERSION`, re-run the evaluation suite (plus new test ads for
the changed rule), and release only if scores hold. Each review stores the prompt and taxonomy version it used, so
pieces reviewed under old rules can be found and re-reviewed. In production, an owner in Compliance signs off on
reference changes, and eCFR change notices can trigger that process.

## 7. How Compliance feedback improves the system

Every finding can be marked correct/incorrect with a note, and Marketing disputes carry reasons. That gives labelled
data per issue code. Over time:
1. **Measure:** precision per code from "incorrect" marks; recall gaps from issues Compliance adds.
2. **Grow the eval set:** confirmed findings and confirmed false alarms become new regression cases.
3. **Improve the prompt:** add clarified applicability rules or worked examples for codes with high error rates,
   validated against the growing eval set before release (no silent changes).
4. **Calibrate:** tune the low-confidence threshold so "needs human judgment" catches most of the errors.
Fine-tuning is only worth considering once there are hundreds of labelled reviews.
