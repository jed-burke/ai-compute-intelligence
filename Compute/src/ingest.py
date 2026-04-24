"""
PDF ingestion pipeline: extract text, chunk, embed, store in ChromaDB.
"""

import os
import re
import zipfile
import hashlib
from pathlib import Path

import pdfplumber
import chromadb
from chromadb.utils import embedding_functions

BASE_DIR = Path(__file__).parent.parent
RESEARCH_ZIP = BASE_DIR / "research.zip"
RESEARCH_DIR = BASE_DIR / "research"
CHROMA_DIR = BASE_DIR / "data" / "chroma"

CHUNK_SIZE = 1800      # characters (~450 tokens)
CHUNK_OVERLAP = 200    # characters of overlap between chunks
EMBED_MODEL = "all-MiniLM-L6-v2"
COLLECTION_NAME = "ai_compute_research"


def get_chroma_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def _get_chroma_client():
    """Lightweight client with no embedding model — safe to call at startup."""
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def extract_zip():
    """Unzip research.zip into the research/ directory if not already done."""
    if not RESEARCH_DIR.exists() or not any(RESEARCH_DIR.glob("*.pdf")):
        RESEARCH_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(RESEARCH_ZIP, "r") as z:
            z.extractall(RESEARCH_DIR)
        return True
    return False


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)
    return text.strip()


def chunk_text(text: str, source: str, page_start: int = 0) -> list[dict]:
    chunks = []
    start = 0
    chunk_index = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end]
        if len(chunk.strip()) > 100:  # skip tiny fragments
            chunks.append({
                "text": chunk.strip(),
                "source": source,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def extract_pdf(pdf_path: Path) -> list[dict]:
    chunks = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                try:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"
                except Exception:
                    continue
            full_text = clean_text(full_text)
            chunks = chunk_text(full_text, source=pdf_path.name)
    except Exception as e:
        print(f"  Warning: could not read {pdf_path.name}: {e}")
    return chunks


def make_chunk_id(source: str, index: int) -> str:
    raw = f"{source}::{index}"
    return hashlib.md5(raw.encode()).hexdigest()


def ingest_all(progress_callback=None) -> dict:
    """
    Full ingestion pipeline. Returns a status dict.
    progress_callback(current, total, filename) called for each PDF.
    """
    extract_zip()

    pdf_files = sorted(RESEARCH_DIR.glob("*.pdf"))
    if not pdf_files:
        return {"status": "error", "message": "No PDFs found in research/"}

    collection = get_chroma_collection()

    # Find which PDFs are already ingested by checking stored sources
    existing = collection.get(include=["metadatas"])
    ingested_sources = set()
    if existing["metadatas"]:
        for meta in existing["metadatas"]:
            if meta and "source" in meta:
                ingested_sources.add(meta["source"])

    total = len(pdf_files)
    new_chunks = 0
    skipped = 0

    for i, pdf_path in enumerate(pdf_files):
        if progress_callback:
            progress_callback(i + 1, total, pdf_path.name)

        if pdf_path.name in ingested_sources:
            skipped += 1
            continue

        chunks = extract_pdf(pdf_path)
        if not chunks:
            continue

        ids = [make_chunk_id(c["source"], c["chunk_index"]) for c in chunks]
        documents = [c["text"] for c in chunks]
        metadatas = [{"source": c["source"], "chunk_index": c["chunk_index"]} for c in chunks]

        # Upsert in batches of 100
        batch_size = 100
        for b in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[b:b+batch_size],
                documents=documents[b:b+batch_size],
                metadatas=metadatas[b:b+batch_size],
            )

        new_chunks += len(chunks)

    total_docs = collection.count()
    return {
        "status": "ok",
        "pdfs_processed": total - skipped,
        "pdfs_skipped": skipped,
        "new_chunks": new_chunks,
        "total_chunks": total_docs,
    }


def ingest_web_articles(articles: list[dict]) -> dict:
    """
    Chunk and embed a list of web articles into ChromaDB.
    Each article: {"title", "url", "text", "source_name", "date"}
    """
    if not articles:
        return {"status": "ok", "new_chunks": 0, "total_chunks": chunk_count()}

    collection = get_chroma_collection()
    new_chunks = 0

    for article in articles:
        text = clean_text(article["text"])
        chunks = chunk_text(text, source=article["source_name"])

        ids, documents, metadatas = [], [], []
        for c in chunks:
            chunk_id = make_chunk_id(article["url"], c["chunk_index"])
            ids.append(chunk_id)
            documents.append(c["text"])
            metadatas.append({
                "source": article["source_name"],
                "url": article["url"],
                "title": article.get("title", ""),
                "date": article.get("date", ""),
                "content_type": "web",
                "chunk_index": c["chunk_index"],
            })

        if not ids:
            continue

        batch_size = 100
        for b in range(0, len(ids), batch_size):
            collection.upsert(
                ids=ids[b:b+batch_size],
                documents=documents[b:b+batch_size],
                metadatas=metadatas[b:b+batch_size],
            )
        new_chunks += len(ids)

    return {
        "status": "ok",
        "new_chunks": new_chunks,
        "total_chunks": collection.count(),
    }


def is_ingested() -> bool:
    try:
        client = _get_chroma_client()
        col = client.get_collection(COLLECTION_NAME)  # raises if not found
        return col.count() > 0
    except Exception:
        return False


def chunk_count() -> int:
    try:
        client = _get_chroma_client()
        col = client.get_collection(COLLECTION_NAME)  # raises if not found
        return col.count()
    except Exception:
        return 0


def get_sources() -> dict:
    """
    Return {"pdf": [...], "web": [...]} of unique source names in the DB.
    PDF sources are filenames ending in .pdf; everything else is web.
    """
    try:
        col = get_chroma_collection()
        result = col.get(include=["metadatas"])
        pdf, web = set(), set()
        for meta in (result["metadatas"] or []):
            if not meta:
                continue
            src = meta.get("source", "")
            if src.lower().endswith(".pdf"):
                pdf.add(src)
            elif src:
                web.add(src)
        return {"pdf": sorted(pdf), "web": sorted(web)}
    except Exception:
        return {"pdf": [], "web": []}
