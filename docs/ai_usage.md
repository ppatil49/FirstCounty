# How AI tools were used

**LLM in the product:** Google Gemini 3.6 Flash via its OpenAI-compatible API (free tier) during development;
Azure OpenAI is the intended production provider. The code supports both, plus Ollama (local) and a replay mode.

**AI coding assistant:** Claude Code (Anthropic) was used throughout:
- **Understanding and scoping:** summarizing the brief, drafting a product brief, acceptance criteria and an
  implementation plan, which I reviewed and edited (scope, assumptions such as requiring comments on Reject).
- **Implementation:** generating the engine, workflow service, audit trail, Streamlit UI, evaluation runner and
  test harness, with me directing design decisions and reviewing the code.
- **Verification:** running the test suite, the evaluation and a scripted UI walkthrough, and fixing the bugs
  those found (for example, a mislabelled audit action caught by the end-to-end test).

All design decisions, the regulation-applicability approach and the final review of outputs were mine.
