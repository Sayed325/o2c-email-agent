# O2C Email Agent

Automated Order-to-Cash email classification and response system powered by Google Gemini AI.

## Architecture

```
data/Sample Emails.json   →   src/classify.py   →   outputs/processed_cases.json
                                                            ↓
                               src/app.py (Streamlit)  ←────┘
                                    ↓
                          src/email_generator.py   →   Draft emails
                                    ↓
                          outputs/sent_emails.json
```

### Components

- **`src/classify.py`** — Batch classifier. Reads 100 emails, classifies each into one of three queues (Cash Application, Disputes, AR Support) using Gemini AI. Uses round-robin API key rotation across multiple keys with model fallback.
- **`src/email_generator.py`** — Draft email generator. Produces professional response emails for classified cases using Gemini AI.
- **`src/app.py`** — Streamlit dashboard. Three queue tabs, case details, AI-generated draft responses, and simulated email sending.

### Queues

| Queue | Category | Example Triggers |
|-------|----------|-----------------|
| Cash Application | Payment Claim | "We paid", "Wire transferred", "Remittance attached" |
| Disputes | Dispute | Short payment, pricing issue, damaged goods, credit note request |
| AR Support | General AR Request | Invoice copy request, statement request, proof of delivery |

## Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure API keys** in `.env`:
   ```
   GEMINI_API_KEY_1=your_key_here
   GEMINI_API_KEY_2=your_key_here
   GEMINI_API_KEY_3=your_key_here
   GEMINI_API_KEY_4=your_key_here
   GEMINI_API_KEY_5=your_key_here
   ```

3. **Run the classifier** (processes all 100 emails):
   ```bash
   python src/classify.py
   ```

4. **Launch the dashboard:**
   ```bash
   streamlit run src/app.py
   ```

## File Structure

```
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
```

## Tech Stack

- **AI Model:** Google Gemini (gemini-2.5-flash-lite / gemini-2.5-flash / gemini-2.0-flash)
- **SDK:** `google-genai`
- **Dashboard:** Streamlit
- **Storage:** JSON files (no database)
