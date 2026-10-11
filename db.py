import psycopg
from pgvector.psycopg import register_vector

import config


def get_conn():
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)
    return conn


SCHEMA_SQL = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kb_chunks (
    id BIGSERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    effective_date DATE,
    section TEXT,
    chunk_text TEXT NOT NULL,
    embedding VECTOR({config.EMBED_DIM}) NOT NULL
);

CREATE INDEX IF NOT EXISTS kb_chunks_status_idx ON kb_chunks (status);
"""


def init_schema():
    with get_conn() as conn:
        conn.execute(SCHEMA_SQL)


def clear_all():
    with get_conn() as conn:
        conn.execute("TRUNCATE kb_chunks")
