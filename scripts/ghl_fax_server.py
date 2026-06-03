#!/usr/bin/env python3
"""
GHL Fax API Server

Exposes endpoints for GoHighLevel to trigger fax sends.
This turns your local machine or server into a Fax Gateway for GHL.

Endpoints:
    POST /api/send-fax
    Payload: {
        "contact_phone": "+15551234567",
        "contact_name": "Dr. Smith",
        "template": "referral_introduction",
        "variables": { ... }
    }

Usage:
    python scripts/ghl_fax_server.py --port 8081
"""

import os
import sys
import argparse
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify
import structlog

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

# Logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
)
logger = structlog.get_logger()

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "GHL Fax Gateway"}), 200

@app.route("/api/send-fax", methods=["POST"])
def send_fax_from_ghl():
    """
    Trigger a fax send from GHL Workflow.
    Expected JSON payload from GHL Webhook Action.
    """
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON payload"}), 400
            
        logger.info("ghl_request_received", data=data)
        
        # 1. Extract parameters
        # GHL often sends "phone" or "contact_phone"
        to_number = data.get("phone") or data.get("contact_phone") or data.get("contact", {}).get("phone")
        if not to_number:
            return jsonify({"error": "Missing phone number"}), 400
            
        template_id = data.get("template", "referral_introduction")
        # GHL Custom Values can be passed as variables
        variables = data.get("customData", {}) # GHL 'Custom Data' property
        
        # 2. Render and Generate PDF
        # We reuse the logic from send_fax.py, but we need to import it carefully
        from scripts.send_fax import load_template, render_template, generate_pdf, send_fax_telnyx, save_to_staging, save_to_outbox, validate_tcpa_compliance
        
        # Load template
        template_content, _ = load_template(template_id)
        
        # Render
        # Merge GHL contact data into variables
        render_vars = {
            "provider_name": data.get("first_name", "") + " " + data.get("last_name", ""),
            "provider_phone": to_number,
            **variables
        }
        
        rendered_content = render_template(template_content, render_vars)
        
        # TCPA Check
        errors = validate_tcpa_compliance(rendered_content, to_number)
        if errors:
            logger.error("tcpa_fail", errors=errors)
            return jsonify({"error": "TCPA Compliance Failed", "details": errors}), 400
            
        # Generate PDF
        pdf_dir = PROJECT_ROOT / "staging" / "ghl_generated"
        pdf_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = pdf_dir / f"ghl_{datetime.now().strftime('%Y%m%d%H%M%S')}_{to_number[-4:]}.pdf"
        generate_pdf(rendered_content, pdf_path)
        
        # 3. Send Fax
        # In a production app, we should offload this to a background queue (Redis/RQ)
        # For this primitive version, we'll do it synchronously (might timeout GHL if slow)
        result = send_fax_telnyx(to_number, pdf_path)
        
        # 4. Save Record
        save_to_outbox(pdf_path, {
            "source": "GHL",
            "ghl_payload": data,
            **result
        })
        
        return jsonify({
            "status": "success",
            "fax_id": result["fax_id"],
            "message": "Fax queued successfully"
        }), 200

    except Exception as e:
        logger.exception("ghl_send_failed", error=str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    
    print(f"🚀 GHL Fax Gateway running on port {args.port}")
    app.run(host="0.0.0.0", port=args.port)
