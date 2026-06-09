# Shared Task List — Fax Webhook Server
> Updated 2026-06-09. Check this file at session start.
> **Scope:** Fax project ONLY. Tasks belonging to other projects go in THEIR .claude/SHARED-TASKS.md.

## Pending Tasks
| # | Status | Task | Notes |
|---|--------|------|-------|
| 2 | 📋 Todo | Configure GHL inbound/outbound webhook URLs in Render env vars | `GHL_INBOUND_WEBHOOK_URL` and `GHL_OUTBOUND_WEBHOOK_URL` not yet set — need GHL workflow webhook IDs |
| 3 | 📋 Todo | Set up Google Drive sync (GDRIVE_INCOMING_FOLDER_ID, service account JSON) | For archiving incoming faxes to Drive |
| 4 | 📋 Todo | Test end-to-end: send a real fax to own number, verify webhook receives it | Needs Telnyx Mission Control configured first (task #1) |
| 5 | 📋 Todo | Add WEBHOOK_SECRET for Telnyx signature verification | Currently allows unsigned webhooks in production |
| 17 | ⏳ Pending | Add SMTP_PASSWORD (Gmail App Password) to Render env | Required for status-notification emails to send. SENDER_EMAIL already set. |
| 18 | 📋 Todo | Implement fax status notifications — PRD approved? | Spec: `.primitive-tasks/specs/fax-status-notifications.md`. Email completed/error/incomplete fax to eyecarecenteroc@gmail.com with status+number subject. AWAITING USER APPROVAL before build. |

## Completed
| # | Status | Task | Completed | Session |
|---|--------|------|-----------|---------|
| 6 | ✅ Done | Fix server startup — missing deps, broken structlog, Flask dev server | 2026-06-02 | render-fix-2026-06 |
| 7 | ✅ Done | Create Render deployment config (Procfile, render.yaml, .python-version, .gitignore) | 2026-06-02 | render-fix-2026-06 |
| 8 | ✅ Done | Merge GHL /api/send-fax route into main webhook server (single Flask app) | 2026-06-02 | render-fix-2026-06 |
| 9 | ✅ Done | Init git repo, push to GitHub (Mobo4/Fax, public) | 2026-06-02 | render-fix-2026-06 |
| 10 | ✅ Done | Create Render service via API (srv-d8fprh77f7vs73eju1f0) | 2026-06-03 | render-fix-2026-06 |
| 11 | ✅ Done | Set 16 env vars on Render from credential vault (Telnyx, Anthropic, GHL, sender info) | 2026-06-03 | render-fix-2026-06 |
| 12 | ✅ Done | Deploy to Render — verified live + health check passing | 2026-06-03 | render-fix-2026-06 |
| 13 | ✅ Done | Fix Render free-tier cold start — keep-alive cron on 0.160 every 14 min | 2026-06-03 | render-fix-2026-06 |
| 14 | ✅ Done | Save Render API key to credential vault (render.env) | 2026-06-03 | render-fix-2026-06 |
| 15 | ✅ Done | Create local .env from vault credentials for local dev | 2026-06-03 | render-fix-2026-06 |
| 1 | ✅ Done | Set Telnyx webhook URL to correct path via API | 2026-06-09 | telnyx-credentials-2026-06 |
| 16 | ✅ Done | Replace placeholder TELNYX_API_KEY with real key (vault + both Render services) | 2026-06-09 | telnyx-credentials-2026-06 |

## Session Log
| Date | Session | Work Done |
|------|---------|-----------|
| 2026-06-02/03 | render-fix-2026-06 | Fixed stuck Render server: missing Python deps, broken structlog config, Flask dev server. Created full Render deployment (Procfile, render.yaml, gunicorn). Pushed to GitHub. Created Render service via API, set 16 env vars, deployed. Added keep-alive cron on 0.160. |
| 2026-06-09 | telnyx-credentials-2026-06 | Added real Telnyx API key (admin@eyecarecenteroc.com account) to vault, .env, both Render services. Fixed Telnyx webhook URL path mismatch (/telnyx/webhook → /webhook/fax/telnyx). Verified API key works, fax app + number active, T38 enabled. Redeployed both services. |
