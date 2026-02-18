"""Streamlit dashboard for O2C Email Agent."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from email_generator import generate_draft_email

BASE_DIR = Path(__file__).resolve().parent.parent
CASES_FILE = BASE_DIR / "outputs" / "processed_cases.json"
SENT_FILE = BASE_DIR / "outputs" / "sent_emails.json"

QUEUE_EMAILS = {
    "Cash Application": "cashapplication@email.com",
    "Disputes": "disputes@email.com",
    "AR Support": "general@email.com",
}


def load_api_keys() -> list[str]:
    load_dotenv(BASE_DIR / ".env")
    keys = []
    for i in range(1, 6):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key)
    return keys


def load_cases() -> list[dict]:
    if not CASES_FILE.exists():
        return []
    with open(CASES_FILE, encoding="utf-8") as f:
        return json.load(f)


def log_sent_email(case: dict, draft: dict, recipient: str):
    sent = []
    if SENT_FILE.exists():
        with open(SENT_FILE, encoding="utf-8") as f:
            sent = json.load(f)
    sent.append({
        "email_id": case["email_id"],
        "to": recipient,
        "subject": draft["subject"],
        "body": draft["body"],
        "sent_at": datetime.now().isoformat(),
    })
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sent, f, indent=2)


def render_queue_tab(cases: list[dict], queue_name: str, api_keys: list[str]):
    """Render a single queue tab with case selector and details."""
    queue_cases = [c for c in cases if c.get("queue") == queue_name]

    if not queue_cases:
        st.info(f"No cases in {queue_name} queue.")
        return

    st.caption(f"{len(queue_cases)} cases")

    # Build display labels for selectbox
    labels = []
    for c in queue_cases:
        inv = ", ".join(c.get("invoice_references", [])) or "N/A"
        customer = c.get("customer_name", "Unknown")
        subject = c.get("subject", "")
        labels.append(f"{inv} \u2014 {customer} \u2014 {subject}")

    selected_idx = st.selectbox(
        "Select a case:",
        range(len(labels)),
        format_func=lambda i: labels[i],
        key=f"select_{queue_name}",
    )

    case = queue_cases[selected_idx]

    # Details panel
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Customer:** {case.get('customer_name', 'N/A')}")
        st.markdown(f"**Invoice References:** {', '.join(case.get('invoice_references', [])) or 'N/A'}")
        st.markdown(f"**Amounts:** {', '.join(str(a) for a in case.get('amounts', [])) or 'N/A'}")
    with col2:
        st.markdown(f"**Dates:** {', '.join(case.get('dates', [])) or 'N/A'}")
        dispute = case.get("dispute_reason", "")
        st.markdown(f"**Dispute Details:** {dispute or 'N/A'}")
        st.markdown(f"**Recommended Action:** {case.get('next_action', 'N/A')}")

    with st.expander("Original Email"):
        st.text(f"From: {case.get('from', '')}")
        st.text(f"Subject: {case.get('subject', '')}")
        st.text(f"Received: {case.get('received_at', '')}")
        st.text("")
        st.text(case.get("body", ""))

    # Draft email generation
    st.markdown("---")
    draft_key = f"draft_{queue_name}_{selected_idx}"

    if st.button("Generate Draft Email", key=f"gen_{queue_name}_{selected_idx}"):
        with st.spinner("Generating draft..."):
            draft = generate_draft_email(case, api_keys)
            st.session_state[draft_key] = draft

    if draft_key in st.session_state:
        draft = st.session_state[draft_key]
        recipient = case.get("from", "unknown@email.com")
        st.markdown(f"**To:** {recipient}")
        st.markdown(f"**Subject:** {draft['subject']}")

        edited_body = st.text_area(
            "Email Body:",
            value=draft["body"],
            height=200,
            key=f"body_{queue_name}_{selected_idx}",
        )

        if st.button("Send Email", key=f"send_{queue_name}_{selected_idx}"):
            final_draft = {"subject": draft["subject"], "body": edited_body}
            log_sent_email(case, final_draft, recipient)
            st.success(f"Email sent to {recipient}!")


def main():
    st.set_page_config(page_title="O2C Email Agent", layout="wide")
    st.title("O2C Email Agent \u2014 Dashboard")

    cases = load_cases()
    if not cases:
        st.error("No processed cases found. Run `python src/classify.py` first to process emails.")
        return

    api_keys = load_api_keys()
    if not api_keys:
        st.warning("No API keys found in .env. Draft generation will not work.")

    manual_review_count = sum(1 for c in cases if c.get("queue") == "Manual Review")
    if manual_review_count:
        st.warning(f"⚠️ {manual_review_count} emails need manual review")

    tab1, tab2, tab3, tab4 = st.tabs(["Cash Application", "Disputes", "AR Support", "Manual Review"])

    with tab1:
        render_queue_tab(cases, "Cash Application", api_keys)
    with tab2:
        render_queue_tab(cases, "Disputes", api_keys)
    with tab3:
        render_queue_tab(cases, "AR Support", api_keys)
    with tab4:
        render_queue_tab(cases, "Manual Review", api_keys)


if __name__ == "__main__":
    main()
