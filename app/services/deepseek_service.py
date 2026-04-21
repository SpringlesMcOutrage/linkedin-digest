"""
DeepSeek V3 via NVIDIA Build API.
Endpoint: https://integrate.api.nvidia.com/v1/chat/completions
"""

import json
import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)


DIGEST_SYSTEM_PROMPT = """You are a professional business intelligence analyst.
Your task is to analyze LinkedIn posts collected from a user's network and produce a structured daily digest.
Respond ONLY with valid JSON — no markdown fences, no preamble.

JSON schema:
{
  "date": "YYYY-MM-DD",
  "overview": "3-5 sentence summary of the day's main themes and activity",
  "top_topics": ["topic1", "topic2", "topic3"],
  "key_events": ["event1", "event2"],
  "post_summaries": [
    {
      "author": "Name",
      "company": "Company",
      "headline": "Author headline",
      "summary": "1-2 sentence summary of what the post says",
      "sentiment": "positive|neutral|negative",
      "relevance": "high|medium|low",
      "post_url": "https://..."
    }
  ],
  "full_text": "Full narrative digest in 3-5 paragraphs covering everything"
}
"""


class DeepSeekService:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "deepseek-ai/deepseek-v3",
        language: str = "Ukrainian",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language

    def generate_digest(self, posts: list[dict], run_date: str = None) -> dict:
        run_date = run_date or date.today().isoformat()

        if not posts:
            return {
                "date": run_date,
                "overview": "No posts collected today.",
                "top_topics": [],
                "key_events": [],
                "post_summaries": [],
                "full_text": "No LinkedIn activity found for today.",
            }

        user_prompt = self._build_user_prompt(posts, run_date)

        raw = self._call_api(user_prompt)
        return self._parse_response(raw, run_date)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_user_prompt(self, posts: list[dict], run_date: str) -> str:
        lines = [
            f"Today is {run_date}. Analyze the following {len(posts)} LinkedIn posts.",
            f"Write the digest in {self.language}.",
            "",
            "POSTS:",
        ]
        for i, p in enumerate(posts, 1):
            lines.append(
                f"\n--- Post {i} ---\n"
                f"Author: {p.get('author_name', 'Unknown')}\n"
                f"Headline: {p.get('author_headline', '')}\n"
                f"Company: {p.get('author_company', '')}\n"
                f"URL: {p.get('post_url', '')}\n"
                f"Reactions: {p.get('reactions_count', 0)} | "
                f"Comments: {p.get('comments_count', 0)}\n"
                f"Text:\n{p.get('post_text', '')}\n"
            )
        return "\n".join(lines)

    def _call_api(self, user_prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": DIGEST_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 4096,
            "temperature": 0.3,
        }

        logger.info("Calling DeepSeek API (%s) with %d chars prompt", self.model, len(user_prompt))
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]
        logger.info("DeepSeek response received (%d chars)", len(content))
        return content

    def _parse_response(self, raw: str, run_date: str) -> dict:
        # Strip any accidental markdown fences
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().rstrip("`").strip()

        try:
            result = json.loads(text)
            result.setdefault("date", run_date)
            return result
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse DeepSeek JSON response: %s", exc)
            return {
                "date": run_date,
                "overview": "AI digest generated but could not be parsed.",
                "top_topics": [],
                "key_events": [],
                "post_summaries": [],
                "full_text": raw,
                "parse_error": str(exc),
            }
