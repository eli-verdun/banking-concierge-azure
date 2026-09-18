"""Vector-store retrieval over the synthetic banking knowledge base."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from concierge.azure_foundry import make_embeddings

# override=True so .env wins over anything exported in the shell, no matter
# which entry point imported this module first.
load_dotenv(override=True)

KB_DIR = Path(__file__).parent / "kb"


def _make_embeddings():
    """Create the Azure AI Foundry embeddings client."""
    return make_embeddings()


def _load_kb_documents() -> list[Document]:
    docs: list[Document] = []
    for md_path in sorted(KB_DIR.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        docs.append(
            Document(
                page_content=text,
                metadata={"source": md_path.name, "topic": md_path.stem},
            )
        )
    return docs


@lru_cache(maxsize=1)
def get_vector_store() -> InMemoryVectorStore:
    docs = _load_kb_documents()
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80)
    chunks = splitter.split_documents(docs)
    embeddings = _make_embeddings()
    return InMemoryVectorStore.from_documents(chunks, embeddings)


def retrieve(query: str, k: int = 4) -> list[Document]:
    return get_vector_store().similarity_search(query, k=k)
