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
