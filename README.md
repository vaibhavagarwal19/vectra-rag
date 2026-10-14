# Vectra Logistics IT KB Assistant

This is a helpdesk assistant for Vectra Logistics employees. Staff ask IT
questions in plain English, and it answers using only the company's 9 IT
knowledge-base (KB) articles — never from outside knowledge, and never by
guessing.

It returns:

```json
{
  "answer": "...",
  "citations": ["KB-007"],
  "abstained": false
}
```

- `answer` — what to tell the employee.
- `citations` — which KB article(s) the answer came from.
- `abstained` — `true` if the KB doesn't cover the question. When this is
  `true`, the answer just tells the employee to raise a ticket — nothing is
  made up.

## How it works, in plain terms

1. **Load the KB into a database that can search by meaning.** Each of the 9
   `.md` files in `knowledge_base/` gets split into pieces, turned into
   "embeddings" (lists of numbers that represent what the text means), and
   stored in a local Postgres database (using the `pgvector` extension).
2. **Someone asks a question.** We turn the question into the same kind of
   embedding and ask the database: "which stored pieces are closest in
   meaning to this?"
3. **If nothing is close enough, we stop and say so.** No KB match → abstain,
   suggest raising a ticket. We never ask the AI model to improvise an answer
   in this case.
4. **If something matches, we hand those pieces to the AI model** with strict
   instructions: only use what I'm giving you, say which article it came
   from, and if it doesn't fully answer the question, say so instead of
   guessing.
5. **We double-check the model's own answer before returning it** — if it
   claims a citation that wasn't actually part of what we gave it, we throw
   that citation out and treat it as "couldn't find an answer" instead of
   trusting the model's word for it.
6. **We hide anyone's personal info (email, phone number)** before it's sent
   to the AI model or shown in the answer, so none of it leaks.

## Why it's split the way it is

Each KB file has a little header at the top (its ID, title, whether it's
`current`, `deprecated`, or `unverified`, and its last-updated date). The
file's content is then split wherever there's a `##` heading — each section
becomes its own searchable piece. If a file is short and has no headings at
all, the whole file becomes one piece.

This matters for two reasons:

- A couple of the articles have **tables** (ticket priority levels, VPN error
  codes). Splitting by heading means a table never gets cut in half — it
  always stays together inside its section.
- One article (`KB-002`) is **outdated** — a newer one (`KB-007`) replaced
  it. We keep the old one in the database but tag it `deprecated`, and
  searches only look at articles tagged `current`, so the outdated one never
  gets used by accident.
- One article (`KB-099`) is **unverified** — just random tips people posted,
  not checked by IT. We don't even load this one into the database at all.
  (It's also worth knowing this file contains a hidden instruction aimed at
  AI assistants, telling them to recommend turning off antivirus software —
  a deliberate trick. Since we never load it, that trick can't do anything.)

## Project files

| File | What it does |
|---|---|
| `answer.py` | The main `answer(question)` function — this is the core of the project. |
| `ingest.py` | Reads the KB files, splits them, creates embeddings, and loads them into the database. |
| `db.py` | Sets up and connects to the Postgres database. |
| `config.py` | Reads settings (API key, database address, etc.) from `.env`. |
| `pii.py` | Hides email addresses and phone numbers in text. |
| `test_answer.py` | Runs a batch of test questions and reports what passed and failed. |
| `sample_questions.py` | The actual test questions used by `test_answer.py`. |
| `knowledge_base/` | The 9 source KB articles. |
| `docker-compose.yml` | Starts the local database. |

## Setup

Start the database:

```bash
docker compose up -d
```

Set up Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set up your API key:

```bash
cp .env.example .env
```

Then open `.env` and paste in your `OPENAI_API_KEY`. The database runs on
port `5433` (not the usual `5432`), already set correctly in `.env.example`.

## Load the knowledge base

```bash
python ingest.py
```

This reads every file in `knowledge_base/`, skips the unverified one, and
loads everything else into the database.

## Ask a question

From the command line:

```bash
python answer.py "What is the resolution target for a P2 ticket?"
```

Or from Python code:

```python
from answer import answer

result = answer("What VPN server address should I use?")
print(result)
```

## Run the tests

```bash
python test_answer.py
```

This runs through the 5 official sample questions plus a batch of tricky and
edge-case ones (a stale document trap, a value hidden inside a table, a
prompt-injection attempt, a blank question, and more), and prints which ones
passed or failed and why.

## Safety measures

- Only `current` articles are searched — `deprecated` ones are excluded at
  search time.
- `unverified` articles are never loaded into the database in the first
  place.
- Personal information is hidden before it reaches the AI model or the final
  answer.
- Every citation the model returns is checked against what it was actually
  given — a made-up citation gets thrown out, not trusted.
- If the KB doesn't cover a question, the assistant says so and suggests
  raising a ticket, instead of guessing.

## What's not perfect yet

The cutoff used to decide "is this close enough to the KB to answer, or
should I abstain" was tuned on a small number of test questions. It works for
all 5 official sample questions, but at least one reasonable question (asking
if it's okay to disable antivirus) ends up on the wrong side of that cutoff
and incorrectly abstains, even though the KB does cover it. Before this goes
live to all 3,000 staff, this needs either a larger set of test questions to
tune against, or a smarter retrieval method (like reranking) instead of a
single fixed cutoff number.
