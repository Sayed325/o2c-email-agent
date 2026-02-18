# PROJECT OVERVIEW — O2C Email Agent

Complete source listing of every file in the project.

---

## `.env`

```env
GEMINI_API_KEY_1=<your-api-key-1>
GEMINI_API_KEY_2=<your-api-key-2>
GEMINI_API_KEY_3=<your-api-key-3>
GEMINI_API_KEY_4=<your-api-key-4>
GEMINI_API_KEY_5=<your-api-key-5>
```

---

## `requirements.txt`

```txt
google-genai
python-dotenv
streamlit
```

---

## `README.md`

```markdown
# O2C Email Agent

Automated Order-to-Cash email classification and response system powered by Google Gemini AI.

## Architecture

data/Sample Emails.json   →   src/classify.py   →   outputs/processed_cases.json
                                                            ↓
                               src/app.py (Streamlit)  ←────┘
                                    ↓
                          src/email_generator.py   →   Draft emails
                                    ↓
                          outputs/sent_emails.json

### Components

- **`src/classify.py`** — Batch classifier. Reads 100 emails, classifies each into one of three queues (Cash Application, Disputes, AR Support) using Gemini AI. Uses round-robin API key rotation across multiple keys with model fallback.
- **`src/email_generator.py`** — Draft email generator. Produces professional response emails for classified cases using Gemini AI.
- **`src/app.py`** — Streamlit dashboard. Four queue tabs (Cash Application, Disputes, AR Support, Manual Review), case details, AI-generated draft responses, and simulated email sending. Shows a warning banner when emails need manual review.

### Queues

| Queue | Category | Example Triggers |
|-------|----------|-----------------|
| Cash Application | Payment Claim | "We paid", "Wire transferred", "Remittance attached" |
| Disputes | Dispute | Short payment, pricing issue, damaged goods, credit note request |
| AR Support | General AR Request | Invoice copy request, statement request, proof of delivery |
| Manual Review | Error | Classification failures, API errors, exhausted retries |

## Setup

1. **Install dependencies:**
   pip install -r requirements.txt

2. **Configure API keys** in `.env`:
   GEMINI_API_KEY_1=your_key_here
   GEMINI_API_KEY_2=your_key_here
   GEMINI_API_KEY_3=your_key_here
   GEMINI_API_KEY_4=your_key_here
   GEMINI_API_KEY_5=your_key_here

3. **Run the classifier** (processes all 100 emails):
   python src/classify.py

4. **Launch the dashboard:**
   streamlit run src/app.py

## File Structure

o2c-email-agent/
├── data/
│   └── Sample Emails.json      # 100 input emails
├── outputs/
│   ├── processed_cases.json    # Classifier output
│   └── sent_emails.json        # Sent email log
├── src/
│   ├── classify.py             # Batch classifier
│   ├── email_generator.py      # Draft generator
│   └── app.py                  # Streamlit dashboard
├── .env                        # API keys
├── requirements.txt
└── README.md

## Tech Stack

- **AI Model:** Google Gemini (gemini-2.5-flash-lite / gemini-2.5-flash / gemini-2.0-flash)
- **SDK:** `google-genai`
- **Dashboard:** Streamlit
- **Storage:** JSON files (no database)
```

---

## `src/classify.py`

```python
"""Batch email classifier — run once before launching the dashboard."""

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google import genai

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = BASE_DIR / "data" / "Sample Emails.json"
OUTPUT_FILE = BASE_DIR / "outputs" / "processed_cases.json"

MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash"]

CLASSIFY_PROMPT = """You are an Order-to-Cash email classification agent.

Analyze this email and respond with ONLY valid JSON, no markdown, no backticks:

From: {sender}
Subject: {subject}
Body: {body}
Received: {received_at}

Respond in this exact JSON format:
{{
    "category": "Payment Claim" OR "Dispute" OR "General AR Request",
    "queue": "Cash Application" OR "Disputes" OR "AR Support",
    "customer_name": "extracted company name",
    "invoice_references": ["INV-XXXXX"],
    "amounts": [],
    "dates": [],
    "dispute_reason": "reason if dispute, otherwise empty string",
    "next_action": "brief recommended next step"
}}

Classification rules:
- "Payment Claim" -> customer says they paid, transferred, remitted -> queue: "Cash Application"
- "Dispute" -> short payment, pricing issue, damaged goods, credit note request, partial payment, deductions, payment on hold -> queue: "Disputes"
- "General AR Request" -> invoice copy request, statement request, payment confirmation request, proof of delivery request -> queue: "AR Support"
"""


def load_api_keys() -> list[str]:
    load_dotenv(BASE_DIR / ".env")
    keys = []
    for i in range(1, 20):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            keys.append(key)
    if not keys:
        print("Error: No GEMINI_API_KEY_* found in .env")
        sys.exit(1)
    return keys


def load_emails() -> list[dict]:
    with open(DATA_FILE, encoding="utf-8") as f:
        return json.load(f)["emails"]


def parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)


def classify_email(email: dict, clients: list, key_index: int) -> dict | None:
    """Classify a single email, rotating through keys and models on failure."""
    prompt = CLASSIFY_PROMPT.format(
        sender=email["from"],
        subject=email["subject"],
        body=email["body"],
        received_at=email["receivedAt"],
    )

    num_keys = len(clients)

    for model in MODELS:
        for offset in range(num_keys):
            ki = (key_index + offset) % num_keys
            client = clients[ki]
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(max_output_tokens=1024),
                )
                return parse_json(response.text)
            except json.JSONDecodeError:
                print(f"\n    JSON parse error on key{ki+1}/{model}", end=" ", flush=True)
                continue
            except Exception as e:
                err = str(e)
                if "429" in err or "503" in err:
                    print(f"\n    Rate limited key{ki+1}/{model}", end=" ", flush=True)
                    continue
                raise

    # All keys/models failed once — wait and try one more time
    print("\n    All keys busy, waiting 15s...", end=" ", flush=True)
    time.sleep(15)
    for model in MODELS:
        for offset in range(num_keys):
            ki = (key_index + offset) % num_keys
            client = clients[ki]
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(max_output_tokens=1024),
                )
                return parse_json(response.text)
            except Exception:
                continue

    return None


def main():
    keys = load_api_keys()
    print(f"Loaded {len(keys)} API keys.")

    clients = [genai.Client(api_key=k) for k in keys]

    emails = load_emails()
    print(f"Found {len(emails)} emails to process.\n")

    results = []
    errors = 0

    for i, email in enumerate(emails):
        ki = i % len(clients)
        print(f"Processing email {i+1}/{len(emails)} (using key {ki+1})...", end=" ", flush=True)

        try:
            data = classify_email(email, clients, ki)
            if data is None:
                raise RuntimeError("All keys exhausted")

            results.append({
                "email_id": email["id"],
                "received_at": email["receivedAt"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
                **data,
            })
            print(f"-> {data['category']} -> {data['queue']}")
        except Exception as e:
            errors += 1
            print(f"ERROR: {e}")
            results.append({
                "email_id": email["id"],
                "received_at": email["receivedAt"],
                "from": email["from"],
                "subject": email["subject"],
                "body": email["body"],
                "category": "Error",
                "queue": "Manual Review",
                "customer_name": "",
                "invoice_references": [],
                "amounts": [],
                "dates": [],
                "dispute_reason": "",
                "next_action": f"Manual review needed: {str(e)[:100]}",
            })

        # Save incrementally
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        # Rate limit delay
        if i < len(emails) - 1:
            time.sleep(4)

    # Print summary
    counts = Counter(r["queue"] for r in results)
    print(f"\nDone! Processed {len(results)}/{len(emails)} emails.")
    print(f"- Cash Application: {counts.get('Cash Application', 0)}")
    print(f"- Disputes: {counts.get('Disputes', 0)}")
    print(f"- AR Support: {counts.get('AR Support', 0)}")
    if errors:
        print(f"- Errors: {errors}")
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
```

---

## `src/email_generator.py`

```python
"""Draft email generator using Gemini API."""

import json
import random

from google import genai

MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]

DRAFT_PROMPT = """You are a professional Accounts Receivable team member.
Generate a response email for this case.

Queue: {queue}
Category: {category}
Customer: {customer_name}
Original Subject: {subject}
Invoice References: {invoice_references}
Dispute Reason: {dispute_reason}
Recommended Action: {next_action}

Write a professional, concise response email addressed to the customer.
End the email with:
Sincerely,
Your {queue} Team

Respond with ONLY valid JSON, no markdown, no backticks:
{{
    "subject": "Re: original subject",
    "body": "professional email body text ending with the sign-off above"
}}"""


def generate_draft_email(case: dict, api_keys: list[str]) -> dict:
    """Generate a draft response email for a case. Returns {subject, body}."""
    prompt = DRAFT_PROMPT.format(
        queue=case.get("queue", "AR Support"),
        category=case.get("category", ""),
        customer_name=case.get("customer_name", ""),
        subject=case.get("subject", ""),
        invoice_references=", ".join(case.get("invoice_references", [])),
        dispute_reason=case.get("dispute_reason", ""),
        next_action=case.get("next_action", ""),
    )

    # Try random keys and models
    shuffled_keys = random.sample(api_keys, len(api_keys))
    for key in shuffled_keys:
        client = genai.Client(api_key=key)
        for model in MODELS:
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(max_output_tokens=1024),
                )
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1]
                    text = text.rsplit("```", 1)[0].strip()
                return json.loads(text)
            except Exception:
                continue

    return {
        "subject": f"Re: {case.get('subject', '')}",
        "body": "Unable to generate draft at this time. Please compose manually.",
    }
```

---

## `src/app.py`

```python
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
    for i in range(1, 20):
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
        labels.append(f"{inv} — {customer} — {subject}")

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
    st.title("O2C Email Agent — Dashboard")

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
```
