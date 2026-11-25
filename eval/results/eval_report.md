# Evaluation Report

Generated 2026-11-24 16:10 UTC · provider `replay` · model `replay:gemini-3.6-flash` · prompt `v1`

Scored on AD-01 to AD-04 (the ads with a published answer key). A match is ad_id + issue_code.

| Metric | All findings | Excluding low-confidence (needs human review) |
| --- | --- | --- |
| Precision | 100% (6/6) | 100% (6/6) |
| Recall | 100% (6/6) | 100% (6/6) |
| F1 | 1.00 | 1.00 |

## Per ad

| Ad | Expected | Caught | Missed | False positives |
| --- | --- | --- | --- | --- |
| AD-01 | FDIC_MISSING_STATEMENT, REGDD_MISSING_APY_TERMS, REGDD_RATE_NOT_APY | FDIC_MISSING_STATEMENT, REGDD_MISSING_APY_TERMS, REGDD_RATE_NOT_APY | - | - |
| AD-02 | REGDD_FREE_MISUSE, UDAAP_MISLEADING | REGDD_FREE_MISUSE, UDAAP_MISLEADING | - | - |
| AD-03 | REGZ_TRIGGER_TERMS | REGZ_TRIGGER_TERMS | - | - |
| AD-04 | - | - | - | - |

## Findings on all 12 ads

| Ad | Findings (code, severity, confidence) |
| --- | --- |
| AD-01 | REGDD_RATE_NOT_APY (high, 0.95); REGDD_MISSING_APY_TERMS (high, 0.95); FDIC_MISSING_STATEMENT (high, 0.95) |
| AD-02 | REGDD_FREE_MISUSE (high, 0.95); UDAAP_MISLEADING (high, 0.95) |
| AD-03 | REGZ_TRIGGER_TERMS (high, 0.95) |
| AD-04 | clean |
| AD-05 | REGZ_RATE_WITHOUT_APR (high, 0.95); REGZ_TRIGGER_TERMS (high, 0.95); EHL_MISSING (high, 0.95); UDAAP_MISLEADING (high, 0.9); FAIR_LENDING_DISCOURAGEMENT (medium, 0.85) |
| AD-06 | REGZ_INTRO_RATE (high, 0.95); EHL_MISSING (high, 0.95) |
| AD-07 | FDIC_NONDEPOSIT_MISREP (high, 0.98); NONDEPOSIT_DISCLOSURES_MISSING (high, 0.98); UDAAP_MISLEADING (high, 0.9) |
| AD-08 | clean |
| AD-09 | REGDD_BONUS_TERMS (high, 0.95); CANSPAM_MISSING_ELEMENT (high, 0.95) |
| AD-10 | FCRA_PRESCREEN_NOTICE (high, 0.98); REGZ_INTRO_RATE (high, 0.95) |
| AD-11 | REGDD_MISSING_APY_TERMS (high, 0.95) |
| AD-12 | clean |
