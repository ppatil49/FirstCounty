"""Playwright fixtures: each test gets its own Streamlit server with an empty
database, in replay mode (no API key; the 12 sample ads have saved AI reviews)."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright")

from playwright.sync_api import Page, expect  # noqa: E402

from config import ADS_DIR, ROOT  # noqa: E402
from engine.reviewer import split_front_matter  # noqa: E402

APP = ROOT / "app" / "streamlit_app.py"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def app_url(tmp_path: Path):
    port = _free_port()
    env = {
        **os.environ,
        "LLM_PROVIDER": "replay",
        "RECORD_REPLAY": "false",
        "DATABASE_URL": f"sqlite:///{(tmp_path / 'ui.db').as_posix()}",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(APP), "--server.headless=true",
         f"--server.port={port}", "--browser.gatherUsageStats=false"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://localhost:{port}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{url}/_stcore/health", timeout=1)
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.fail("Streamlit server did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def sample_body(ad_id: str) -> str:
    return split_front_matter((ADS_DIR / f"{ad_id}.md").read_text(encoding="utf-8"))[1].strip()


class App:
    """Small page object over the Streamlit UI."""

    def __init__(self, page: Page, url: str):
        self.page = page
        page.set_default_timeout(20_000)
        page.goto(url)
        expect(page.get_by_role("heading", name="Marketing Compliance Pre-Review")).to_be_visible()
        self.idle()

    # -- plumbing -----------------------------------------------------------
    def idle(self, quiet_ms: int = 700, timeout_ms: int = 30_000) -> None:
        """Wait until Streamlit has finished re-running. A click can trigger two runs back to
        back (the action, then st.rerun()), so require the page to stay quiet for a while."""
        busy = self.page.locator('[data-testid="stStatusWidget"], [data-stale="true"]')
        quiet_since = None
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if busy.count():
                quiet_since = None
            elif quiet_since is None:
                quiet_since = time.monotonic()
            elif (time.monotonic() - quiet_since) * 1000 >= quiet_ms:
                return
            self.page.wait_for_timeout(100)
        raise AssertionError("Streamlit app did not become idle")

    def click(self, name: str, nth: int = 0) -> None:
        self.page.get_by_role("button", name=name).nth(nth).click()
        self.idle()

    def select(self, label: str, option: str) -> None:
        self.page.get_by_test_id("stSelectbox").filter(has_text=label).click()
        self.page.get_by_role("option", name=option, exact=True).click()
        self.idle()

    def fill_input(self, label: str, text: str, nth: int = 0) -> None:
        box = self.page.get_by_label(label).nth(nth)
        box.fill(text)
        box.press("Enter")
        self.idle()

    def fill_area(self, label: str, text: str) -> None:
        box = self.page.get_by_label(label)
        box.fill(text)
        box.press("Control+Enter")
        self.idle()

    # -- app actions ----------------------------------------------------------
    def sign_in(self, who: str) -> None:
        self.page.get_by_test_id("stSidebar").get_by_text(who).click()
        self.idle()

    def submit_sample(self, ad_id: str, title: str | None = None) -> None:
        if not self.page.get_by_text("Load a sample ad (optional)").is_visible():
            self.page.get_by_text("Step 1 · Submit a new piece").click()
        self.select("Load a sample ad (optional)", ad_id)
        if title:
            # Inside st.form: no Enter (it would submit); values are sent with the submit button.
            self.page.get_by_label("Title").fill(title)
        self.click("Submit for AI pre-review")

    def status_heading(self):
        return self.page.get_by_role("heading", level=3).first

    def finding_cards(self):
        return self.page.get_by_text("confidence 0.", exact=False)

    def dispute_all(self, reason: str = "Disclosure appears on the reverse side") -> None:
        n = self.page.get_by_role("button", name="Dispute", exact=True).count()
        for i in range(n):
            self.fill_input("Dispute reason", reason, nth=i)
            self.click("Dispute", nth=i)


@pytest.fixture
def app(page: Page, app_url: str) -> App:
    return App(page, app_url)
