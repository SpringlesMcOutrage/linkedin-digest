"""
Salesforce REST API service.

For each LinkedIn post:
  1. Find or create a Contact/Lead by author name + company.
  2. Create a Task (activity) record linked to that Contact/Lead,
     storing the post URL, text snippet, and reaction counts.

Authentication:
  - If sf_access_token_override is provided (passed from Salesforce Flow),
    use it directly (no OAuth round-trip needed).
  - Otherwise, use Username-Password OAuth flow with the stored credentials.
"""

import logging
from datetime import date

import requests

logger = logging.getLogger(__name__)

SF_API_VERSION = "v59.0"


class SalesforceService:
    def __init__(
        self,
        instance_url: str,
        client_id: str,
        client_secret: str,
        username: str,
        password: str,
        security_token: str,
        access_token_override: str = None,
    ):
        self.instance_url = instance_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.username = username
        self.password = password
        self.security_token = security_token
        self._access_token = access_token_override

    # ── Public ────────────────────────────────────────────────────────────────

    def sync_posts(self, posts: list[dict], run_date: str = None) -> dict:
        run_date = run_date or date.today().isoformat()
        token = self._get_access_token()
        synced = 0
        errors = []

        for post in posts:
            try:
                self._upsert_post(post, token, run_date)
                synced += 1
            except Exception as exc:
                err_msg = f"{post.get('author_name')}: {exc}"
                logger.warning("SF sync error — %s", err_msg)
                errors.append(err_msg)

        return {"synced": synced, "errors": errors}

    # ── Auth ──────────────────────────────────────────────────────────────────

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        url = f"{self.instance_url}/services/oauth2/token"
        resp = requests.post(url, data={
            "grant_type": "password",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "username": self.username,
            "password": self.password + self.security_token,
        }, timeout=30)
        resp.raise_for_status()
        self._access_token = resp.json()["access_token"]
        logger.info("Salesforce OAuth token obtained")
        return self._access_token

    # ── Core sync logic ───────────────────────────────────────────────────────

    def _upsert_post(self, post: dict, token: str, run_date: str):
        """
        1. Find existing Contact by LinkedIn URL (custom field) or name.
        2. If not found, create a Lead.
        3. Create a Task linked to Contact or Lead.
        """
        author_name = post.get("author_name", "Unknown")
        profile_url = post.get("author_profile_url", "")
        company = post.get("author_company", "")

        # Try to find contact
        contact_id = self._find_contact(token, profile_url, author_name)

        if contact_id:
            who_id = contact_id
            who_type = "Contact"
        else:
            # Create or find a Lead
            lead_id = self._upsert_lead(token, post)
            who_id = lead_id
            who_type = "Lead"

        # Create Task (activity)
        self._create_task(token, who_id, who_type, post, run_date)

    def _find_contact(self, token: str, profile_url: str, name: str) -> str | None:
        """Query Contact by LinkedIn_Profile_URL__c or full name."""
        headers = self._headers(token)

        # First try by LinkedIn URL (custom field — create it in your SF org if needed)
        if profile_url:
            soql = (
                f"SELECT Id FROM Contact "
                f"WHERE LinkedIn_Profile_URL__c = '{_soql_escape(profile_url)}' "
                f"LIMIT 1"
            )
            result = self._query(token, soql)
            records = result.get("records", [])
            if records:
                return records[0]["Id"]

        # Fallback: search by name
        parts = name.split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else ""
        soql = (
            f"SELECT Id FROM Contact "
            f"WHERE FirstName = '{_soql_escape(first)}' "
            f"AND LastName = '{_soql_escape(last)}' "
            f"LIMIT 1"
        )
        result = self._query(token, soql)
        records = result.get("records", [])
        return records[0]["Id"] if records else None

    def _upsert_lead(self, token: str, post: dict) -> str:
        """Create a Lead if one doesn't already exist for this person."""
        author_name = post.get("author_name", "Unknown")
        profile_url = post.get("author_profile_url", "")
        company = post.get("author_company", "LinkedIn Network")
        headline = post.get("author_headline", "")

        # Check if Lead exists
        if profile_url:
            soql = (
                f"SELECT Id FROM Lead "
                f"WHERE LinkedIn_Profile_URL__c = '{_soql_escape(profile_url)}' "
                f"LIMIT 1"
            )
            result = self._query(token, soql)
            records = result.get("records", [])
            if records:
                return records[0]["Id"]

        # Create new Lead
        parts = author_name.split(" ", 1)
        first = parts[0]
        last = parts[1] if len(parts) > 1 else "."

        lead_data = {
            "FirstName": first,
            "LastName": last,
            "Company": company or "LinkedIn Network",
            "Title": headline[:80] if headline else "",
            "LeadSource": "LinkedIn",
            "Description": f"Auto-created from LinkedIn feed digest.",
        }
        if profile_url:
            lead_data["LinkedIn_Profile_URL__c"] = profile_url

        resp = self._post(token, "Lead", lead_data)
        lead_id = resp.get("id", "")
        logger.debug("Created Lead %s for %s", lead_id, author_name)
        return lead_id

    def _create_task(self, token: str, who_id: str, who_type: str, post: dict, run_date: str):
        """Create a Task (activity) for the LinkedIn post."""
        post_text = post.get("post_text", "")
        snippet = post_text[:200] + ("..." if len(post_text) > 200 else "")
        post_url = post.get("post_url", "")
        reactions = post.get("reactions_count", 0)
        comments = post.get("comments_count", 0)

        description = (
            f"LinkedIn post ({run_date})\n"
            f"URL: {post_url}\n"
            f"Reactions: {reactions} | Comments: {comments}\n\n"
            f"{snippet}"
        )

        task_data = {
            "Subject": f"LinkedIn post: {post.get('author_name', 'Unknown')} ({run_date})",
            "WhoId": who_id,
            "ActivityDate": run_date,
            "Status": "Completed",
            "TaskSubtype": "Call",  # closest standard value; customize as needed
            "Description": description,
            "Type": "LinkedIn",
        }

        self._post(token, "Task", task_data)

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _query(self, token: str, soql: str) -> dict:
        url = f"{self.instance_url}/services/data/{SF_API_VERSION}/query"
        resp = requests.get(url, headers=self._headers(token), params={"q": soql}, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, token: str, sobject: str, data: dict) -> dict:
        url = f"{self.instance_url}/services/data/{SF_API_VERSION}/sobjects/{sobject}/"
        resp = requests.post(url, headers=self._headers(token), json=data, timeout=30)
        resp.raise_for_status()
        return resp.json()


def _soql_escape(value: str) -> str:
    return value.replace("'", "\\'").replace("\\", "\\\\")
