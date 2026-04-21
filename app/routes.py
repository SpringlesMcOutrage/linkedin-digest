import hashlib
import hmac
import logging
from flask import Blueprint, request, jsonify, current_app
from .services.pipeline import run_daily_pipeline

logger = logging.getLogger(__name__)
bp = Blueprint("main", __name__)


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 signature sent by Salesforce Flow."""
    if not secret:
        return True  # skip verification if no secret configured (dev mode)
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@bp.route("/webhook/run-digest", methods=["POST"])
def run_digest():
    """
    Salesforce calls this endpoint (via Flow → HTTP Callout or Apex).
    Expected JSON body:
    {
        "signature": "<hmac_sha256_hex>",   // optional but recommended
        "nvidia_api_key": "...",             // can override env var
        "sf_access_token": "...",            // SF bearer token from the calling org
        "max_posts": 50                      // optional override
    }
    """
    payload = request.get_data()
    data = request.get_json(silent=True) or {}

    # Signature check
    sig = data.get("signature", "")
    secret = current_app.config["WEBHOOK_SECRET"]
    if not verify_webhook_signature(payload, sig, secret):
        logger.warning("Webhook: invalid signature")
        return jsonify({"error": "Unauthorized"}), 401

    # Allow Salesforce to pass its own access token so we don't need
    # a separate OAuth flow for the Salesforce write-back
    sf_access_token = data.get("sf_access_token")
    nvidia_key_override = data.get("nvidia_api_key")
    max_posts = data.get("max_posts", current_app.config["MAX_POSTS_PER_RUN"])

    logger.info("Webhook triggered — starting daily pipeline")

    try:
        result = run_daily_pipeline(
            sf_access_token=sf_access_token,
            nvidia_api_key_override=nvidia_key_override,
            max_posts=int(max_posts),
        )
        return jsonify({"status": "success", "summary": result}), 200
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        return jsonify({"status": "error", "detail": str(exc)}), 500


def register_routes(app):
    app.register_blueprint(bp)
