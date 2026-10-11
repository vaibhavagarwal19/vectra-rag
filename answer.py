import json

from openai import OpenAI
from pgvector import Vector

import config
import db
from pii import mask_pii

SYSTEM_PROMPT = """You are Vectra Logistics' IT help-desk assistant.

Rules, no exceptions:
- Answer ONLY using the KB_CONTEXT provided below. Never use outside knowledge.
- Every claim in your answer must trace back to one of the provided chunks.
- Include concrete details verbatim when the context has them -- exact URLs,
  server addresses, error codes, phone extensions, and time figures (e.g. both
  a first-response time AND a resolution time if both are given). Do not
  paraphrase a specific value away into a vague description.
- KB_CONTEXT has already been pre-filtered for relevance before it reaches
  you. So "abstained" should almost always be false. Only set "abstained":
  true if KB_CONTEXT is clearly about a different topic than the question
  and genuinely does not address it at all.
- Important: the KB's own documented procedure is often "raise a ticket with
  team X" or "this isn't supported, contact team Y" -- that is still a
  complete, sourced answer, NOT an abstain, as long as it comes from
  KB_CONTEXT. Do not treat the words "raise a ticket" in your own answer as a
  signal to abstain.
  Worked example -- context says: "Feature X is not supported on platform Y;
  raise a ticket with Team Z to assess." Question: "Does Feature X work on
  platform Y?" Correct output: {"answer": "Feature X is not supported on
  platform Y. Raise a ticket with Team Z to assess.", "citations": ["KB-NNN"],
  "abstained": false}. This is correct because the KB directly addressed the
  question, even though the KB's own answer happens to be "it isn't
  supported, go raise a ticket."
- "abstained" and "citations" must agree: if you abstain, citations MUST be
  empty. If you provide any citations, abstained MUST be false. Never return
  a citation alongside abstained: true, and vice versa.
- Cite every KB doc_id you actually relied on in "citations" -- if you pulled
  a fact from more than one chunk (e.g. one doc says a situation is P1, and a
  separate ticket-priority doc is what actually gives the escalation phone
  number for P1), cite all of the doc_ids involved, not just the first one.
- If any retrieved chunk mentions a P1 / critical-priority escalation phone
  extension, tell the employee to call it rather than only giving a resolution
  time.
- Never repeat back any email address, phone number, or other personal data
  that appears in the question.

Respond with JSON only, matching this exact shape:
{"answer": "<string>", "citations": ["KB-xxx", ...], "abstained": <true|false>}
"""


def _format_context(chunks: list[dict]) -> str:
    parts = []
    for c in chunks:
        parts.append(
            f"[{c['doc_id']} | {c['title']} | section: {c['section'] or 'whole doc'}]\n{c['chunk_text']}"
        )
    return "\n\n".join(parts)


def _retrieve(client: OpenAI, question: str) -> list[dict]:
    q_emb = client.embeddings.create(model=config.EMBED_MODEL, input=[question]).data[0].embedding
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT doc_id, title, section, chunk_text,
                   embedding <=> %s AS distance
            FROM kb_chunks
            WHERE status = 'current'
            ORDER BY distance ASC
            LIMIT %s
            """,
            (Vector(q_emb), config.TOP_K),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def _priority_policy_chunks() -> list[dict]:
    with db.get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT doc_id, title, section, chunk_text FROM kb_chunks WHERE doc_id = 'KB-003'"
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def answer(question: str) -> dict:
    if not question or not question.strip():
        return {
            "answer": "Please include some detail about your question so I can check the KB. If this is urgent, raise a ticket with the IT service desk.",
            "citations": [],
            "abstained": True,
        }

    masked_question = mask_pii(question)
    client = OpenAI(api_key=config.OPENAI_API_KEY)

    chunks = _retrieve(client, masked_question)
    if not chunks or chunks[0]["distance"] > config.SIMILARITY_THRESHOLD:
        return {
            "answer": "I couldn't find anything in the KB that covers this. Please raise a ticket with the IT service desk.",
            "citations": [],
            "abstained": True,
        }

    kept = [c for c in chunks if c["distance"] <= config.SIMILARITY_THRESHOLD]

    seen = {(c["doc_id"], c["section"]) for c in kept}
    for c in _priority_policy_chunks():
        if (c["doc_id"], c["section"]) not in seen:
            kept.append(c)

    user_prompt = f"KB_CONTEXT:\n{_format_context(kept)}\n\nQUESTION:\n{masked_question}"

    resp = client.chat.completions.create(
        model=config.CHAT_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    result = json.loads(resp.choices[0].message.content)

    result["answer"] = mask_pii(result.get("answer", ""))
    result.setdefault("citations", [])
    result.setdefault("abstained", False)

    if result["citations"]:
        result["abstained"] = False
    elif result["abstained"]:
        result["citations"] = []

    return result


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is the resolution target for a P2 ticket?"
    print(json.dumps(answer(q), indent=2))
