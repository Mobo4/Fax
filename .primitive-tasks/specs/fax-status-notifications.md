# PRD — Fax Status Notifications

_Status: DRAFT (awaiting approval) · Date: 2026-06-09 · Owner: Fax project_
_Discovery: `.primitive-tasks/discoveries/fax-status-notifications.md`_

## Problem Statement

When an outbound fax finishes, the user (eyecarecenteroc@gmail.com) gets **no notification**. The
Telnyx webhook already delivers `fax.delivered` and `fax.failed` events to the server, but the handlers
only write a local log file on Render (ephemeral, invisible to the user). The practice needs to know,
per fax, whether it **completed**, **errored**, or was **incomplete**, and to which number.

## Goal

On every terminal outbound fax event, send one notification whose **subject line states the status and
destination number**, so the user can triage from their inbox without opening the server.

Required subject formats (number formatted `xxx-xxx-xxxx`):
- `Completed fax to 714-555-1234`
- `Error fax to 714-555-1234`
- `Incomplete fax to 714-555-1234`

## Delivery Channel Decision

**Recommendation: Email to eyecarecenteroc@gmail.com.** Rationale (Primitive Gate):
- The email helper `send_email_notification()` already exists and supports exact subject control.
- Email lands directly where the user asked; no external workflow to build.
- GHL webhook would require building a GHL workflow AND GHL has no clean concept of a custom email
  "subject" — it would need a parallel email-send action anyway. More moving parts for the same result.

GHL is kept as an **optional secondary** (out of scope for v1 unless email proves unreliable).

## Status Mapping (the one non-obvious decision)

Telnyx has no "incomplete" event. Derive three buckets from the event + `failure_reason`:

| Notification status | Triggered by |
|---|---|
| **Completed** | `fax.delivered` |
| **Incomplete** | `fax.failed` where `failure_reason` indicates partial / mid-transmission loss (e.g. `partial`, contains `transmission` / `disconnected` / `timeout` / `interrupted`) |
| **Error** | `fax.failed` for any other reason (e.g. `busy`, `no_answer`, `invalid_number`, `rejected`, `account_*`) |

The exact `failure_reason` string is included in the email body for diagnosis. The bucketing list lives
in **one config constant** so it can be tuned without code surgery (verify criterion #5).

## Proposed Changes (numbered, specific)

1. **`scripts/receive_webhook.py`** — add a helper `notify_fax_status(status_label, to_number, fax_data)`
   that:
   - formats the destination number to `xxx-xxx-xxxx` (strip `+1`, group digits; fall back to raw on odd length),
   - builds subject `"{status_label} fax to {formatted_number}"`,
   - builds a body with fax_id, from, to, pages, status, and `failure_reason` (if any),
   - calls existing `send_email_notification(to_email=NOTIFY_EMAIL, subject, body, attachment_path=None)`,
   - is wrapped in try/except and logs on failure (must never 500 the webhook → Telnyx would retry).
2. **`scripts/receive_webhook.py:245`** — in the `fax.delivered` branch, call
   `notify_fax_status("Completed", fax_data.get("to"), fax_data)`.
3. **`scripts/receive_webhook.py:248`** — in the `fax.failed` branch, classify via the `failure_reason`
   bucket constant → call `notify_fax_status("Incomplete" | "Error", fax_data.get("to"), fax_data)`.
4. **Make `send_email_notification` attachment-optional** — current signature requires `attachment_path`;
   allow `None` (status emails have no PDF). Small change at `receive_webhook.py:258`.
5. **Config** — add to `.env` / Render env:
   - `NOTIFY_EMAIL` (default `eyecarecenteroc@gmail.com`)
   - `SMTP_PASSWORD` (Gmail App Password — **currently missing; required for ANY email to send**)
   - `INCOMPLETE_FAILURE_REASONS` optional override (comma list) for the incomplete bucket.
6. **Docs** — note the new env vars in `.env.example`.

## Out of Scope (v1)

- GHL webhook delivery (kept as fallback only).
- Inbound fax notifications (already handled separately).
- SMS/Telegram/push notification channels.
- Retry/queue for failed email sends (Telnyx already retries the webhook; a dropped email just logs).
- Fixing the placeholder `TELNYX_API_KEY` — tracked separately; it blocks end-to-end *testing* but not
  building this feature.

## Dependencies / Blockers

- **SMTP_PASSWORD** (Gmail App Password for eyecarecenteroc@gmail.com) must be set in Render env before
  emails actually send. Until then the code runs but email login fails (logged, non-fatal).
- **Real TELNYX_API_KEY** required to generate real terminal events for a true end-to-end test. Unit
  tests (simulated webhook payloads) do not need it.

## Verify Criteria (acceptance)

1. POST a simulated `fax.delivered` payload → email arrives with subject `Completed fax to <num>`.
2. POST a simulated `fax.failed` with reason `busy` → subject `Error fax to <num>`.
3. POST a simulated `fax.failed` with a partial/transmission reason → subject `Incomplete fax to <num>`.
4. Number formatting: `+17145551234` renders as `714-555-1234` in the subject.
5. Changing `INCOMPLETE_FAILURE_REASONS` reclassifies a reason without code changes.
6. A raised exception inside `notify_fax_status` does NOT cause the webhook to return 500 (returns 200,
   logs the error) — verified by forcing an SMTP error.
7. Body of every email contains fax_id and the raw `failure_reason` (when present).

## Primitive Gate (passed)

1. Simplest thing that works? **Yes** — extend two existing handlers + reuse the existing email helper.
2. New services/containers/deps? **No** — pure stdlib (`smtplib`, `email`) already imported.
3. Added cognitive load? **Minimal** — one helper + one bucket constant.
4. Would a senior call it over-engineered? **No.**
5. Can it break something working? **Low** — additive, try/except-wrapped, webhook stays 200.

## Synthesis Notes

- Single-app design retained (notifications live in the same Flask app, consistent with the earlier
  merge of the GHL send route).
- "Incomplete" is the only ambiguous requirement; resolved by deriving from `failure_reason` since
  Telnyx emits no incomplete event — documented as a tunable config constant rather than hard-coded.
- Email chosen over GHL strictly on simplicity + exact subject-line control, per the user's
  "whichever is easier."
