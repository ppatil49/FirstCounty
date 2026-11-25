# Run Instructions

How to install, configure, run and test the Marketing Compliance Pre-Review app.
For how to use it, see the [User Manual](user_manual.md).

## 1. Requirements

| Need | Version / notes |
| --- | --- |
| Python | 3.11 or newer (tested on 3.15; the Docker image uses 3.12) |
| Git | Any recent version |
| Disk | About 500 MB for packages (+ ~300 MB for the browser if you run browser tests) |
| AI access (optional) | None for replay mode; otherwise a Gemini key, Ollama, OpenAI or Azure OpenAI |

## 2. Install (about 2 minutes)

**Windows (PowerShell or Command Prompt)**
```bat
git clone https://github.com/ppatil49/FirstCounty.git
cd FirstCounty
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```bash
git clone https://github.com/ppatil49/FirstCounty.git
cd FirstCounty
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Activate the virtual environment (`.venv\Scripts\activate` or `source .venv/bin/activate`) in every new terminal
before running the commands below.

## 3. Choose the AI provider

Edit `.env` (it is git-ignored, so keys stay on your machine). Set **one** option:

| Option | `.env` settings | Notes |
| --- | --- | --- |
| **Replay** (default, no key) | `LLM_PROVIDER=replay` | Uses saved AI reviews for the 12 sample ads. New or edited text cannot be reviewed. |
| **Google Gemini** (free key) | `LLM_PROVIDER=gemini`<br>`GEMINI_API_KEY=<your key>` | Get a key at https://aistudio.google.com → **Get API key**. Default model `gemini-3.6-flash`; ~5 s per review. |
| **Ollama** (local, free, offline) | `LLM_PROVIDER=ollama` | Install from https://ollama.com, then `ollama pull qwen2.5:7b` (~4.7 GB). Slower on a laptop without a GPU. |
| **OpenAI** | `LLM_PROVIDER=openai`<br>`OPENAI_API_KEY=<key>` | Default model `gpt-4.1`. |
| **Azure OpenAI** | `LLM_PROVIDER=azure_openai`<br>`AZURE_OPENAI_API_KEY=<key>`<br>`AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com`<br>`AZURE_OPENAI_DEPLOYMENT=<deployment>` | Production target. |

Other settings:

| Setting | Default | Purpose |
| --- | --- | --- |
| `LLM_MODEL` | provider default | Override the model name |
| `LOW_CONFIDENCE_THRESHOLD` | `0.6` | Findings below this are flagged "needs human judgment" |
| `DATABASE_URL` | `sqlite:///var/fcb.db` | Any SQLAlchemy URL (e.g. Azure SQL, PostgreSQL) |
| `RECORD_REPLAY` | `true` | Save live AI responses so they can be replayed without a key |

Never paste keys into code, chat or commits.

## 4. Run the app

```bash
streamlit run app/streamlit_app.py
```

It opens http://localhost:8501. Stop it with **Ctrl+C** in the terminal.

- Data is stored in `var/fcb.db`. To start fresh, stop the app and delete that file.
- Use a different port with `--server.port 8502`.
- The sidebar shows which AI provider and model are active.

### Run with Docker (optional)

```bash
docker build -t fcb-prereview .
docker run -p 8501:8501 --env-file .env fcb-prereview
```

Then open http://localhost:8501. (Docker Desktop must be running.)

## 5. Run the tests

| Command | What it does | Time | Needs a key? |
| --- | --- | --- | --- |
| `pytest` | 86 unit, workflow, audit, end-to-end and evaluation tests | ~10 s | No |
| `pytest -m ui` | 11 Playwright browser tests of the full workflow | ~3 min | No |

Browser tests need a one-time setup:
```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
pytest -m ui
pytest -m ui --headed --slowmo 300   # watch the browser click through
```

Both suites also run automatically on GitHub (Actions tab) on every push.

## 6. Run the evaluation

```bash
python eval/run_eval.py --replay              # score the saved reviews; no key needed
python eval/run_eval.py                       # live review of all 12 ads with your provider
python eval/run_eval.py --runs 3 --delay 6    # stability check: 3 runs, 6 s between calls
python eval/run_eval.py --out ollama          # keep this provider's results in eval/results/ollama/
```

Results are written to `eval/results/`:

| File | Contents |
| --- | --- |
| `eval_report.md` | Precision and recall on AD-01 to AD-04, per-ad table, findings for all 12 ads, stability |
| `findings_all_12.json` | Raw findings for every ad |
| `findings_all_runs.json` | Every run, when `--runs` is more than 1 |
| `baseline_scores.json` | Scores the regression tests compare against |
| `replay_cache/` | Saved AI responses used by replay mode |

If any ad fails (for example because of a rate limit), results are saved with a `.partial` suffix and the existing
results are **not** overwritten. The command exits with code 1.

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `GEMINI_API_KEY is not set` | Key missing or line still commented | In `.env`, remove the `#` and paste the key, no quotes or spaces |
| `Error code: 429` | Free-tier rate or daily limit reached | Wait (daily limits reset at midnight Pacific), use `--delay 6`, or switch provider |
| `Error code: 503` | Model temporarily overloaded | Retry later or set `LLM_MODEL` to another model |
| "Replay mode has no saved review for this exact text" | Replay only covers the 12 sample ads, unedited | Use a sample ad, or set a live provider in `.env` |
| `Connection refused` with Ollama | Ollama not running or model not downloaded | Start Ollama; run `ollama pull qwen2.5:7b`; check `ollama list` |
| Ollama download stuck | Network, VPN or firewall | Run `ollama pull qwen2.5:7b` in a normal terminal; try another network |
| `Port 8501 is already in use` | Another app instance is running | Close it, or use `--server.port 8502` |
| `ModuleNotFoundError` | Virtual environment not active | Activate `.venv`, then `pip install -r requirements.txt` |
| Sidebar shows **Audit chain: ❌ broken** | The audit table was altered outside the app | Investigate; restore the database from backup |
| Want a clean slate | — | Stop the app and delete `var/fcb.db` |
