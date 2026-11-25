"""Browser tests for the 3-step workflow. Run with:  pytest -m ui
(add --headed to watch, --slowmo 300 to slow it down)."""
import pytest
from playwright.sync_api import expect

from tests.ui.conftest import App, sample_body

pytestmark = pytest.mark.ui

MARIA = "Maria (Marketing)"
CHRIS = "Chris (Compliance)"


def send_ad01_to_compliance(app: App) -> None:
    app.submit_sample("AD-01")
    app.dispute_all()
    app.click("Send to Compliance ➜")
    expect(app.status_heading()).to_contain_text("PENDING_COMPLIANCE")


def test_app_loads_with_role_switcher_and_replay_notice(app: App):
    sidebar = app.page.get_by_test_id("stSidebar")
    expect(sidebar.get_by_text(MARIA)).to_be_visible()
    expect(sidebar.get_by_text(CHRIS)).to_be_visible()
    expect(sidebar.get_by_text("Replay mode")).to_be_visible()
    expect(sidebar.get_by_text("Audit chain: ✅ intact")).to_be_visible()


def test_submit_sample_shows_findings_and_blocks_sending(app: App):
    app.submit_sample("AD-01", title="CD postcard")
    expect(app.status_heading()).to_contain_text("AI_REVIEWED")
    for code in ["REGDD_RATE_NOT_APY", "REGDD_MISSING_APY_TERMS", "FDIC_MISSING_STATEMENT"]:
        expect(app.page.get_by_text(code).first).to_be_visible()
    expect(app.page.get_by_text("high finding has no response").first).to_be_visible()
    expect(app.page.get_by_role("button", name="Send to Compliance ➜")).to_be_disabled()


def test_clean_ad_has_no_findings_and_can_be_sent(app: App):
    app.submit_sample("AD-04")
    expect(app.page.get_by_text("No issues found by the AI pre-review.")).to_be_visible()
    app.click("Send to Compliance ➜")
    expect(app.status_heading()).to_contain_text("PENDING_COMPLIANCE")


def test_dispute_requires_a_reason(app: App):
    app.submit_sample("AD-03")
    app.click("Dispute", nth=0)
    expect(app.page.get_by_text("A reason for the dispute is required.")).to_be_visible()


def test_accepting_a_high_finding_still_blocks_until_resubmitted(app: App):
    app.submit_sample("AD-03")
    app.click("Accept", nth=0)
    expect(app.page.get_by_text("accepted but not yet fixed").first).to_be_visible()
    expect(app.page.get_by_role("button", name="Send to Compliance ➜")).to_be_disabled()


def test_disputing_all_high_findings_unlocks_sending(app: App):
    app.submit_sample("AD-01")
    app.dispute_all()
    expect(app.page.get_by_text("Marketing disputeed")).to_have_count(0)
    expect(app.page.get_by_text("Marketing disputed").first).to_be_visible()
    expect(app.page.get_by_role("button", name="Send to Compliance ➜")).to_be_enabled()


def test_role_separation_in_the_ui(app: App):
    send_ad01_to_compliance(app)
    # Marketing sees no decision buttons
    expect(app.page.get_by_role("button", name="✅ Approve")).to_have_count(0)
    app.sign_in(CHRIS)
    # Compliance cannot submit, respond or resubmit
    expect(app.page.get_by_text("Step 1 · Submit a new piece")).to_have_count(0)
    expect(app.page.get_by_role("button", name="Dispute", exact=True)).to_have_count(0)
    expect(app.page.get_by_role("button", name="Resubmit revised version")).to_have_count(0)
    expect(app.page.get_by_role("button", name="✅ Approve")).to_be_visible()


def test_compliance_feedback_on_findings_is_saved(app: App):
    send_ad01_to_compliance(app)
    app.sign_in(CHRIS)
    app.click("✔ AI correct", nth=0)
    expect(app.page.get_by_text("Compliance marked this finding").first).to_be_visible()


def test_return_and_reject_require_a_comment(app: App):
    send_ad01_to_compliance(app)
    app.sign_in(CHRIS)
    app.click("↩ Return with comments")
    expect(app.page.get_by_text("A comment for returned is required.")).to_be_visible()
    app.click("⛔ Reject with comments")
    expect(app.page.get_by_text("A comment for rejected is required.")).to_be_visible()
    expect(app.status_heading()).to_contain_text("PENDING_COMPLIANCE")


def test_reject_with_comment(app: App):
    send_ad01_to_compliance(app)
    app.sign_in(CHRIS)
    app.fill_area("Comment (required to return or reject)", "Rate offer withdrawn; do not run")
    app.click("⛔ Reject with comments")
    app.page.get_by_test_id("stSidebar").get_by_text("Show only my queue").click()
    app.idle()
    expect(app.status_heading()).to_contain_text("REJECTED")
    expect(app.page.get_by_text("Rate offer withdrawn; do not run")).to_be_visible()


def test_full_journey_return_resubmit_approve(app: App):
    send_ad01_to_compliance(app)

    # Compliance returns it with a comment
    app.sign_in(CHRIS)
    app.fill_area("Comment (required to return or reject)", "Put the APY disclosures on this side")
    app.click("↩ Return with comments")

    # Marketing sees it back, with the comment, and resubmits a fixed version
    app.sign_in(MARIA)
    expect(app.status_heading()).to_contain_text("RETURNED")
    expect(app.page.get_by_text("Put the APY disclosures on this side")).to_be_visible()
    app.fill_area("Edit the piece", sample_body("AD-04"))
    app.click("Resubmit revised version")
    expect(app.status_heading()).to_contain_text("AI_REVIEWED")
    expect(app.page.get_by_text("version 2", exact=False).first).to_be_visible()
    expect(app.page.get_by_text("No issues found by the AI pre-review.")).to_be_visible()

    # Versions & diff tab shows both versions and the change
    app.page.get_by_role("tab", name="Versions & diff").click()
    expect(app.page.get_by_text("Version 1 ·", exact=False).first).to_be_visible()
    expect(app.page.get_by_text("Version 2 ·", exact=False).first).to_be_visible()
    expect(app.page.get_by_text("+Grow your savings", exact=False)).to_be_visible()
    app.page.get_by_role("tab", name="Review").click()

    # Send again and approve
    app.click("Send to Compliance ➜")
    app.sign_in(CHRIS)
    app.click("✅ Approve")
    app.page.get_by_test_id("stSidebar").get_by_text("Show only my queue").click()
    app.idle()
    expect(app.status_heading()).to_contain_text("APPROVED")
    expect(app.page.get_by_text("APPROVED by chris on v2")).to_be_visible()

    # Audit trail tab renders and the hash chain is intact
    app.page.get_by_role("tab", name="Audit trail").click()
    expect(app.page.get_by_test_id("stDataFrame")).to_be_visible()
    expect(app.page.get_by_test_id("stSidebar").get_by_text("Audit chain: ✅ intact")).to_be_visible()
