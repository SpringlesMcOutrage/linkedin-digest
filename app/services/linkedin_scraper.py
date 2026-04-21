"""
LinkedIn Feed Scraper using Playwright (headless Chromium).

Strategy:
- First run: logs in with email/password, saves cookies to file.
- Subsequent runs: loads cookies (much faster, avoids login rate limits).
- Scrolls through /feed, extracts posts from followed connections.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.warning("playwright not installed — scraper will return mock data")


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
    FEED_URL = "https://www.linkedin.com/feed/"
    LOGIN_URL = "https://www.linkedin.com/login"

    def __init__(self, email: str, password: str, cookies_file: str = "linkedin_cookies.json"):
        self.email = email
        self.password = password
        self.cookies_file = Path(cookies_file)

    # ── Public ────────────────────────────────────────────────────────────────

    def fetch_feed_posts(self, max_posts: int = 50) -> list[dict]:
        if not PLAYWRIGHT_AVAILABLE:
            logger.warning("Playwright not available — returning empty list")
            return []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
            )

            # Load saved cookies if available
            if self.cookies_file.exists():
                with open(self.cookies_file) as f:
                    context.add_cookies(json.load(f))

            page = context.new_page()

            try:
                page.goto(self.FEED_URL, wait_until="domcontentloaded", timeout=30_000)

                # Check if we're logged in
                if "login" in page.url or "checkpoint" in page.url:
                    logger.info("Not logged in — performing login")
                    self._login(page)
                    self._save_cookies(context)

                posts = self._scrape_feed(page, max_posts)
                return [p.to_dict() for p in posts]

            except PWTimeout as e:
                logger.error("Playwright timeout: %s", e)
                return []
            finally:
                browser.close()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _login(self, page):
        page.goto(self.LOGIN_URL, wait_until="domcontentloaded")
        page.fill("#username", self.email)
        page.fill("#password", self.password)
        page.click('[type="submit"]')
        page.wait_for_url("**/feed/**", timeout=20_000)
        logger.info("LinkedIn login successful")

    def _save_cookies(self, context):
        cookies = context.cookies()
        with open(self.cookies_file, "w") as f:
            json.dump(cookies, f)
        logger.info("Cookies saved to %s", self.cookies_file)

    def _scrape_feed(self, page, max_posts: int) -> list[LinkedInPost]:
        posts: list[LinkedInPost] = []
        seen_urls: set[str] = set()
        scroll_attempts = 0
        max_scrolls = max_posts // 3 + 10  # rough estimate

        logger.info("Scrolling feed to collect up to %d posts", max_posts)

        while len(posts) < max_posts and scroll_attempts < max_scrolls:
            # Wait for feed items to render
            try:
                page.wait_for_selector(
                    "div.feed-shared-update-v2",
                    timeout=8_000,
                    state="attached",
                )
            except PWTimeout:
                break

            cards = page.query_selector_all("div.feed-shared-update-v2")

            for card in cards:
                if len(posts) >= max_posts:
                    break
                try:
                    post = self._parse_card(page, card)
                    if post and post.post_url not in seen_urls:
                        seen_urls.add(post.post_url)
                        posts.append(post)
                except Exception as exc:
                    logger.debug("Failed to parse card: %s", exc)

            # Scroll down
            page.evaluate("window.scrollBy(0, 1200)")
            time.sleep(1.5)
            scroll_attempts += 1

        logger.info("Collected %d unique posts after %d scrolls", len(posts), scroll_attempts)
        return posts

    def _parse_card(self, page, card) -> Optional[LinkedInPost]:
        # Author name
        author_el = card.query_selector(
            ".update-components-actor__name span[aria-hidden='true']"
        )
        author_name = author_el.inner_text().strip() if author_el else "Unknown"

        # Author headline
        headline_el = card.query_selector(".update-components-actor__description span[aria-hidden='true']")
        author_headline = headline_el.inner_text().strip() if headline_el else ""

        # Author profile URL
        profile_el = card.query_selector(".update-components-actor__meta a")
        author_profile_url = ""
        if profile_el:
            href = profile_el.get_attribute("href") or ""
            author_profile_url = href.split("?")[0]  # strip tracking params

        # Company (last part of headline often has company)
        author_company = _extract_company(author_headline)

        # Post text
        text_el = card.query_selector(".feed-shared-update-v2__description")
        post_text = text_el.inner_text().strip() if text_el else ""
        if not post_text:
            return None  # skip reposts with no text

        # Post URL (permalink)
        post_url = ""
        link_el = card.query_selector("a.app-aware-link[href*='/posts/']")
        if link_el:
            href = link_el.get_attribute("href") or ""
            post_url = href.split("?")[0]

        # Reactions
        reactions_el = card.query_selector(".social-details-social-counts__reactions-count")
        reactions_count = _parse_count(reactions_el.inner_text() if reactions_el else "0")

        # Comments
        comments_el = card.query_selector(".social-details-social-counts__comments")
        comments_count = _parse_count(comments_el.inner_text() if comments_el else "0")

        # Timestamp
        time_el = card.query_selector(".update-components-actor__sub-description span[aria-hidden='true']")
        timestamp_raw = time_el.inner_text().strip() if time_el else ""

        return LinkedInPost(
            author_name=author_name,
            author_headline=author_headline,
            author_profile_url=author_profile_url,
            author_company=author_company,
            post_text=post_text[:2000],  # truncate very long posts
            post_url=post_url,
            reactions_count=reactions_count,
            comments_count=comments_count,
            timestamp_raw=timestamp_raw,
        )


# ── Utilities ─────────────────────────────────────────────────────────────────

def _parse_count(text: str) -> int:
    text = text.strip().lower().replace(",", "")
    if "k" in text:
        return int(float(text.replace("k", "")) * 1000)
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else 0


def _extract_company(headline: str) -> str:
    """Best-effort: 'Senior Dev at Acme Corp' → 'Acme Corp'"""
    for sep in (" at ", " @ ", " | ", " · "):
        if sep in headline:
            return headline.split(sep)[-1].strip()
    return ""
