"""Minimal workflow UI. Run with:  streamlit run app/streamlit_app.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from config import ADS_DIR, Settings  # noqa: E402
from engine.reviewer import Reviewer, split_front_matter  # noqa: E402
from workflow.models import make_session_factory  # noqa: E402
from workflow.service import (  # noqa: E402
    AI_REVIEWED, APPROVED, CHANNELS, COMPLIANCE, MARKETING, PENDING_COMPLIANCE, PRODUCT_TYPES,
    REJECTED, RETURNED, SUBMITTED, User, WorkflowError, WorkflowService,
)

st.set_page_config(page_title="FCB Compliance Pre-Review", layout="wide")

USERS = {"Maria (Marketing)": User("maria", MARKETING), "Chris (Compliance)": User("chris", COMPLIANCE)}
STATUS_BADGE = {SUBMITTED: "🟦", AI_REVIEWED: "🟨", PENDING_COMPLIANCE: "🟧", APPROVED: "🟩",
                RETURNED: "🟪", REJECTED: "🟥"}
SEVERITY_BADGE = {"high": "🔴 high", "medium": "🟠 medium", "low": "⚪ low"}


@st.cache_resource
def get_service() -> WorkflowService:
    settings = Settings.load()
    return WorkflowService(make_session_factory(settings.database_url), lambda: Reviewer.from_settings(settings))


def guess_metadata(meta: dict) -> tuple[str, str]:
    """Map a sample ad's free-text front matter onto the form's dropdowns."""
    ch, pr = meta.get("channel", "").lower(), meta.get("product", "").lower()
    channel = next((v for k, v in [("email", "email"), ("social", "social"), ("instagram", "social"),
                                   ("website", "web"), ("radio", "radio"), ("mail", "mailer"),
                                   ("letter", "mailer"), ("postcard", "mailer")] if k in ch), "print")
    product = next((v for k, v in [("credit card", "credit_card"), ("mortgage", "mortgage"),
                                   ("home equity", "mortgage"), ("annuity", "investment"),
                                   ("investment", "investment"), ("loan", "loan"), ("deposit", "deposit")]
                    if k in pr), "general")
    return channel, product


def run(action, success: str | None = None) -> bool:
    try:
        action()
    except WorkflowError as exc:
        st.error(str(exc))
        return False
    if success:
        st.toast(success)
    return True


svc = get_service()
settings = Settings.load()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("FCB Compliance Pre-Review")
    user = USERS[st.radio("Signed in as (mock login)", list(USERS))]
    st.caption(f"AI provider: **{settings.llm_provider}** · model: **{settings.llm_model or '-'}**")
    if settings.llm_provider == "replay":
        st.info("Replay mode: only the 12 sample ads have saved AI reviews. Set LLM_PROVIDER in .env for live reviews.")
    ok, broken = svc.verify_audit_chain()
    st.caption("Audit chain: ✅ intact" if ok else f"Audit chain: ❌ broken at event {broken}")

st.title("Marketing Compliance Pre-Review")
st.caption("AI does the first pass. Compliance makes every final decision.")

# ---------------------------------------------------------------- new submission (Marketing)
if user.role == MARKETING:
    with st.expander("➕ Step 1 · Submit a new piece", expanded=not svc.list_submissions()):
        samples = sorted(ADS_DIR.glob("AD-*.md"))
        pick = st.selectbox("Load a sample ad (optional)", ["—"] + [p.stem for p in samples])
        meta, body = ({}, "")
        if pick != "—":
            meta, body = split_front_matter((ADS_DIR / f"{pick}.md").read_text(encoding="utf-8"))
        g_channel, g_product = guess_metadata(meta) if meta else ("email", "deposit")
        with st.form("submit", clear_on_submit=False):
            title = st.text_input("Title", value=f"{pick} sample" if meta else "")
            c1, c2 = st.columns(2)
            channel = c1.selectbox("Channel", CHANNELS, index=CHANNELS.index(g_channel))
            product = c2.selectbox("Product type", PRODUCT_TYPES, index=PRODUCT_TYPES.index(g_product))
            content = st.text_area("Content (text or markdown)", value=body.strip(), height=220)
            if st.form_submit_button("Submit for AI pre-review", type="primary"):
                with st.spinner("AI is reviewing..."):
                    holder = {}
                    if run(lambda: holder.update(id=svc.submit(user, title, channel, product, content)),
                           "Submitted"):
                        st.session_state["selected"] = holder["id"]
                        st.rerun()

# ---------------------------------------------------------------- queue
subs = svc.list_submissions({PENDING_COMPLIANCE} if user.role == COMPLIANCE and
                            st.sidebar.checkbox("Show only my queue", True) else None)
if not subs:
    st.info("Nothing here yet." if user.role == MARKETING else "No pieces waiting for Compliance.")
    st.stop()

labels = {s.id: f"{STATUS_BADGE[s.status]} {s.id} · {s.title} · {s.status}" for s in subs}
ids = list(labels)
default = ids.index(st.session_state["selected"]) if st.session_state.get("selected") in ids else 0
sid = st.selectbox("Piece", ids, index=default, format_func=labels.get)
st.session_state["selected"] = sid
sub = svc.get(sid)
current = sub.versions[-1]

st.subheader(f"{sub.title}  ·  {STATUS_BADGE[sub.status]} {sub.status}")
st.caption(f"{sub.id} · channel **{sub.channel}** · product **{sub.product_type}** · "
           f"version **{current.number}** · AI: {current.ai_model or '—'} / prompt {current.prompt_version or '—'}")
for d in sub.decisions:
    msg = f"**{d.decision}** by {d.actor} on v{d.version_number}" + (f": {d.comment}" if d.comment else "")
    (st.success if d.decision == APPROVED else st.warning if d.decision == RETURNED else st.error)(msg)

tab_review, tab_versions, tab_audit = st.tabs(["Review", "Versions & diff", "Audit trail"])


def finding_card(f, editable_marketing: bool, editable_compliance: bool):
    with st.container(border=True):
        top = f"{SEVERITY_BADGE[f.severity]} · **{f.issue_code}** · `{f.regulation}` · confidence {f.confidence:.2f}"
        if f.needs_human_review:
            top += " · ⚠️ **low confidence — needs human judgment**"
        st.markdown(top)
        if f.offending_text:
            st.markdown(f"> {f.offending_text}")
        st.write(f.explanation)
        st.markdown(f"**Suggested fix:** {f.suggested_fix}")
        if f.validation_notes:
            st.caption("Validation: " + "; ".join(f.validation_notes))
        r = f.latest_response
        if r:
            verb = {"accept": "accepted", "dispute": "disputed"}[r.action]
            st.markdown(f"**Marketing {verb}**" + (f" — “{r.reason}”" if r.reason else "") + f" ({r.actor})")
        if editable_marketing:
            c1, c2, c3 = st.columns([1, 3, 1])
            if c1.button("Accept", key=f"acc{f.id}"):
                run(lambda: svc.respond(user, f.id, "accept"), "Accepted — revise and resubmit to fix it")
                st.rerun()
            reason = c2.text_input("Dispute reason", key=f"why{f.id}", label_visibility="collapsed",
                                   placeholder="Reason for dispute")
            if c3.button("Dispute", key=f"dis{f.id}"):
                if run(lambda: svc.respond(user, f.id, "dispute", reason), "Disputed"):
                    st.rerun()
        fb = f.latest_feedback
        if fb:
            st.caption(f"Compliance marked this finding **{fb.verdict}**" + (f": {fb.note}" if fb.note else ""))
        if editable_compliance:
            c1, c2, c3 = st.columns([1, 1.4, 2.6])
            note = c3.text_input("Note", key=f"note{f.id}", label_visibility="collapsed", placeholder="Optional note")
            if c1.button("✔ AI correct", key=f"ok{f.id}"):
                run(lambda: svc.give_feedback(user, f.id, "correct", note), "Feedback saved")
                st.rerun()
            if c2.button("✘ AI incorrect", key=f"no{f.id}"):
                run(lambda: svc.give_feedback(user, f.id, "incorrect", note), "Feedback saved")
                st.rerun()


with tab_review:
    if current.ai_error:
        st.error(f"AI review failed: {current.ai_error}")
        if user.role == MARKETING and sub.status == SUBMITTED and st.button("Retry AI review"):
            with st.spinner("AI is reviewing..."):
                run(lambda: svc.retry_ai_review(user, sid))
            st.rerun()

    left, right = st.columns([2, 3])
    with left:
        st.markdown(f"#### Version {current.number}")
        with st.container(border=True):
            st.markdown(current.content)
    with right:
        st.markdown(f"#### AI findings ({len(current.findings)})")
        if current.reviewed_at and not current.findings:
            st.success("No issues found by the AI pre-review.")
        can_respond = user.role == MARKETING and sub.status == AI_REVIEWED
        can_rate = user.role == COMPLIANCE and sub.status != SUBMITTED
        for f in current.findings:
            finding_card(f, can_respond, can_rate)

    if user.role == MARKETING and sub.status in {AI_REVIEWED, RETURNED}:
        st.divider()
        st.markdown("#### Step 2 · Revise & resubmit")
        new = st.text_area("Edit the piece", value=current.content, height=220, key=f"edit{sid}{current.number}")
        if st.button("Resubmit revised version"):
            with st.spinner("AI is reviewing the new version..."):
                if run(lambda: svc.resubmit(user, sid, new), "New version submitted"):
                    st.rerun()
    if user.role == MARKETING and sub.status == AI_REVIEWED:
        blockers = svc.gate_blockers(sid)
        if blockers:
            st.warning("Before sending to Compliance:\n\n" + "\n".join(f"- {b}" for b in blockers))
        if st.button("Send to Compliance ➜", type="primary", disabled=bool(blockers)):
            if run(lambda: svc.send_to_compliance(user, sid), "Sent to Compliance"):
                st.rerun()

    if user.role == COMPLIANCE and sub.status == PENDING_COMPLIANCE:
        st.divider()
        st.markdown("#### Step 3 · Compliance decision")
        comment = st.text_area("Comment (required to return or reject)", key=f"cmt{sid}")
        c1, c2, c3 = st.columns(3)
        for col, decision, label in [(c1, APPROVED, "✅ Approve"), (c2, RETURNED, "↩ Return with comments"),
                                     (c3, REJECTED, "⛔ Reject with comments")]:
            if col.button(label, key=f"d{decision}"):
                if run(lambda d=decision: svc.decide(user, sid, d, comment), f"{decision}"):
                    st.rerun()

with tab_versions:
    for v in reversed(sub.versions):
        with st.expander(f"Version {v.number} · {v.created_by} · {len(v.findings)} findings "
                         f"· {', '.join(f.issue_code for f in v.findings) or 'clean'}", expanded=False):
            st.markdown(v.content)
    if len(sub.versions) > 1:
        nums = [v.number for v in sub.versions]
        c1, c2 = st.columns(2)
        a = c1.selectbox("From", nums, index=len(nums) - 2)
        b = c2.selectbox("To", nums, index=len(nums) - 1)
        st.code(svc.diff(sid, a, b) or "(no differences)", language="diff")

with tab_audit:
    rows = [{
        "#": e.id, "when (UTC)": e.at.strftime("%Y-%m-%d %H:%M:%S"), "who": e.actor, "role": e.role,
        "action": e.action, "version": e.version_number, "status": f"{e.from_status or ''} → {e.to_status or ''}"
        if e.to_status else "", "model": e.ai_model or "", "prompt": e.prompt_version or "",
        "details": e.details, "hash": e.hash[:12],
    } for e in svc.audit_log(sid)]
    st.dataframe(rows, width="stretch", hide_index=True)
