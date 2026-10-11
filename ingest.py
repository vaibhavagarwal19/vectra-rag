import glob
import os
import re

import yaml
from openai import OpenAI
from pgvector import Vector

import config
import db

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_kb_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    m = FRONT_MATTER_RE.match(raw)
    if not m:
        raise ValueError(f"{path} is missing the --- front-matter block")
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2).strip()
    meta["body"] = body
    return meta


def split_sections(body: str) -> list[tuple[str, str]]:
    lines = body.splitlines()
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    if not sections:
        sections = [("", body.strip())]
    return sections


def embed_texts(client: OpenAI, texts: list[str]) -> list[list[float]]:
    resp = client.embeddings.create(model=config.EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def ingest_all(kb_dir: str | None = None, wipe_first: bool = True) -> dict:
    kb_dir = kb_dir or config.KB_DIR
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    db.init_schema()
    if wipe_first:
        db.clear_all()

    summary: dict[str, int | list[str]] = {"files": 0, "chunks": 0, "skipped": []}
    paths = sorted(glob.glob(os.path.join(kb_dir, "KB-*.md")))

    rows = []
    for path in paths:
        meta = parse_kb_file(path)
        doc_id = meta["doc_id"]
        status = meta.get("status", "current")

        if status == "unverified":
            summary["skipped"].append(doc_id)
            continue

        sections = split_sections(meta["body"])
        for heading, text in sections:
            rows.append(
                {
                    "doc_id": doc_id,
                    "title": meta.get("title", doc_id),
                    "status": status,
                    "effective_date": meta.get("effective_date"),
                    "section": heading,
                    "chunk_text": text,
                }
            )
        summary["files"] += 1

    if not rows:
        return summary

    embeddings = embed_texts(client, [r["chunk_text"] for r in rows])

    with db.get_conn() as conn, conn.cursor() as cur:
        for row, emb in zip(rows, embeddings):
            cur.execute(
                """
                INSERT INTO kb_chunks
                    (doc_id, title, status, effective_date, section, chunk_text, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["doc_id"],
                    row["title"],
                    row["status"],
                    row["effective_date"],
                    row["section"],
                    row["chunk_text"],
                    Vector(emb),
                ),
            )
    summary["chunks"] = len(rows)
    return summary


if __name__ == "__main__":
    result = ingest_all()
    print(f"Ingested {result['chunks']} chunks from {result['files']} files.")
    if result["skipped"]:
        print(f"Skipped unverified docs (never ingested): {result['skipped']}")
