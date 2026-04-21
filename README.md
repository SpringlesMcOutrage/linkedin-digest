# LinkedIn Daily Digest

> Automatically scrape your LinkedIn feed every day, sync contacts to Salesforce, and generate an AI-powered digest using DeepSeek V3 via NVIDIA's API — all triggered by a Salesforce Scheduled Flow.

```
Salesforce Scheduled Flow (10 PM daily)
             │
             │  POST /webhook/run-digest
             ▼
     ┌───────────────────┐
     │   Flask API       │  ← runs on your EC2
     └───────┬───────────┘
             │
    ┌────────┼────────────┐
    ▼        ▼            ▼
LinkedIn  Salesforce   NVIDIA
Scraper   REST API     DeepSeek V3
(Posts)  (Contacts,   (AI Digest)
          Tasks)
```

---

## Features

- **LinkedIn feed scraping** — collects posts from everyone you follow using Playwright (headless Chromium); saves session cookies so it never re-logs in
- **Salesforce sync** — for each post, finds or creates a Contact / Lead and logs a Task with the post URL, snippet, and engagement counts
- **AI digest** — sends all posts to DeepSeek V3 (via NVIDIA Build API) and returns a structured JSON summary: overview, top topics, key events, per-post summaries, full narrative
- **Webhook API** — single `POST /webhook/run-digest` endpoint; Salesforce Flow calls it daily and passes its own session token, so no extra OAuth config is needed
- **HMAC signature verification** — optional shared secret between Salesforce and the API

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | Python 3.12, Flask, Gunicorn |
| Scraping | Playwright (headless Chromium) |
| AI | DeepSeek V3 via NVIDIA Build API |
| CRM | Salesforce REST API v59 |
| Infrastructure | Docker, AWS EC2 |
| Scheduler | Salesforce Scheduled Flow |

---

## Project Structure

```
linkedin-digest/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # All config from environment variables
│   ├── routes.py                # Webhook endpoint + signature verification
│   └── services/
│       ├── pipeline.py          # Orchestrator — calls all three services
│       ├── linkedin_scraper.py  # Playwright-based LinkedIn feed scraper
│       ├── deepseek_service.py  # NVIDIA / DeepSeek V3 API client
│       └── salesforce_service.py# Salesforce OAuth + REST API client
├── wsgi.py                      # Gunicorn entry point
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env.example                 # Copy to .env and fill in your credentials
```

---

## Deployment Guide

### Prerequisites

- AWS EC2 instance (Ubuntu 22.04, `t3.small` or larger)
- Port `5000` open in the EC2 Security Group (inbound TCP)
- A LinkedIn account
- NVIDIA Build API key — [get one here](https://build.nvidia.com/)
- Salesforce org with API access

---

### Step 1 — Prepare the EC2 instance

SSH into your instance, then install Docker:

```bash
sudo apt update && sudo apt install -y git docker.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

---

### Step 2 — Clone the repository

```bash
git clone https://github.com/SpringlesMcOutrage/linkedin-digest.git
cd linkedin-digest
```

---

### Step 3 — Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in every value:

| Variable | Where to get it |
|---|---|
| `SECRET_KEY` | Any random string — run `openssl rand -hex 32` |
| `WEBHOOK_SECRET` | Any random string — must match what you put in the Salesforce Flow body |
| `LINKEDIN_EMAIL` | Your LinkedIn login email |
| `LINKEDIN_PASSWORD` | Your LinkedIn password |
| `NVIDIA_API_KEY` | [build.nvidia.com](https://build.nvidia.com/) → Get API Key |
| `SF_INSTANCE_URL` | e.g. `https://yourorg.my.salesforce.com` |
| `SF_CLIENT_ID` | Salesforce → Setup → App Manager → Connected App → Consumer Key |
| `SF_CLIENT_SECRET` | Same Connected App → Consumer Secret |
| `SF_USERNAME` | Salesforce API user email |
| `SF_PASSWORD` | Salesforce API user password |
| `SF_SECURITY_TOKEN` | Salesforce → Settings → Reset My Security Token |

Save with `Ctrl+O`, exit with `Ctrl+X`.

---

### Step 4 — Start the container

```bash
mkdir -p data
docker compose up -d --build
```

Verify it's running:

```bash
docker compose logs -f
# You should see: Listening at: http://0.0.0.0:5000

curl http://localhost:5000/health
# → {"status": "ok"}
```

---

### Step 5 — Test the full pipeline

Trigger a manual run to confirm LinkedIn login works and the pipeline is wired up correctly:

```bash
curl -X POST http://YOUR_EC2_IP:5000/webhook/run-digest \
  -H "Content-Type: application/json" \
  -d '{
    "nvidia_api_key": "nvapi-YOUR_KEY",
    "signature": "YOUR_WEBHOOK_SECRET",
    "max_posts": 10
  }'
```

You should get back `"status": "success"` with a populated `digest` object. Playwright will log in to LinkedIn, save cookies to `data/linkedin_cookies.json`, and all future runs will reuse the session.

---

### Step 6 — Salesforce setup

#### 6a. Custom field on Contact and Lead

Add `LinkedIn_Profile_URL__c` (Text, 255) to both objects so the API can match post authors to existing records:

```
Setup → Object Manager → Contact → Fields & Relationships → New
  Field Type:  Text
  Length:      255
  Field Label: LinkedIn Profile URL
  Field Name:  LinkedIn_Profile_URL__c
```

Repeat the exact same steps for **Lead**.

---

#### 6b. Connected App

```
Setup → App Manager → New Connected App
  ✓ Enable OAuth Settings
  Callback URL: https://login.salesforce.com/services/oauth2/success
  Scopes:
    - Access and manage your data (api)
    - Perform requests at any time (refresh_token, offline_access)
```

Copy the **Consumer Key** → `SF_CLIENT_ID` and **Consumer Secret** → `SF_CLIENT_SECRET` into your `.env`.

---

#### 6c. Remote Site Setting

```
Setup → Security → Remote Site Settings → New Remote Site
  Name: LinkedInDigest
  URL:  http://YOUR_EC2_IP:5000
  ✓ Active
```

---

#### 6d. Named Credential

```
Setup → Security → Named Credentials → New
  Label:    LinkedIn Digest API
  Name:     LinkedIn_Digest_API
  URL:      http://YOUR_EC2_IP:5000
  Identity Type: Named Principal
  Auth Protocol: No Authentication
  ✓ Allow Merge Fields in HTTP Body
```

---

#### 6e. Scheduled Flow

```
Setup → Flows → New Flow → Scheduled-Triggered Flow
```

**Schedule:** Frequency `Daily`, Time `22:00` (your timezone).

Add these elements to the Flow canvas:

**Element 1 — HTTP Callout action**

```
Method:  POST
URL:     {!$Credential.LinkedIn_Digest_API}/webhook/run-digest
Headers: Content-Type: application/json
Body:
{
  "nvidia_api_key":  "nvapi-YOUR_KEY_HERE",
  "sf_access_token": "{!$Api.Session_ID}",
  "max_posts":       50,
  "signature":       "YOUR_WEBHOOK_SECRET"
}
```

> `{!$Api.Session_ID}` is a built-in Flow merge field that injects the current Salesforce session token automatically. The API uses it to write Contacts, Leads, and Tasks back to your org — no extra OAuth setup required.

**Element 2 — Decision (check the result)**

```
Outcome "Success":  {!HTTPCallout.responseStatusCode}  =  200
Outcome "Error":    all other outcomes
```

**Element 3 — Send Email (optional)**

```
To:      your@email.com
Subject: LinkedIn Digest {!$Flow.CurrentDate}
Body:    {!HTTPCallout.responseBody}
```

---

#### 6f. Alternative — Apex class

If HTTP Callout is not available in your Flow edition, create this Apex class instead:

```apex
public class LinkedInDigestCallout {
    @InvocableMethod(label='Run LinkedIn Digest')
    public static void runDigest(List<String> unused) {
        Http http = new Http();
        HttpRequest req = new HttpRequest();
        req.setEndpoint('callout:LinkedIn_Digest_API/webhook/run-digest');
        req.setMethod('POST');
        req.setHeader('Content-Type', 'application/json');
        req.setTimeout(120000);

        Map<String, Object> body = new Map<String, Object>{
            'nvidia_api_key'  => 'nvapi-YOUR_KEY_HERE',
            'sf_access_token' => UserInfo.getSessionId(),
            'max_posts'       => 50,
            'signature'       => 'YOUR_WEBHOOK_SECRET'
        };
        req.setBody(JSON.serialize(body));

        HttpResponse res = http.send(req);
        System.debug('Digest: ' + res.getStatusCode() + ' ' + res.getBody());
    }
}
```

In the Flow, replace the HTTP Callout element with **Action → Apex** and select `LinkedInDigestCallout`.

---

## API Reference

### `GET /health`

```json
{ "status": "ok" }
```

### `POST /webhook/run-digest`

**Request body**

```json
{
  "nvidia_api_key":  "nvapi-...",
  "sf_access_token": "00D...",
  "signature":       "your-webhook-secret",
  "max_posts":       50
}
```

`sf_access_token` and `nvidia_api_key` are optional — they override the `.env` values when provided, which is how Salesforce Flow passes them at runtime.

**Response**

```json
{
  "status": "success",
  "summary": {
    "date": "2025-01-15",
    "posts_found": 42,
    "sf_synced": 40,
    "sf_errors": [],
    "digest": {
      "date": "2025-01-15",
      "overview": "Today's feed was dominated by AI and startup topics...",
      "top_topics": ["artificial intelligence", "startups", "product launches"],
      "key_events": ["XYZ announced a Series B round", "New open-source model from ABC"],
      "post_summaries": [
        {
          "author": "John Smith",
          "company": "TechCorp",
          "headline": "CTO at TechCorp",
          "summary": "Shared thoughts on the future of AI agents in enterprise.",
          "sentiment": "positive",
          "relevance": "high",
          "post_url": "https://linkedin.com/posts/..."
        }
      ],
      "full_text": "Full 5-paragraph narrative digest..."
    }
  }
}
```

---

## Updating the app

```bash
cd ~/linkedin-digest
git pull
docker compose down
docker compose up -d --build
```

---

## Troubleshooting

**LinkedIn login fails** — delete `data/linkedin_cookies.json` and trigger a manual run; Playwright will re-authenticate and save fresh cookies.

**Playwright crashes in Docker** — make sure you're on `t3.small` or larger; headless Chromium needs at least 1 GB RAM.

**Salesforce callout times out** — the pipeline takes 60–90 seconds on large feeds. Increase the Apex `setTimeout` to `180000` or raise the Flow timeout if needed.

**`sf_errors` in the response** — the `LinkedIn_Profile_URL__c` custom field is likely missing on Contact or Lead. Follow step 6a above.

**Port 5000 unreachable** — check the EC2 Security Group inbound rules: TCP port 5000 must be open to the Salesforce IP ranges (or `0.0.0.0/0` for testing).

---

## License

MIT
