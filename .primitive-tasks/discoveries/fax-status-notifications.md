# Discovery — Fax Status Notifications

_Date: 2026-06-09 · Session: render-fix-2026-06_

## What exists today

- **Server**: `scripts/receive_webhook.py` (Flask via gunicorn on Render). Two live URLs:
  `https://telnyx-fax-webhook.onrender.com` and `https://fax-webhook-server.onrender.com`. Both healthy.
- **Webhook route**: `/webhook/fax/telnyx` already receives Telnyx events.
- **Outbound status handlers already wired but DO NOTHING useful** (`receive_webhook.py:245-250`):
  - `fax.delivered` → only `log_to_activity_file("✅ Fax Delivered", fax_data)`
  - `fax.failed` → only `log_to_activity_file("❌ Fax Failed: {failure_reason}", fax_data)`
  - **Neither sends any notification to the user.**
- **Email helper EXISTS and works**: `send_email_notification(to_email, subject, body, attachment_path)`
  (`receive_webhook.py:258`) — SMTP via Gmail, supports subject + attachment. Currently only called
  for **inbound** `fax.received` (line 234), gated on `SENDER_EMAIL` + `SMTP_PASSWORD`.
- **GHL forward helper exists**: posts to `GHL_INBOUND_WEBHOOK_URL` (currently used for inbound only).

## Config state (Render env vars)

- `SENDER_EMAIL` = set (eyecarecenteroc@gmail.com)
- `SMTP_PASSWORD` = **NOT set** → email path is currently dead until a Gmail App Password is added.
- `GHL_INBOUND_WEBHOOK_URL` = **NOT set**.
- `TELNYX_API_KEY` = **PLACEHOLDER** (`KEYxxxx...`) → no real fax can send/receive yet. Blocker for end-to-end test.

## Telnyx event reality (affects the "incomplete" requirement)

Telnyx fax webhooks emit terminal events `fax.delivered` and `fax.failed`. There is **no native
"incomplete" event.** `fax.failed` carries a `failure_reason` string. "Incomplete" must be **derived**
by bucketing `failure_reason` values (e.g. partial-page / dropped-mid-transmission vs hard reject).

## Implication

Feature is **additive and small**: extend the two existing handlers to call the existing email helper
with a status-specific subject. No new service, container, or dependency. Primary blocker for testing
(not for building) is the placeholder Telnyx key + missing SMTP_PASSWORD.
