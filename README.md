# FCB Marketing Compliance Pre-Review Agent

A working prototype of an AI-assisted **first-pass compliance review** for First County Bank marketing.
The AI flags likely federal advertising issues (Reg DD, Reg Z, FDIC, fair lending, UDAAP, FCRA, CAN-SPAM),
Marketing accepts or disputes each finding and revises, and **Compliance makes every final decision**,
with an append-only, tamper-evident audit trail.

All data is synthetic. Built for the FCB Senior AI Application Engineer take-home.

## Quick start (under 10 minutes)

Requires Python 3.11+ (tested on 3.15).

```bash
git clone https://github.com/ppatil49/FirstCounty.git
cd FirstCounty
python -m venv .venv
.venv\Scripts\activate            # Windows   (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # Windows   (macOS/Linux: cp .env.example .env)
```

Then pick one way to run it:

| Path | Needs | `.env` setting |
| --- | --- | --- |
| **A. Replay (no key)** | Nothing | `LLM_PROVIDER=replay` (default). Uses saved AI reviews for the 12 sample ads. |
| **B. Gemini (free key)** | Key from https://aistudio.google.com | `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` |
| **C. Ollama (free, offline)** | Ollama installed + `ollama pull qwen2.5:7b` | `LLM_PROVIDER=ollama` |
| **D. Azure OpenAI** | Azure resource + deployment | `LLM_PROVIDER=azure_openai` + the `AZURE_OPENAI_*` values |

```bash
pytest                                   # full test harness, no key needed (~5 s)
python eval/run_eval.py --replay         # score saved results, no key needed
python eval/run_eval.py                  # live run on all 12 ads with your provider
streamlit run app/streamlit_app.py       # the workflow app, opens http://localhost:8501
```

Or with Docker: `docker build -t fcb-prereview . && docker run -p 8501:8501 --env-file .env fcb-prereview`

## Demo script

1. Sidebar: sign in as **Maria (Marketing)**. Open **Submit a new piece**, load sample **AD-01**, submit.
2. The AI flags the issues. Dispute or accept each one. **Send to Compliance** stays disabled until every
   high-severity finding is disputed with a reason or fixed by a resubmission.
3. Edit the text, **Resubmit**: a new version is created and re-reviewed. See **Versions & diff**.
4. Switch to **Chris (Compliance)**: see the piece, findings and Marketing's responses side by side,
   mark findings correct/incorrect, then Approve, Return with comments, or Reject with comments.
5. Open **Audit trail** to reconstruct every step (who, what, when, version, model, prompt version).

## How it works

```
ad text + channel + product
        │
        ▼
 engine/prompts.py   versioned prompt: full regulation reference + 15 issue codes +
                     classify → decide which rules apply → check → report
        │
        ▼
 engine/llm.py       one OpenAI-compatible client: gemini | ollama | openai | azure_openai,
                     temperature 0, JSON output; every response saved for replay
        │
        ▼
 engine/validate.py  deterministic guardrails: unknown codes dropped, citation taken from the
                     taxonomy, quotes verified against the ad, one finding per code,
                     low confidence flagged for human judgment
        │
        ▼
 workflow/service.py state machine + role checks + gate, every action → audit event
 workflow/audit.py   append-only (ORM guard + SQLite triggers) and SHA-256 hash-chained
```

**Statuses:** `SUBMITTED → AI_REVIEWED → PENDING_COMPLIANCE → APPROVED | RETURNED | REJECTED`.
Resubmitting (from `AI_REVIEWED` or `RETURNED`) creates a new version and a new AI review.

**Gate rule:** a high-severity finding passes only when it is *disputed with a reason*. *Accepting* it means
"I'll fix it", so the marketer must resubmit; if the new version no longer triggers it, it is fixed.

## Project layout

```
config.py                settings from env/.env (same code locally and on Azure)
data/                    the take-home ads, regulations and answer key
engine/                  prompt, LLM switch, validation, reviewer
workflow/                models, state machine service, audit trail
app/streamlit_app.py     UI with mock role switcher
eval/run_eval.py         evaluation runner; results in eval/results/
tests/                   unit, workflow, audit, end-to-end and evaluation tests
docs/                    design note and before-production list
```

## Testing harness

| Command | What it checks | Key? |
| --- | --- | --- |
| `pytest` | Validation, prompt grounding, provider switch, state machine, gate, roles, required comments, versions, audit immutability and hash chain, full journey, scoring maths, replay regression | No |
| `python eval/run_eval.py` | Live precision/recall on AD-01..04 + raw findings for all 12 ads | Yes |
| `python eval/run_eval.py --runs 3` | Same, plus which findings change between runs | Yes |
| `python eval/run_eval.py --replay` | Re-scores saved responses through current code | No |

Results: [`eval/results/eval_report.md`](eval/results/eval_report.md) and
[`eval/results/findings_all_12.json`](eval/results/findings_all_12.json).
