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
    cfg = current_app.config
    today = date.today().isoformat()
    logger.info("Pipeline started for %s", today)

    # ── 1. Scrape LinkedIn via RapidAPI ───────────────────────────────────────
    profiles_raw = cfg.get("LINKEDIN_PROFILES", "")
    profiles = [p.strip() for p in profiles_raw.split(",") if p.strip()]

    scraper = LinkedInScraper(
        apify_token=cfg.get("APIFY_TOKEN", ""),
        profiles=profiles,
    )
    posts = scraper.fetch_feed_posts(max_posts=max_posts)
    logger.info("Scraped %d posts", len(posts))

    if not posts:
        return {"date": today, "posts_found": 0, "digest": "No posts found today."}

    # ── 2. Salesforce sync ────────────────────────────────────────────────────
    sf = SalesforceService(
        instance_url=cfg.get("SF_INSTANCE_URL", ""),
        client_id=cfg.get("SF_CLIENT_ID", ""),
        client_secret=cfg.get("SF_CLIENT_SECRET", ""),
        username=cfg.get("SF_USERNAME", ""),
        password=cfg.get("SF_PASSWORD", ""),
        security_token=cfg.get("SF_SECURITY_TOKEN", ""),
        access_token_override=sf_access_token,
    )
    sf_results = sf.sync_posts(posts, run_date=today)
    logger.info("Salesforce sync done: %s", sf_results)

    # ── 3. DeepSeek AI digest ─────────────────────────────────────────────────
    ai = DeepSeekService(
        api_key=nvidia_api_key_override or cfg.get("NVIDIA_API_KEY", ""),
        base_url=cfg.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        model=cfg.get("DEEPSEEK_MODEL", "deepseek-ai/deepseek-v3"),
        language=cfg.get("DIGEST_LANGUAGE", "Ukrainian"),
    )
    digest = ai.generate_digest(posts, run_date=today)
    logger.info("Digest generated")

    return {
        "date": today,
        "posts_found": len(posts),
        "sf_synced": sf_results.get("synced", 0),
        "sf_errors": sf_results.get("errors", []),
        "digest": digest,
    }