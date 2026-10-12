# Vectra Logistics IT KB Assistant

This project answers IT help-desk questions for Vectra Logistics staff.

It only answers from the files in `knowledge_base/`. If the knowledge base does
not cover the question, the assistant says it cannot find an answer and tells the
user to raise a ticket.

## What It Does

- Loads the IT knowledge base into Postgres with pgvector.
- Finds the most relevant knowledge base sections for a user question.
- Sends only those sections to an OpenAI chat model.
- Returns a JSON answer with citations.
- Masks email addresses and phone numbers before calling OpenAI.
- Ignores deprecated or unverified articles.

Example output:

```json
{
  "answer": "A P2 ticket has a 30 minute first-response target and an 8 business hour resolution target.",
  "citations": ["KB-003"],
  "abstained": false
}
```

## Project Files

- `answer.py` - main question-answering code.
- `ingest.py` - loads the knowledge base into the database.
- `db.py` - creates and connects to the Postgres database.
- `config.py` - reads settings from `.env`.
- `pii.py` - masks personal data.
- `test_answer.py` - runs sample and edge-case questions.
- `knowledge_base/` - the source articles used for answers.
- `docker-compose.yml` - starts local Postgres with pgvector.

## Setup

Start the database:

```bash
docker compose up -d
```

Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```bash
cp .env.example .env
```

Open `.env` and add your `OPENAI_API_KEY`.

## Load The Knowledge Base

Run:

```bash
python ingest.py
```

This reads the Markdown files in `knowledge_base/`, creates embeddings, and saves
the searchable chunks in Postgres.

The local database runs on port `5433`.

## Ask A Question

Run:

```bash
python answer.py "What is the resolution target for a P2 ticket?"
```

You can also import the function in Python:

```python
from answer import answer

result = answer("What VPN server address should I use?")
print(result)
```

## Run Tests

Run:

```bash
python test_answer.py
```

The tests check normal questions, tricky questions, prompt-injection attempts,
deprecated articles, unverified articles, and PII masking.

## How Answers Are Kept Safe

The assistant has a few important guardrails:

- It only searches articles marked as `current`.
- It does not ingest articles marked as `unverified`.
- It does not use deprecated VPN instructions from `KB-002`.
- It masks email addresses and phone numbers before sending text to OpenAI.
- It returns citations so the source article is visible.
- It abstains when the KB does not contain an answer.

## Current Known Limitation

The similarity threshold works for the official sample questions, but it is not a
perfect long-term solution. Some valid questions may be close to the cutoff. A
production version should add reranking, keyword search, or a larger test set
before rolling this out to all staff.

