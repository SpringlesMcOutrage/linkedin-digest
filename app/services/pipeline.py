import logging
from datetime import date
from flask import current_app
from .linkedin_scraper import LinkedInScraper
from .deepseek_service import DeepSeekService
from .salesforce_service import SalesforceService

logger = logging.getLogger(__name__)


def run_daily_pipeline(
    sf_access_token: str = None,
    nvidia_api_key_override: str = None,
    max_posts: int = 50,
) -> dict:
    """
    Full daily pipeline:
    1. Scrape LinkedIn feed posts from followed people
    2. Push basic contact/activity data to Salesforce
    3. Send all posts to DeepSeek for AI digest generation
    4. Return structured digest
    """
    cfg = current_app.config
    today = date.today().isoformat()
    logger.info("Pipeline started for %s", today)

    # ── 1. Scrape LinkedIn ────────────────────────────────────────────────────
    scraper = LinkedInScraper(
        email=cfg["LINKEDIN_EMAIL"],
        password=cfg["LINKEDIN_PASSWORD"],
        cookies_file=cfg["LINKEDIN_COOKIES_FILE"],
    )
    posts = scraper.fetch_feed_posts(max_posts=max_posts)
    logger.info("Scraped %d posts", len(posts))

    if not posts:
        return {"date": today, "posts_found": 0, "digest": "No posts found today."}

    # ── 2. Salesforce sync ────────────────────────────────────────────────────
    sf = SalesforceService(
        instance_url=cfg["SF_INSTANCE_URL"],
        client_id=cfg["SF_CLIENT_ID"],
        client_secret=cfg["SF_CLIENT_SECRET"],
        username=cfg["SF_USERNAME"],
        password=cfg["SF_PASSWORD"],
        security_token=cfg["SF_SECURITY_TOKEN"],
        access_token_override=sf_access_token,
    )
    sf_results = sf.sync_posts(posts, run_date=today)
    logger.info("Salesforce sync done: %s", sf_results)

    # ── 3. DeepSeek AI digest ─────────────────────────────────────────────────
    ai = DeepSeekService(
        api_key=nvidia_api_key_override or cfg["NVIDIA_API_KEY"],
        base_url=cfg["NVIDIA_BASE_URL"],
        model=cfg["DEEPSEEK_MODEL"],
        language=cfg["DIGEST_LANGUAGE"],
    )
    digest = ai.generate_digest(posts, run_date=today)
    logger.info("Digest generated (%d chars)", len(digest.get("full_text", "")))

    return {
        "date": today,
        "posts_found": len(posts),
        "sf_synced": sf_results.get("synced", 0),
        "sf_errors": sf_results.get("errors", []),
        "digest": digest,
    }
