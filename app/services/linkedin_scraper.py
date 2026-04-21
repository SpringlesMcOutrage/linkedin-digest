"""
LinkedIn Feed Scraper using linkedin-api (mobile API).
No browser needed — works from any IP including AWS.
"""

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from linkedin_api import Linkedin
    LINKEDIN_API_AVAILABLE = True
except ImportError:
    LINKEDIN_API_AVAILABLE = False
    logger.warning("linkedin-api not installed")


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
    def __init__(self, email: str, password: str, cookies_file: str = None):
        self.email = email
        self.password = password
        self._api = None

    def _get_api(self):
        if self._api is None:
            if not LINKEDIN_API_AVAILABLE:
                raise RuntimeError("linkedin-api not installed")
            logger.info("Authenticating with LinkedIn API...")
            self._api = Linkedin(self.email, self.password)
            logger.info("LinkedIn API authenticated successfully")
        return self._api

    def fetch_feed_posts(self, max_posts: int = 50) -> list[dict]:
        if not LINKEDIN_API_AVAILABLE:
            logger.warning("linkedin-api not available — returning empty list")
            return []

        try:
            api = self._get_api()
            posts = []
            seen_urls = set()

            logger.info("Fetching LinkedIn feed posts (max: %d)", max_posts)

            feed = api.get_feed_posts(limit=max_posts)

            for item in feed:
                if len(posts) >= max_posts:
                    break
                try:
                    post = self._parse_feed_item(item)
                    if post and post.post_url not in seen_urls:
                        seen_urls.add(post.post_url)
                        posts.append(post.to_dict())
                except Exception as exc:
                    logger.debug("Failed to parse feed item: %s", exc)
                    continue

            logger.info("Collected %d posts from LinkedIn feed", len(posts))
            return posts

        except Exception as exc:
            logger.error("LinkedIn API error: %s", exc)
            return []

    def _parse_feed_item(self, item: dict) -> Optional[LinkedInPost]:
        actor = item.get("actor", {})
        author_name = actor.get("name", {}).get("text", "Unknown")
        description = actor.get("description", {})
        author_headline = description.get("text", "") if description else ""
        author_company = _extract_company(author_headline)

        actor_urn = actor.get("urn", "")
        profile_id = ""
        for prefix in ("urn:li:member:", "urn:li:person:"):
            if prefix in actor_urn:
                profile_id = actor_urn.split(prefix)[-1]
                break
        author_profile_url = f"https://www.linkedin.com/in/{profile_id}" if profile_id else ""

        commentary = item.get("commentary", {})
        post_text = ""
        if commentary:
            text_obj = commentary.get("text", {})
            post_text = text_obj.get("text", "") if isinstance(text_obj, dict) else str(text_obj)

        if not post_text:
            return None

        entity_urn = item.get("entityUrn", "")
        post_url = f"https://www.linkedin.com/feed/update/{entity_urn}" if entity_urn else ""

        social = item.get("socialDetail", {})
        reactions_count = 0
        comments_count = 0
        if social:
            reactions_count = social.get("reactionSummary", {}).get("count", 0) or 0
            comments_count = (social.get("comments", {}).get("paging", {}) or {}).get("total", 0)

        sub_desc = actor.get("subDescription", {})
        timestamp_raw = sub_desc.get("text", "") if sub_desc else ""

        return LinkedInPost(
            author_name=author_name,
            author_headline=author_headline,
            author_profile_url=author_profile_url,
            author_company=author_company,
            post_text=post_text[:2000],
            post_url=post_url,
            reactions_count=reactions_count,
            comments_count=comments_count,
            timestamp_raw=timestamp_raw,
        )


def _extract_company(headline: str) -> str:
    for sep in (" at ", " @ ", " | ", " · "):
        if sep in headline:
            return headline.split(sep)[-1].strip()
    return ""