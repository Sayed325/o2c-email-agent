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
    for i in range(1, 6):
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
