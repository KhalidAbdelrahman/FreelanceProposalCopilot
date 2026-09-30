# Freelance Proposal Copilot

A working, compliance-first initial build for **Freelancer.com and Upwork only**. It discovers opportunities, qualifies them, drafts proposals in Amgad's playbook style, sends review notifications, records manually submitted proposals in the existing Excel tracker, and alerts on client-response emails. Fiverr and PeoplePerHour are intentionally out of scope for this phase.

> **Hard safety boundary:** this project contains no code that submits a proposal, places a bid, sends a custom offer, sends a client message, bypasses a CAPTCHA, or reuses browser/session cookies in an API client. “Approve” means “I reviewed this draft”; it does not send anything. Final submission stays on the platform and requires your click.

## 1. What is implemented

```text
Freelancer official API ─┐
Platform alert emails ───┼─> normalize -> score -> draft -> SQLite review queue
Opt-in browser reader ───┘                         │
                                                   ├─> Slack / Telegram review link
                                                   └─> local review page
                                                        │
                                      personal review + approve
                                                        │
                               copy text + open platform job
                                                        │
                                   YOU click final Submit
                                                        │
                         mark manually submitted -> Excel tracker

Platform reply emails -> Microsoft Graph Mail.Read -> Slack / Telegram alert
```

### Discovery

- **Freelancer.com:** read-only discovery through the official `/api/projects/0.1/projects/active/` API using your OAuth token.
- **Upwork:** platform-native saved-search/instant-alert emails are the default. Upwork's current policy warns that unapproved scripts, browser extensions, page monitors, auto-refresh tools, and background polling can trigger enforcement. Apply for an official API key before adding API automation.
- **Optional Upwork browser reader:** a foreground, one-shot Playwright adapter is included but disabled. It only collects visible job links; it never fills or clicks a form. This remains a policy/enforcement risk and should not be used without written approval from Upwork.

### Drafting and personal tone

The initial profile comes from `Freelance_Platform_System_Playbook.docx` and `Freelance_Application_Tracker.xlsx`:

1. Begin with one exact project detail, not a biography.
2. Use one truthful proof point only.
3. Give a short, concrete approach.
4. Ask one useful clarifying question.
5. Stay below 150 words; avoid generic filler.

The two reference files did **not** contain full historical proposal bodies. Import your own past proposals to learn your actual phrasing:

```bash
python -m app.cli import-proposals /path/to/proposal-export.xlsx
# Also supports CSV, TXT, Markdown, or a directory of TXT/Markdown files.
```

For CSV/XLSX, use a column named `proposal`, `cover letter`, `application`, or `text`. Review `tone_profile.yaml` and add only proof points you can truthfully claim.

## 2. Install

Python 3.11+ is required.

```bash
cd FreelanceProposalCopilot
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
python -m app.cli init-db
```

Run tests:

```bash
pytest -q
```

## 3. Connect the existing Excel tracker

Keep `Freelance_Application_Tracker.xlsx` in a locally synced OneDrive/SharePoint folder and set the full local path in `.env`:

```dotenv
TRACKER_PATH=/Users/amgad/OneDrive/Freelance_Application_Tracker.xlsx
```

Windows example:

```dotenv
TRACKER_PATH=C:\Users\Amgad\OneDrive\Freelance_Application_Tracker.xlsx
```

After you personally submit a proposal and click **I manually submitted it — record in tracker**, the app:

- validates the expected 12-column `Pipeline` schema;
- creates `Freelance_Application_Tracker.xlsx.bak` first;
- writes the next blank row (rows 5–300);
- marks `Personalized Opening?` as `Y`, status as `Sent`, and follow-up as three days later.

Do not keep the workbook open in desktop Excel while writing if your OS locks the file.

## 4. Configure AI drafting

The app uses an OpenAI-compatible Responses API. Put credentials in `.env`:

```dotenv
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-5-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

Without a key, the system still runs and creates deterministic fallback drafts, which must be edited more heavily.

Privacy note: job descriptions, your style profile, approved proof points, and imported proposal samples are sent to the configured model provider when a draft is generated. Do not import client-confidential material you are not permitted to share.

## 5. Configure Freelancer.com official API

1. Create an application/token in Freelancer.com's developer portal.
2. Start in the sandbox when practical.
3. Put the OAuth token in `.env`:

```dotenv
FREELANCER_OAUTH_TOKEN=your_oauth_token
FREELANCER_API_BASE=https://www.freelancer.com/api
```

4. Edit `freelancer_queries` in `config.yaml`.

The connector is read-only. Although the official API/SDK exposes bid and messaging functions, this project intentionally does not call them; the final bid remains manual.

## 6. Configure Microsoft 365 mail monitoring

This is the default low-risk discovery/reply-monitor path for both initial platforms. First enable email notifications on Upwork and Freelancer.com.

In Microsoft Entra ID:

1. Register a single-tenant or personal/internal-use app.
2. Enable public client/device-code flow.
3. Add delegated Microsoft Graph permission **Mail.Read** only.
4. Put the application and tenant IDs in `.env`:

```dotenv
M365_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
M365_TENANT_ID=your-tenant-id
```

Authenticate once:

```bash
python -m app.cli auth-m365
```

The token cache is written to `data/msal_cache.json`. Treat it as a secret; the included `.gitignore` excludes it. The reader fetches new messages, classifies platform job/reply notifications, stores the latest cursor, and does not send or delete mail.

If you already manage tokens elsewhere, set a short-lived `M365_ACCESS_TOKEN` instead.

## 7. Configure notifications

### Slack

Create an incoming webhook and set:

```dotenv
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### Telegram

Create a bot, start a chat with it, and set:

```dotenv
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Notifications contain the draft excerpt and a local review URL. `PUBLIC_BASE_URL` must be reachable from the device opening the alert. On a trusted LAN, for example:

```dotenv
PUBLIC_BASE_URL=http://192.168.1.20:8765
```

Do not expose the review app directly to the public internet. If remote access is needed, place it behind an authenticated VPN/reverse proxy.

## 8. Run

One cycle for testing:

```bash
python -m app.cli run-once
```

Continuous local dashboard and polling worker:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open <http://127.0.0.1:8765>.

Workflow for each proposal:

1. Open the draft from Slack/Telegram or the dashboard.
2. Read the original job and edit the draft.
3. Check the certification box and approve.
4. Copy the proposal and open the platform job.
5. Review price, milestones, attachments, screening questions, Connects/bid fees, and identity prompts.
6. Personally click the platform's final Submit/Send button.
7. Return to the dashboard and record the manual submission in the tracker.

## 9. Optional foreground browser reader — higher risk

The browser reader is intentionally off and is never launched by the background scheduler.

```dotenv
ENABLE_EXPERIMENTAL_BROWSER=true
BROWSER_PROFILE_DIR=data/browser-profile
```

Add saved-search URLs to `config.yaml`, then:

```bash
playwright install chromium
python -m app.cli browser-scan upwork
# Do not run this without written approval from Upwork.
```

You log in yourself in the visible browser. The adapter waits between pages and only extracts matching links. Selectors and page structures can change. It must not be adapted to auto-refresh, run headlessly in the background, fill forms, click submit, bypass CAPTCHA, or copy session cookies into scripts.

## 10. Platform recommendation and risk decisions

| Platform | Default implementation | Remaining risk | Recommendation |
|---|---|---|---|
| Upwork | Native email alerts for discovery and replies; manual website submission | Lowest practical risk. Email delivery may lag; proposal fields remain manual. | Use this now. Apply for an official API key only if eligible and keep automation inside the approved scope. Do not run the browser reader without written approval. |
| Freelancer.com | Official OAuth API for project discovery; email reply alerts; manual bid submission | API terms, rate limits, and approved data-use rules still apply. API/SDK versions may change. | Best candidate for deeper integration, but retain the human submit gate even though the SDK exposes bid functions. |

## 11. Why there is no one-click platform submit

The local **Approve** button is deliberately separate from platform submission. A single click that transmits a bid would defeat the documented human-review requirement and creates accidental-spam, pricing, Connects, attachment, identity, and policy risks. The design makes the review attestation auditable in SQLite while preserving the final platform action for you.

## 12. Operations and security

- Run under your user account; never share platform passwords or cookies.
- Store `.env`, `data/msal_cache.json`, `data/browser-profile/`, and the SQLite DB outside version control.
- Use least-privilege permissions: Graph `Mail.Read`; Freelancer read-only endpoints.
- Rotate API/webhook tokens and review notification logs.
- Keep polling at 60 seconds or slower. Platform-native email latency controls actual response time.
- Re-check platform policies before enabling new automation. Policies and interfaces change.
- Every draft remains untrusted until you review factual claims, scope, price, timeline, attachments, and client-specific details.

## 13. Policy sources checked (28 September 2026)

- Upwork automation policy: https://support.upwork.com/hc/en-us/articles/43342677368467-Use-bots-and-other-automation-properly
- Upwork API-key requirements: https://support.upwork.com/hc/en-us/articles/115015857647-How-to-request-an-API-key-from-Upwork
- Freelancer developer portal: https://developers.freelancer.com/
- Freelancer API terms: https://www.freelancer.com/about/apiterms
- Freelancer official Python SDK: https://github.com/freelancer/freelancer-sdk-python

This is an engineering interpretation, not legal advice. If a platform gives account-specific written guidance, follow that guidance over this README.
