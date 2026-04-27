"""Ingest stablebread.com published posts into the RAG store.

Run from the venv:
    python -m tweetgod.ingest

Idempotent — posts whose WP `modified` timestamp matches the row already in
`rag_articles` are skipped. Re-run anytime; only new/changed articles get
re-embedded.

Pulls only published posts (status=publish, the WP REST default for
unauthenticated requests). Skips pages, drafts, private posts, etc.
"""

from __future__ import annotations

import logging
import sys
import time

import httpx

from tweetgod.config import settings
from tweetgod.dedup import _get_client as get_supabase
from tweetgod.rag import chunk_blocks, embed_texts, html_to_blocks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("tweetgod.ingest")

WP_BASE = "https://stablebread.com/wp-json/wp/v2"
EMBED_BATCH = 100  # chunks per OpenAI embeddings call
INSERT_BATCH = 50  # chunks per Supabase insert


def fetch_all_posts() -> list[dict]:
    """Pull every published post (paginated)."""
    posts: list[dict] = []
    page = 1
    fields = "id,slug,title,content,modified,featured_media,link"

    with httpx.Client(timeout=30) as client:
        while True:
            resp = client.get(
                f"{WP_BASE}/posts",
                params={
                    "status": "publish",
                    "per_page": 100,
                    "page": page,
                    "_fields": fields,
                },
            )
            # WP returns 400 with code "rest_post_invalid_page_number" past the end
            if resp.status_code == 400:
                break
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            posts.extend(batch)
            log.info(
                "Fetched page %d (%d posts, %d total so far)",
                page,
                len(batch),
                len(posts),
            )
            page += 1

    return posts


def fetch_featured_image(media_id: int) -> str | None:
    if not media_id:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{WP_BASE}/media/{media_id}",
                params={"_fields": "source_url"},
            )
            resp.raise_for_status()
            return resp.json().get("source_url")
    except Exception:
        log.warning("Failed to fetch featured image %s", media_id, exc_info=True)
        return None


def _strip_title_html(title_html: str) -> str:
    """WordPress titles often contain HTML entities — clean them up."""
    from bs4 import BeautifulSoup
    return BeautifulSoup(title_html, "html.parser").get_text(strip=True)


def ingest_post(post: dict, supabase) -> dict:
    """Ingest a single post. Returns a stats dict."""
    post_id: int = post["id"]
    slug: str = post["slug"]
    title: str = _strip_title_html(post["title"]["rendered"])
    url: str = post["link"]
    modified: str = post["modified"]  # ISO, no timezone (WP convention)
    content_html: str = post["content"]["rendered"]
    featured_media_id: int = post.get("featured_media") or 0

    # Skip if unchanged since last ingest
    existing = (
        supabase.table("rag_articles")
        .select("modified_at")
        .eq("id", post_id)
        .execute()
        .data
    )
    if existing:
        prior = existing[0]["modified_at"] or ""
        # Compare to second-precision (strip TZ suffix on ours)
        if prior[:19] == modified[:19]:
            log.info("[%s] %s — unchanged, skip", post_id, slug)
            return {"status": "skipped"}

    # Chunk
    blocks = html_to_blocks(content_html)
    chunks = chunk_blocks(blocks)
    if not chunks:
        log.warning("[%s] %s — no extractable content, skip", post_id, slug)
        return {"status": "empty"}

    # Embed in batches
    vectors: list[list[float]] = []
    for i in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[i : i + EMBED_BATCH]
        vectors.extend(embed_texts([c.content for c in batch]))

    # Featured image
    featured_image_url = fetch_featured_image(featured_media_id)

    # Upsert article
    supabase.table("rag_articles").upsert(
        {
            "id": post_id,
            "slug": slug,
            "title": title,
            "url": url,
            "featured_image_url": featured_image_url,
            "modified_at": modified + "Z",
        }
    ).execute()

    # Replace chunks (delete + insert is simplest given UNIQUE(article_id, ordinal))
    supabase.table("rag_chunks").delete().eq("article_id", post_id).execute()
    rows = [
        {
            "article_id": post_id,
            "ordinal": chunks[i].ordinal,
            "content": chunks[i].content,
            "token_count": chunks[i].token_count,
            "embedding": vectors[i],
        }
        for i in range(len(chunks))
    ]
    for i in range(0, len(rows), INSERT_BATCH):
        supabase.table("rag_chunks").insert(rows[i : i + INSERT_BATCH]).execute()

    total_tokens = sum(c.token_count for c in chunks)
    log.info(
        "[%s] %s — %d chunks, %d tokens",
        post_id,
        slug,
        len(chunks),
        total_tokens,
    )
    return {"status": "ingested", "chunks": len(chunks), "tokens": total_tokens}


def main() -> None:
    if not settings.openai_api_key:
        log.error("OPENAI_API_KEY not set in .env — aborting")
        sys.exit(1)
    if not settings.supabase_url or not settings.supabase_key:
        log.error("Supabase env not set — aborting")
        sys.exit(1)

    log.info("Embedding model: %s @ 1536 dims", settings.openai_embed_model)
    log.info("Fetching all published posts from %s", WP_BASE)
    posts = fetch_all_posts()
    log.info("Got %d posts", len(posts))

    supabase = get_supabase()

    stats = {
        "ingested": 0,
        "skipped": 0,
        "empty": 0,
        "errors": 0,
        "chunks": 0,
        "tokens": 0,
    }
    started = time.monotonic()

    for i, post in enumerate(posts, 1):
        try:
            result = ingest_post(post, supabase)
            stats[result["status"]] += 1
            stats["chunks"] += result.get("chunks", 0)
            stats["tokens"] += result.get("tokens", 0)
        except Exception:
            log.error("Ingest failed for post %s", post.get("id"), exc_info=True)
            stats["errors"] += 1

        if i % 10 == 0:
            elapsed = time.monotonic() - started
            log.info(
                "Progress: %d/%d posts — %.1fs elapsed",
                i,
                len(posts),
                elapsed,
            )

    elapsed = time.monotonic() - started
    log.info(
        "Done in %.1fs — ingested=%d skipped=%d empty=%d errors=%d "
        "chunks=%d tokens=%d",
        elapsed,
        stats["ingested"],
        stats["skipped"],
        stats["empty"],
        stats["errors"],
        stats["chunks"],
        stats["tokens"],
    )


if __name__ == "__main__":
    main()
