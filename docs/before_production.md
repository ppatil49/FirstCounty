# Before Production

What I would change before real Compliance staff at a bank used this. Grouped by risk area, most important first within each.

## Security and access
1. **Real identity:** replace the role switcher with Microsoft Entra ID (SSO + MFA). Map Entra groups to the Marketing and Compliance roles; enforce roles on the server, never in the UI.
2. **Separation of duties:** block a person from approving a piece they submitted or edited, even if they hold both roles.
3. **Secrets:** move API keys and DB credentials to Azure Key Vault, read through managed identity. No keys in files or environment dumps.
4. **Network:** private endpoints for Azure OpenAI, the database and Key Vault; the app behind Azure Front Door with WAF; no public database.
5. **App hardening:** input size limits, file-type checks for uploads, rate limiting, dependency scanning and pinned images.

## Data handling
1. **Model data terms:** use Azure OpenAI (or another enterprise endpoint) with no training on our data and an approved data-processing agreement. The prototype's free Gemini tier is for synthetic data only.
2. **Data residency and retention:** keep data in US Azure regions; define retention for drafts, versions and the audit log in line with bank record-keeping policy.
3. **Sensitive content:** marketing drafts can contain unreleased rates and offers; treat as confidential. Scan for customer PII before sending to the model and block or redact it.
4. **Encryption:** encryption at rest (customer-managed keys if required) and TLS everywhere.

## Model risk management (SR 11-7 / OCC 2011-12 style)
1. **Model inventory and validation:** register the engine as a model; independent validation on a larger, Compliance-labelled test set before go-live (12 synthetic ads is far too few).
2. **Pinned versions:** pin the model version and prompt version; any change goes through a re-evaluation gate with documented precision/recall before release. Every review already records model and prompt version.
3. **Ongoing monitoring:** track Compliance's correct/incorrect feedback per issue code, dispute rates, "clean" rates and drift; alert when precision or recall drops.
4. **Human in the loop stays mandatory:** the AI never approves. Low-confidence findings are already flagged; consider routing them to a senior reviewer.
5. **Fallback:** if the model is unavailable, pieces queue for manual review rather than blocking Marketing (the prototype already keeps them in SUBMITTED with a retry).
6. **Regulation currency:** owner and process for updating the reference when rules change, with a re-evaluation run each time.

## Audit and records
1. **Immutable storage:** keep the hash-chained log, and also write it to Azure immutable (WORM) Blob storage or a ledger table so even DB admins cannot alter history.
2. **Store full AI inputs and outputs** for each review (the prototype keeps findings plus a replay cache) so an examiner can see exactly what the model saw and said.
3. **Exportable examiner report** per piece: versions, diffs, findings, responses, decisions and the audit trail as a PDF.

## Deployment on Azure
1. **Compute:** container image on Azure Container Apps (or App Service), at least two replicas, health probes (the Dockerfile already has one).
2. **Data:** Azure SQL Database or Azure Database for PostgreSQL (SQLAlchemy URL change only); automated backups and point-in-time restore.
3. **AI:** Azure OpenAI deployment with provisioned or reserved capacity sized to review volume; retries with backoff (already in place).
4. **Observability:** Application Insights for logs, traces, latency and token usage; dashboards for review volume and AI quality.
5. **CI/CD:** GitHub Actions or Azure DevOps: tests (already in CI) → evaluation gate → staging → production, with infrastructure as code (Bicep or Terraform).
6. **Environments:** separate dev, test and prod subscriptions; prod data never used in dev.

## Product gaps to close
- PDF and image input (OCR) for flyers, mailers and social images.
- Approval expiry: re-review approved pieces when rates, dates or regulations change.
- Notifications (Teams or email) on status changes.
- A second-level approver for high-risk products (investments, mortgages).
- State-level advertising rules where applicable.
