import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
EMBED_DIM = 1536

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://vectra:vectra@localhost:5433/vectra_rag")

TOP_K = int(os.getenv("TOP_K", "4"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.25"))

KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "knowledge_base")
