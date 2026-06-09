#!/usr/bin/env python3
"""
Webhook Receiver for Incoming Faxes

This script runs a Flask server that receives webhook events from Telnyx
when faxes are received or when outbound fax status changes.

Usage:
    python scripts/receive_webhook.py --port 8080
    
For local testing:
    ngrok http 8080
    # Then set the ngrok URL in Telnyx Mission Control
"""

import os
import sys
import json
import hashlib
import hmac
from datetime import datetime
from pathlib import Path
from typing import Optional

import logging
import requests
import structlog
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Configure stdlib logging so structlog's filter_by_level works
logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logger = structlog.get_logger()

# Initialize Flask app
app = Flask(__name__)

# Configuration
INBOX_DIR = PROJECT_ROOT / "data" / "inbox"
LOGS_DIR = PROJECT_ROOT / "logs"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "eyecarecenteroc@gmail.com")

# failure_reason values that mean partial transmission (→ "Incomplete"), not hard reject (→ "Error")
INCOMPLETE_REASONS = set(
    r.strip().lower()
    for r in os.getenv("INCOMPLETE_FAILURE_REASONS", "partial,transmission,disconnected,timeout,interrupted").split(",")
)

# Ensure directories exist at import time (gunicorn doesn't call main())
INBOX_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


@app.route("/", methods=["GET"])
def index():
    return jsonify({
        "service": "Fax Webhook Server",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "telnyx_webhook": "/webhook/fax/telnyx",
            "srfax_webhook": "/webhook/fax/srfax",
            "ghl_send_fax": "/api/send-fax"
        }
    })


def verify_telnyx_signature(payload: bytes, signature: str) -> bool:
    """Verify Telnyx webhook signature for security."""
    if not WEBHOOK_SECRET:
        logger.warning("webhook_secret_not_configured")
        return True  # Allow in development
    
    expected = hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected, signature)


def download_fax_pdf(media_url: str, fax_id: str) -> Optional[Path]:
    """Download fax PDF from Telnyx and save to inbox."""
    try:
        response = requests.get(
            media_url,
            headers={"Authorization": f"Bearer {os.getenv('TELNYX_API_KEY')}"},
            timeout=30
        )
        response.raise_for_status()
        
        # Save to inbox
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fax_id}.pdf"
        filepath = INBOX_DIR / filename
        
        filepath.write_bytes(response.content)
        logger.info("fax_downloaded", path=str(filepath), size=len(response.content))
        
        return filepath
        
    except Exception as e:
        logger.error("fax_download_failed", error=str(e), fax_id=fax_id)
        return None


def save_fax_metadata(fax_id: str, data: dict, filepath: Optional[Path]) -> None:
    """Save fax metadata as JSON for tracking."""
    metadata = {
        "fax_id": fax_id,
        "received_at": datetime.now().isoformat(),
        "from_number": data.get("from"),
        "to_number": data.get("to"),
        "pages": data.get("page_count"),
        "status": data.get("status"),
        "pdf_path": str(filepath) if filepath else None,
        "raw_payload": data
    }
    
    metadata_path = INBOX_DIR / f"{fax_id}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    logger.info("metadata_saved", path=str(metadata_path))


def log_to_activity_file(event_type: str, data: dict) -> None:
    """Append activity to markdown log file for agent readability."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / "fax_activity.md"
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    entry = f"""
## {timestamp} - {event_type}
- **Fax ID**: {data.get('fax_id', 'N/A')}
- **From**: {data.get('from', 'N/A')}
- **To**: {data.get('to', 'N/A')}
- **Status**: {data.get('status', 'N/A')}
- **Pages**: {data.get('page_count', 'N/A')}

---
"""
    
    with open(log_file, "a") as f:
        f.write(entry)


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})


@app.route("/webhook/fax/telnyx", methods=["POST"])
def telnyx_webhook():
    """
    Handle Telnyx fax webhooks.
    Acts as 'Traffic Cop' to route fax to:
    1. Local Inbox (always)
    2. Google Drive (Archive)
    3. GoHighLevel (Workflow Trigger)
    4. Email (Notification)
    """
    # Verify signature
    signature = request.headers.get("telnyx-signature-ed25519", "")
    if WEBHOOK_SECRET and not verify_telnyx_signature(request.data, signature):
        logger.warning("invalid_webhook_signature")
        return jsonify({"error": "Invalid signature"}), 401
    
    try:
        payload = request.json
        event_type = payload.get("data", {}).get("event_type", "unknown")
        fax_data = payload.get("data", {}).get("payload", {})
        fax_id = fax_data.get("fax_id", "unknown")
        
        logger.info("webhook_received", event_type=event_type, fax_id=fax_id)
        
        if event_type == "fax.received":
            # 1. Download to Local Inbox
            media_url = fax_data.get("media_url")
            filepath = None
            if media_url:
                filepath = download_fax_pdf(media_url, fax_id)
                save_fax_metadata(fax_id, fax_data, filepath)
            
            # 2. Upload to Google Drive
            gdrive_link = None
            if filepath and os.getenv("GDRIVE_INCOMING_FOLDER_ID"):
                try:
                    from scripts.sync_gdrive import get_drive_service, upload_file
                    service = get_drive_service()
                    result = upload_file(service, filepath, os.getenv("GDRIVE_INCOMING_FOLDER_ID"))
                    gdrive_link = result.get("link")
                    logger.info("gdrive_synced", link=gdrive_link)
                except Exception as e:
                    logger.error("gdrive_sync_failed", error=str(e))

            # 3. Forward to GoHighLevel
            if os.getenv("GHL_INBOUND_WEBHOOK_URL"):
                try:
                    # Enrich payload with our processed data
                    ghl_payload = {
                        "event": "fax_received",
                        "fax_id": fax_id,
                        "from_number": fax_data.get("from"),
                        "to_number": fax_data.get("to"),
                        "pdf_url": gdrive_link or media_url, # Prefer Drive Link (permanent)
                        "pages": fax_data.get("page_count"),
                        "original_data": fax_data
                    }
                    requests.post(os.getenv("GHL_INBOUND_WEBHOOK_URL"), json=ghl_payload, timeout=10)
                    logger.info("ghl_forwarded")
                except Exception as e:
                    logger.error("ghl_forward_failed", error=str(e))

            # 4. JSON Email Notification
            if filepath and os.getenv("SENDER_EMAIL") and os.getenv("SMTP_PASSWORD"):
                 try:
                     send_email_notification(
                         to_email=os.getenv("SENDER_EMAIL"),
                         subject=f"New Fax from {fax_data.get('from')}",
                         body=f"Received new fax ID: {fax_id}\nPages: {fax_data.get('page_count')}",
                         attachment_path=filepath
                     )
                 except Exception as e:
                     logger.error("email_send_failed", error=str(e))

            log_to_activity_file("📥 Fax Received", fax_data)
            
        elif event_type == "fax.delivered":
            log_to_activity_file("✅ Fax Delivered", fax_data)
            notify_fax_status("Completed", fax_data.get("to"), fax_data)

        elif event_type == "fax.failed":
            failure_reason = fax_data.get("failure_reason", "unknown")
            log_to_activity_file(f"❌ Fax Failed: {failure_reason}", fax_data)
            # Classify: if the reason contains any incomplete keyword → "Incomplete", else "Error"
            reason_lower = failure_reason.lower()
            label = "Incomplete" if any(kw in reason_lower for kw in INCOMPLETE_REASONS) else "Error"
            notify_fax_status(label, fax_data.get("to"), fax_data)
            
        return jsonify({"status": "ok", "event_type": event_type}), 200
        
    except Exception as e:
        logger.exception("webhook_error", error=str(e))
        return jsonify({"error": str(e)}), 500

def send_email_notification(to_email: str, subject: str, body: str, attachment_path: Optional[Path] = None):
    """Send email via SMTP, optionally with a PDF attachment."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    from email.mime.application import MIMEApplication

    msg = MIMEMultipart()
    msg["From"] = os.getenv("SENDER_EMAIL")
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body))

    if attachment_path:
        with open(attachment_path, "rb") as f:
            part = MIMEApplication(f.read(), Name=attachment_path.name)
            part["Content-Disposition"] = f'attachment; filename="{attachment_path.name}"'
            msg.attach(part)

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(os.getenv("SENDER_EMAIL"), os.getenv("SMTP_PASSWORD"))
        server.send_message(msg)

    logger.info("email_sent", to=to_email, subject=subject)


def format_fax_number(raw: str) -> str:
    """Format +17145551234 → 714-555-1234 for human-readable subjects."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return raw or "unknown"


def notify_fax_status(status_label: str, to_number: str, fax_data: dict) -> None:
    """Email a fax status notification — must never raise (webhook stays 200)."""
    try:
        if not os.getenv("SMTP_PASSWORD"):
            logger.warning("notify_skipped_no_smtp_password")
            return

        formatted = format_fax_number(to_number)
        subject = f"{status_label} fax to {formatted}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z") or datetime.now().strftime("%Y-%m-%d %H:%M:%S PST")

        lines = [
            "=" * 50,
            "FAX TRANSMISSION VERIFICATION",
            "=" * 50,
            "",
            f"Date/Time:       {timestamp}",
            f"Fax ID:          {fax_data.get('fax_id', 'N/A')}",
            f"From:            {fax_data.get('from', 'N/A')}",
            f"To:              {to_number or 'N/A'} ({formatted})",
            f"Pages:           {fax_data.get('page_count', 'N/A')}",
            f"Result:          {status_label.upper()}",
        ]
        reason = fax_data.get("failure_reason")
        if reason:
            lines.append(f"Failure Reason:  {reason}")
        lines += [
            "",
            "-" * 50,
            "LEGAL NOTICE — CALIFORNIA PROOF OF FAX SERVICE",
            "-" * 50,
            "This transmission confirmation constitutes proof of",
            "service by facsimile pursuant to California Code of",
            "Civil Procedure § 1013(e). This record confirms that",
            f"the above document was {'successfully transmitted' if status_label == 'Completed' else 'attempted for transmission'}",
            f"to fax number {formatted} on {timestamp}.",
            "",
            f"Sending Party:   {os.getenv('SENDER_NAME', 'Eye Care Center of Orange County')}",
            f"Sender Fax:      {format_fax_number(os.getenv('SENDER_FAX', ''))}",
            f"Confirmation ID: {fax_data.get('fax_id', 'N/A')}",
            "",
            "Retain this record for your files.",
            "=" * 50,
        ]

        send_email_notification(
            to_email=NOTIFY_EMAIL,
            subject=subject,
            body="\n".join(lines),
        )
        logger.info("fax_status_notified", status=status_label, to=to_number)
    except Exception as e:
        logger.error("fax_status_notify_failed", error=str(e), status=status_label)


@app.route("/webhook/fax/srfax", methods=["POST"])
def srfax_webhook():
    """
    Handle SRFax webhooks (alternative provider).
    Note: SRFax uses polling by default, this endpoint is for their
    optional webhook notifications.
    """
    try:
        payload = request.json
        logger.info("srfax_webhook_received", payload=payload)
        
        # SRFax has different payload structure
        fax_id = payload.get("FaxDetailsID")
        from_number = payload.get("CallerID")
        pages = payload.get("Pages")
        
        log_to_activity_file("📥 SRFax Received", {
            "fax_id": fax_id,
            "from": from_number,
            "pages": pages
        })
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("srfax_webhook_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/webhook/ghl", methods=["POST"])
def ghl_forward():
    """
    Forward fax events to GoHighLevel workflow.
    This can be used to trigger GHL workflows when faxes are received.
    """
    try:
        payload = request.json
        
        # Forward to GHL inbound webhook if configured
        ghl_webhook_url = os.getenv("GHL_INBOUND_WEBHOOK_URL")
        if ghl_webhook_url:
            response = requests.post(
                ghl_webhook_url,
                json=payload,
                timeout=10
            )
            logger.info("ghl_forward_success", status=response.status_code)
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        logger.exception("ghl_forward_error", error=str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/send-fax", methods=["POST"])
def send_fax_from_ghl():
    """Trigger a fax send from GHL Workflow."""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload"}), 400

        logger.info("ghl_request_received", data=data)

        to_number = data.get("phone") or data.get("contact_phone") or data.get("contact", {}).get("phone")
        if not to_number:
            return jsonify({"error": "Missing phone number"}), 400

        template_id = data.get("template", "referral_introduction")
        variables = data.get("customData", {})

        from scripts.send_fax import load_template, render_template, generate_pdf, send_fax_telnyx, save_to_outbox, validate_tcpa_compliance

        template_content, _ = load_template(template_id)

        render_vars = {
            "provider_name": data.get("first_name", "") + " " + data.get("last_name", ""),
            "provider_phone": to_number,
            **variables
        }
        rendered_content = render_template(template_content, render_vars)

        errors = validate_tcpa_compliance(rendered_content, to_number)
        if errors:
            logger.error("tcpa_fail", errors=errors)
            return jsonify({"error": "TCPA Compliance Failed", "details": errors}), 400

        pdf_dir = PROJECT_ROOT / "staging" / "ghl_generated"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"ghl_{datetime.now().strftime('%Y%m%d%H%M%S')}_{to_number[-4:]}.pdf"
        generate_pdf(rendered_content, pdf_path)

        result = send_fax_telnyx(to_number, pdf_path)
        save_to_outbox(pdf_path, {"source": "GHL", "ghl_payload": data, **result})

        return jsonify({
            "status": "success",
            "fax_id": result["fax_id"],
            "message": "Fax queued successfully"
        }), 200

    except Exception as e:
        logger.exception("ghl_send_failed", error=str(e))
        return jsonify({"error": str(e)}), 500


def main():
    """Run the webhook receiver server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Fax Webhook Receiver")
    parser.add_argument("--port", type=int, default=int(os.getenv("WEBHOOK_PORT", 8080)))
    parser.add_argument("--host", default=os.getenv("WEBHOOK_HOST", "0.0.0.0"))
    parser.add_argument("--debug", action="store_true", default=os.getenv("DEBUG", "false").lower() == "true")
    args = parser.parse_args()
    
    logger.info("starting_webhook_server", host=args.host, port=args.port)
    
    # Initialize directories
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize activity log
    activity_log = LOGS_DIR / "fax_activity.md"
    if not activity_log.exists():
        activity_log.write_text("# Fax Activity Log\n\n")
    
    print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                    FAX WEBHOOK RECEIVER                        ║
╠═══════════════════════════════════════════════════════════════╣
║  Server:     http://{args.host}:{args.port}                          
║  Health:     http://{args.host}:{args.port}/health                   
║  Telnyx:     http://{args.host}:{args.port}/webhook/fax/telnyx       
║  SRFax:      http://{args.host}:{args.port}/webhook/fax/srfax        
╠═══════════════════════════════════════════════════════════════╣
║  For local testing, use ngrok:                                 ║
║  $ ngrok http {args.port}                                              
║  Then set the ngrok URL in your fax provider's portal.         ║
╚═══════════════════════════════════════════════════════════════╝
""")
    
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
