"""
Retrieval and Claude API integration.
"""

from __future__ import annotations
import os
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import anthropic

from ingest import get_chroma_collection

load_dotenv(Path(__file__).parent.parent / ".env")

TOP_K = 8
MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an AI compute intelligence analyst. Your job is to provide \
rigorous, evidence-based analysis of global AI compute infrastructure — including data \
centers, GPU/chip supply chains, hyperscaler strategies, export controls, and geopolitical \
dependencies.

You answer questions using ONLY the research documents provided in the context below. \
When you cite information, reference the source document by name. If the provided context \
does not contain enough information to answer confidently, say so explicitly rather than \
speculating. Be precise and analytical."""


def build_where_clause(
    source_type: str,           # "all" | "pdf" | "web"
    selected_sources: list[str],
    days_back: int | None,
    pdf_sources: list[str],
    web_sources: list[str],
) -> dict | None:
    """Build a ChromaDB where clause from the active filters."""

    # 1. Determine candidate pool
    if source_type == "pdf":
        pool = list(pdf_sources)
    elif source_type == "web":
        pool = list(web_sources)
    else:
        pool = list(pdf_sources) + list(web_sources)

    # 2. Apply specific-source selection
    if selected_sources:
        pool = [s for s in pool if s in selected_sources]

    if not pool:
        return None

    # 3. Date filter — applies only to web chunks (PDFs have no date)
    if days_back and source_type != "pdf":
        cutoff = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        web_pool = [s for s in pool if s in web_sources]
        pdf_pool = [s for s in pool if s in pdf_sources]

        if web_pool and pdf_pool:
            # Mix: date-filtered web OR all selected PDFs
            return {"$or": [
                {"$and": [
                    {"source": {"$in": web_pool}},
                    {"date": {"$gte": cutoff}},
                ]},
                {"source": {"$in": pdf_pool}},
            ]}
        elif web_pool:
            return {"$and": [
                {"source": {"$in": web_pool}},
                {"date": {"$gte": cutoff}},
            ]}
        else:
            return {"source": {"$in": pdf_pool}}

    # 4. No date filter
    if len(pool) == 1:
        return {"source": pool[0]}
    return {"source": {"$in": pool}}


def retrieve(
    query_text: str,
    n_results: int = TOP_K,
    where: dict | None = None,
) -> list[dict]:
    """Return top-k chunks from ChromaDB most relevant to the query."""
    collection = get_chroma_collection()
    total = collection.count()
    if total == 0:
        return []

    kwargs = dict(
        query_texts=[query_text],
        n_results=min(n_results, total),
        include=["documents", "metadatas", "distances"],
    )
    if where:
        kwargs["where"] = where

    results = collection.query(**kwargs)
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "source": meta.get("source", "unknown"),
            "url": meta.get("url", ""),
            "title": meta.get("title", ""),
            "date": meta.get("date", ""),
            "score": round(1 - dist, 3),
        })
    return chunks


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] Source: {chunk['source']}\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)


def query(
    question: str,
    api_key: str,
    n_results: int = TOP_K,
    where: dict | None = None,
) -> dict:
    """
    Run a RAG query: retrieve relevant chunks, then ask Claude.
    Returns {"answer": str, "sources": list[str], "chunks": list[dict]}
    """
    chunks = retrieve(question, n_results=n_results, where=where)
    if not chunks:
        return {
            "answer": "No relevant documents found matching your filters. Try broadening the source selection or date range.",
            "sources": [],
            "chunks": [],
        }

    context = build_context(chunks)
    sources = sorted(set(c["source"] for c in chunks))

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Research context:\n\n{context}\n\n"
                    f"---\n\nQuestion: {question}"
                ),
            }
        ],
    )

    return {
        "answer": message.content[0].text,
        "sources": sources,
        "chunks": chunks,
    }
