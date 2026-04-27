"""RAG helpers: HTML chunking + OpenAI embeddings.

Phase 3 uses this for the one-time ingest of stablebread.com.
Phase 4 will add a `retrieve_context()` function here for polish-time use.

Embedding model: text-embedding-3-large with dimensions=1536. 1536 keeps the
HNSW index working in pgvector (capped at 2000 dims), and per OpenAI's own
benchmarks, 3-large at reduced dims still beats 3-small at full dims.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx
import tiktoken
from bs4 import BeautifulSoup

from tweetgod.config import settings

log = logging.getLogger(__name__)

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"
EMBED_DIMS = 1536  # also matches the VECTOR(1536) column in rag_chunks

# tiktoken's cl100k_base encoding is what text-embedding-3-* uses.
_ENCODING = tiktoken.get_encoding("cl100k_base")

# Heading tags — we use them as natural section boundaries
_HEADING_TAGS = {"h2", "h3", "h4"}
# Block tags we extract as content
_CONTENT_TAGS = {"p", "ul", "ol", "blockquote", "pre", "table"}


@dataclass
class Chunk:
    ordinal: int
    content: str
    token_count: int


def count_tokens(text: str) -> int:
    return len(_ENCODING.encode(text))


def html_to_blocks(html: str) -> list[tuple[str, str]]:
    """Parse WP post HTML into a list of (kind, text) blocks.

    Kind is 'h2'/'h3'/'h4' for headings, or 'body' for content blocks.
    Headings act as section boundaries during chunking.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Strip non-content elements
    for tag in soup(["script", "style", "img", "figure", "iframe", "noscript"]):
        tag.decompose()

    blocks: list[tuple[str, str]] = []
    for el in soup.find_all(_HEADING_TAGS | _CONTENT_TAGS):
        text = el.get_text(separator=" ", strip=True)
        if not text:
            continue
        # Collapse whitespace
        text = " ".join(text.split())
        if el.name in _HEADING_TAGS:
            blocks.append((el.name, text))
        else:
            blocks.append(("body", text))

    return blocks


def chunk_blocks(
    blocks: list[tuple[str, str]],
    max_tokens: int = 500,
    overlap_tokens: int = 100,
) -> list[Chunk]:
    """Combine blocks into chunks of ~max_tokens.

    Strategy:
    - Headings reset the section context. Their text gets prepended to every
      chunk in that section (so retrieval surfaces "what part of the article
      this is from").
    - Body blocks get greedily combined up to max_tokens.
    - A single body block exceeding max_tokens gets hard-split with overlap.
    """
    chunks: list[Chunk] = []
    current_h2 = ""
    current_h3 = ""
    buffer: list[str] = []
    buffer_tokens = 0

    def flush() -> None:
        nonlocal buffer, buffer_tokens
        if not buffer:
            return
        prefix_parts = [p for p in (current_h2, current_h3) if p]
        prefix = " > ".join(prefix_parts)
        body = "\n\n".join(buffer)
        content = f"[{prefix}]\n{body}" if prefix else body
        chunks.append(
            Chunk(
                ordinal=len(chunks),
                content=content,
                token_count=count_tokens(content),
            )
        )
        buffer = []
        buffer_tokens = 0

    for kind, text in blocks:
        if kind == "h2":
            flush()
            current_h2 = text
            current_h3 = ""
            continue
        if kind in ("h3", "h4"):
            flush()
            current_h3 = text
            continue

        block_tokens = count_tokens(text)

        # Hard-split a single oversize block
        if block_tokens > max_tokens:
            flush()
            tokens = _ENCODING.encode(text)
            step = max_tokens - overlap_tokens
            for start in range(0, len(tokens), step):
                slice_text = _ENCODING.decode(tokens[start : start + max_tokens])
                buffer.append(slice_text)
                buffer_tokens = count_tokens(slice_text)
                flush()
            continue

        # Otherwise greedily combine
        if buffer_tokens + block_tokens > max_tokens and buffer:
            flush()
        buffer.append(text)
        buffer_tokens += block_tokens

    flush()
    return chunks


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts via OpenAI. Returns one vector per input."""
    if not texts:
        return []
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    payload = {
        "model": settings.openai_embed_model,
        "input": texts,
        "dimensions": EMBED_DIMS,
    }
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=60) as client:
        resp = client.post(OPENAI_EMBED_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            log.error(
                "OpenAI embed failed: %s — %s",
                resp.status_code,
                resp.text[:500],
            )
            resp.raise_for_status()
        data = resp.json()

    vectors = [item["embedding"] for item in data["data"]]
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"OpenAI returned {len(vectors)} vectors for {len(texts)} inputs"
        )
    return vectors


def retrieve_context(
    query: str,
    k: int | None = None,
    threshold: float | None = None,
) -> list[dict]:
    """Embed a query, find the top-K most similar chunks via the match_chunks RPC.

    Returns a list of dicts (one per chunk) with these keys:
      chunk_id, article_id, content, ordinal, similarity,
      article_title, article_url, featured_image_url

    Returns [] if RAG isn't configured or the query is empty.
    """
    if not query or not query.strip():
        return []
    if not settings.openai_api_key or not settings.supabase_url:
        log.warning("retrieve_context called but OpenAI/Supabase not configured")
        return []

    k = k if k is not None else settings.rag_top_k
    threshold = threshold if threshold is not None else settings.rag_similarity_threshold

    try:
        vectors = embed_texts([query])
    except Exception:
        log.error("Failed to embed RAG query", exc_info=True)
        return []
    if not vectors:
        return []

    # Lazy import to avoid circular deps with dedup.py
    from tweetgod.dedup import _get_client
    supabase = _get_client()

    try:
        resp = supabase.rpc(
            "match_chunks",
            {
                "query_embedding": vectors[0],
                "match_threshold": threshold,
                "match_count": k,
            },
        ).execute()
    except Exception:
        log.error("match_chunks RPC failed", exc_info=True)
        return []

    return resp.data or []


def format_excerpts(chunks: list[dict]) -> str:
    """Format retrieved chunks into a string block for prompt injection."""
    if not chunks:
        return ""
    parts = []
    for c in chunks:
        title = c.get("article_title", "")
        url = c.get("article_url", "")
        content = c.get("content", "")
        parts.append(f"[Article: \"{title}\" — {url}]\n{content}")
    return "\n\n".join(parts)


# CLI test mode: `python -m tweetgod.rag "DCF discount rate"`
# Lets you eyeball retrieval quality before turning RAG_ENABLED on.
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m tweetgod.rag <query>", file=sys.stderr)
        sys.exit(1)

    q = " ".join(sys.argv[1:])
    print(f"Query: {q!r}\n")
    results = retrieve_context(q)
    if not results:
        print("No matching chunks found.")
        sys.exit(0)

    print(f"Top {len(results)} chunks:\n")
    for r in results:
        sim = r.get("similarity", 0.0)
        title = r.get("article_title", "")
        url = r.get("article_url", "")
        content = r.get("content", "")
        preview = content[:300].replace("\n", " ")
        print(f"--- similarity={sim:.3f} | {title}")
        print(f"    {url}")
        print(f"    {preview}{'...' if len(content) > 300 else ''}")
        print()
