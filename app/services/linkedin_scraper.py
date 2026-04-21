"""
LinkedIn scraper using LI Data Scraper API via RapidAPI.
Fetches recent posts from a list of LinkedIn profiles.
"""

import logging
import requests
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

RAPIDAPI_HOST = "li-data-scraper.p.rapidapi.com"


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
    def __init__(self, rapidapi_key: str, profiles: list[str], **kwargs):
        self.rapidapi_key = rapidapi_key
        self.profiles = [p.strip() for p in profiles if p.strip()]
        self.headers = {
            "x-rapidapi-host": RAPIDAPI_HOST,
            "x-rapidapi-key": rapidapi_key,
            "Content-Type": "application/json",
        }

    def fetch_feed_posts(self, max_posts: int = 50) -> list[dict]:
        if not self.profiles:
            logger.warning("No LinkedIn profiles configured in LINKEDIN_PROFILES")
            return []

        all_posts = []
        posts_per_profile = max(1, max_posts // len(self.profiles))

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
        url = f"https://{RAPIDAPI_HOST}/get-profile-post-and-comments"
        params = {
            "url": profile_url,
            "page": "1",
        }

        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        posts = []
        items = data if isinstance(data, list) else data.get("data", data.get("posts", []))

        for item in items[:limit]:
            try:
                post = self._parse_item(item, profile_url)
                if post:
                    posts.append(post)
            except Exception as exc:
                logger.debug("Failed to parse post item: %s", exc)

        return posts

    def _parse_item(self, item: dict, profile_url: str) -> Optional[LinkedInPost]:
        # Post text
        post_text = (
            item.get("text") or
            item.get("commentary") or
            item.get("description") or
            ""
        )
        if not post_text:
            return None

        # Author info
        author = item.get("author", item.get("actor", {}))
        if isinstance(author, dict):
            author_name = author.get("name") or author.get("fullName") or "Unknown"
            author_headline = author.get("headline") or author.get("occupation") or ""
            author_profile_url = author.get("url") or author.get("profileUrl") or profile_url
        else:
            author_name = "Unknown"
            author_headline = ""
            author_profile_url = profile_url

        author_company = _extract_company(author_headline)

        # Post URL
        post_url = (
            item.get("url") or
            item.get("postUrl") or
            item.get("shareUrl") or
            ""
        )

        # Engagement
        reactions_count = (
            item.get("totalReactionCount") or
            item.get("reactions") or
            item.get("likesCount") or
            0
        )
        comments_count = (
            item.get("commentsCount") or
            item.get("comments") or
            0
        )
        if isinstance(reactions_count, dict):
            reactions_count = reactions_count.get("count", 0)
        if isinstance(comments_count, dict):
            comments_count = comments_count.get("count", 0)

        # Timestamp
        timestamp_raw = (
            item.get("postedAt") or
            item.get("publishedAt") or
            item.get("createdAt") or
            ""
        )

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