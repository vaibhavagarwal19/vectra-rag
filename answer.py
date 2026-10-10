"""The core answer(question) function the brief asks for.

Pipeline:
  1. Mask PII in the incoming question before it's logged or sent to OpenAI.
  2. Embed the (masked) question and do a cosine-similarity search against
     pgvector, restricted to status = 'current' -- this is what stops the
     deprecated KB-002 VPN doc from ever being retrieved, instead of hoping
     the model notices a status line in the text. (KB-099 is never even in
     the table -- see ingest.py.)
  3. If nothing clears the similarity threshold, abstain immediately --
     no call to the chat model, no invented answer.
  4. Otherwise, ask the chat model to answer using ONLY the retrieved
     chunks, in a fixed JSON shape, citing doc_ids. If KB-003's P1 escalation
     language is in the retrieved context, the prompt tells the model to
     surface the phone extension rather than just the SLA number.
  5. Mask PII again on the way out, defensively, in case the model echoed
     anything back.
"""
import json

from openai import OpenAI

import config
import db
from pii import mask_pii

SYSTEM_PROMPT = """You are Vectra Logistics' IT help-desk assistant.

Rules, no exceptions:
- Answer ONLY using the KB_CONTEXT provided below. Never use outside knowledge.
- Every claim in your answer must trace back to one of the provided chunks.
- If the context does not fully answer the question, set "abstained": true,
  write an answer that tells the employee to raise a ticket, and return an
  empty citations list. Do not guess, do not partially answer, do not invent
  a process, URL, or policy that is not in the context.
- Cite the KB doc_ids you actually relied on in "citations".
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
            (q_emb, config.TOP_K),
        )
        rows = cur.fetchall()
        cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def answer(question: str) -> dict:
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
    return result


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "What is the resolution target for a P2 ticket?"
    print(json.dumps(answer(q), indent=2))
