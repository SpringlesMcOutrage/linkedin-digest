import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

    # Salesforce webhook auth
    WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

    # LinkedIn credentials (for Playwright login)
    LINKEDIN_EMAIL = os.environ.get("LINKEDIN_EMAIL", "")
    LINKEDIN_PASSWORD = os.environ.get("LINKEDIN_PASSWORD", "")
    LINKEDIN_COOKIES_FILE = os.environ.get("LINKEDIN_COOKIES_FILE", "linkedin_cookies.json")

    # NVIDIA / DeepSeek
    NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
    NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
    DEEPSEEK_MODEL = "deepseek-ai/deepseek-v3"

    # Salesforce
    SF_INSTANCE_URL = os.environ.get("SF_INSTANCE_URL", "")   # e.g. https://yourorg.my.salesforce.com
    SF_CLIENT_ID = os.environ.get("SF_CLIENT_ID", "")
    SF_CLIENT_SECRET = os.environ.get("SF_CLIENT_SECRET", "")
    SF_USERNAME = os.environ.get("SF_USERNAME", "")
    SF_PASSWORD = os.environ.get("SF_PASSWORD", "")
    SF_SECURITY_TOKEN = os.environ.get("SF_SECURITY_TOKEN", "")

    # Digest settings
    MAX_POSTS_PER_RUN = int(os.environ.get("MAX_POSTS_PER_RUN", "50"))
    DIGEST_LANGUAGE = os.environ.get("DIGEST_LANGUAGE", "Ukrainian")
