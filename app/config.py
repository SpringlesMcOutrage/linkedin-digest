import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

    # RapidAPI / LI Data Scraper
    RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
    LINKEDIN_PROFILES = os.environ.get("LINKEDIN_PROFILES", "")

    # NVIDIA / DeepSeek
    NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEEPSEEK_MODEL = "deepseek-ai/deepseek-v3"

    # Salesforce
    SF_INSTANCE_URL = os.environ.get("SF_INSTANCE_URL", "")
    SF_CLIENT_ID = os.environ.get("SF_CLIENT_ID", "")
    SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET", "")
    SF_USERNAME = os.environ.get("SF_USERNAME", "")
    SF_PASSWORD = os.environ.get("SF_PASSWORD", "")
    SF_SECURITY_TOKEN = os.environ.get("SF_SECURITY_TOKEN", "")

    # Pipeline
    MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "50"))
    DIGEST_LANGUAGE = os.environ.get("DIGEST_LANGUAGE", "Ukrainian")