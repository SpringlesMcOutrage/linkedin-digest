"""
LinkedIn scraper using Apify - Profile Posts Scraper (apimaestro/linkedin-profile-posts).
No cookies, no login needed.
"""

import logging
import time
import requests
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

APIFY_BASE = "https://api.apify.com/v2"
ACTOR_ID = "apimaestro~linkedin-profile-posts"


@dataclass
class LinkedInPost:
    author_name: str
    author_headline: str
    author_profile_url: str
    author_company: str
    post_text: str
    post_url: str
    reactions_count: int
    comments_count: int
    timestamp_raw: str
    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class LinkedInScraper:
    def __init__(self, apify_token: str, profiles: list[str], **kwargs):
        self.apify_token = apify_token
        self.profiles = [p.strip() for p in profiles if p.strip()]

    def fetch_feed_posts(self, max_posts: int = 50) -> list[dict]:
        if not self.profiles:
            logger.warning("No LinkedIn profiles configured")
            return []

        all_posts = []
        posts_per_profile = max(5, max_posts // len(self.profiles))

        for profile_url in self.profiles:
            if len(all_posts) >= max_posts:
                break
            try:
                posts = self._fetch_profile_posts(profile_url, limit=posts_per_profile)
                all_posts.extend(posts)
                logger.info("Fetched %d posts from %s", len(posts), profile_url)
            except Exception as exc:
                logger.error("Failed to fetch posts from %s: %s", profile_url, exc)

        logger.info("Total posts collected: %d", len(all_posts))
        return [p.to_dict() for p in all_posts[:max_posts]]

    def _fetch_profile_posts(self, profile_url: str, limit: int = 10) -> list[LinkedInPost]:
        # Start actor run
        run_url = f"{APIFY_BASE}/acts/{ACTOR_ID}/runs"
        payload = {
            "profileUrl": profile_url,
            "resultLimit": limit,
        }
        resp = requests.post(
            run_url,
            json=payload,
            params={"token": self.apify_token},
            timeout=30,
        )
        resp.raise_for_status()
        run_id = resp.json()["data"]["id"]
        logger.info("Apify run started: %s", run_id)

        # Wait for run to finish (poll every 5s, max 120s)
        for _ in range(24):
            time.sleep(5)
            status_resp = requests.get(
                f"{APIFY_BASE}/actor-runs/{run_id}",
                params={"token": self.apify_token},
                timeout=15,
            )
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                logger.error("Apify run %s failed with status: %s", run_id, status)
                return []

        # Get results
        dataset_id = status_resp.json()["data"]["defaultDatasetId"]
        items_resp = requests.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            params={"token": self.apify_token, "format": "json"},
            timeout=30,
        )
        items_resp.raise_for_status()
        items = items_resp.json()

        posts = []
        for item in items[:limit]:
            try:
                post = self._parse_item(item, profile_url)
                if post:
                    posts.append(post)
            except Exception as exc:
                logger.debug("Failed to parse item: %s", exc)

        return posts

    def _parse_item(self, item: dict, profile_url: str) -> Optional[LinkedInPost]:
        post_text = (
            item.get("text") or
            item.get("content") or
            item.get("postText") or
            ""
        )
        if not post_text:
            return None

        author = item.get("author", {})
        author_name = author.get("name") or author.get("fullName") or "Unknown"
        author_headline = author.get("headline") or author.get("occupation") or ""
        author_profile_url = author.get("profileUrl") or author.get("url") or profile_url
        author_company = _extract_company(author_headline)

        post_url = item.get("url") or item.get("postUrl") or item.get("shareUrl") or ""

        reactions_count = item.get("totalReactionCount") or item.get("likesCount") or 0
        comments_count = item.get("commentsCount") or item.get("comments") or 0

        if isinstance(reactions_count, dict):
            reactions_count = reactions_count.get("count", 0)
        if isinstance(comments_count, dict):
            comments_count = comments_count.get("count", 0)

        timestamp_raw = item.get("postedAt") or item.get("publishedAt") or ""

        return LinkedInPost(
            author_name=str(author_name),
            author_headline=str(author_headline),
            author_profile_url=str(author_profile_url),
            author_company=str(author_company),
            post_text=str(post_text)[:2000],
            post_url=str(post_url),
            reactions_count=int(reactions_count) if reactions_count else 0,
            comments_count=int(comments_count) if comments_count else 0,
            timestamp_raw=str(timestamp_raw),
        )


def _extract_company(headline: str) -> str:
    for sep in (" at ", " @ ", " | ", " · "):
        if sep in headline:
            return headline.split(sep)[-1].strip()
    return ""