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
