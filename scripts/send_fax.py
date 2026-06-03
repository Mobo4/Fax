#!/usr/bin/env python3
"""
Send Fax Script

Send faxes via Telnyx API with template rendering and TCPA compliance validation.

Usage:
    # Dry run (preview only, no sending)
    python scripts/send_fax.py --to "+15551234567" --template referral_introduction --dry-run
    
    # Actually send
    python scripts/send_fax.py --to "+15551234567" --template referral_introduction
    
    # Send with custom variables
    python scripts/send_fax.py --to "+15551234567" --template referral_introduction \
        --var provider_name="Dr. Smith" --var practice_name="Smith Eye Care"
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import telnyx
import yaml
from dotenv import load_dotenv
from jinja2 import Template
import structlog

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables
load_dotenv(PROJECT_ROOT / ".env")

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
)
logger = structlog.get_logger()

# Configure Telnyx
telnyx.api_key = os.getenv("TELNYX_API_KEY")


def load_config(config_name: str) -> dict:
    """Load YAML configuration file."""
    config_path = PROJECT_ROOT / "config" / f"{config_name}.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_template(template_id: str) -> tuple[str, dict]:
    """Load template file and its configuration."""
    templates_config = load_config("templates")
    
    template_config = None
    for t in templates_config.get("templates", []):
        if t["id"] == template_id:
            template_config = t
            break
    
    if not template_config:
        raise ValueError(f"Template not found: {template_id}")
    
    template_path = PROJECT_ROOT / template_config["file"]
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    
    return template_path.read_text(), template_config


def validate_tcpa_compliance(fax_content: str, to_number: str) -> list[str]:
    """
    Validate fax meets TCPA requirements.
    Returns list of compliance errors (empty if compliant).
    """
    errors = []
    compliance_config = load_config("compliance")
    tcpa = compliance_config.get("tcpa", {})
    
    if not tcpa.get("enabled"):
        return errors
    
    # Check opt-out notice
    opt_out_keywords = ["opt-out", "optout", "unsubscribe", "remove", "do not fax"]
    has_opt_out = any(kw in fax_content.lower() for kw in opt_out_keywords)
    if tcpa.get("requirements", {}).get("opt_out_required") and not has_opt_out:
        errors.append("TCPA: Missing opt-out mechanism in fax content")
    
    # Check sender identification
    sender_info = tcpa.get("requirements", {}).get("sender_identification", {})
    if sender_info:
        if sender_info.get("name") and sender_info["name"] not in fax_content:
            errors.append("TCPA: Missing sender name in fax content")
        if sender_info.get("phone") and sender_info["phone"] not in fax_content:
            errors.append("TCPA: Missing sender phone in fax content")
    
    # Check do-not-fax list
    dnf_config = tcpa.get("requirements", {}).get("do_not_fax_list", {})
    if dnf_config.get("enabled") and dnf_config.get("check_before_send"):
        dnf_path = PROJECT_ROOT / dnf_config.get("list_path", "data/lists/do_not_fax.csv")
        if dnf_path.exists():
            dnf_numbers = dnf_path.read_text().strip().split("\n")
            if to_number in dnf_numbers:
                errors.append("TCPA: Recipient is on do-not-fax list")
    
    return errors


def render_template(template_content: str, variables: dict) -> str:
    """Render Jinja2 template with variables."""
    # Add default variables
    templates_config = load_config("templates")
    sender = templates_config.get("default_sender", {})
    
    defaults = {
        "current_date": datetime.now().strftime("%B %d, %Y"),
        "sender_name": sender.get("name", os.getenv("SENDER_NAME", "")),
        "sender_phone": sender.get("phone", os.getenv("SENDER_PHONE", "")),
        "sender_fax": sender.get("fax", os.getenv("SENDER_FAX", "")),
        "sender_address": sender.get("address", os.getenv("SENDER_ADDRESS", "")),
        "sender_email": sender.get("email", os.getenv("SENDER_EMAIL", "")),
        "opt_out_email": sender.get("opt_out_email", os.getenv("SENDER_OPTOUT_EMAIL", "")),
    }
    
    all_vars = {**defaults, **variables}
    
    template = Template(template_content)
    return template.render(**all_vars)


def generate_pdf(content: str, output_path: Path) -> Path:
    """Convert Markdown content to PDF."""
    try:
        import markdown
        from weasyprint import HTML, CSS
        
        # Convert Markdown to HTML
        html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
        
        # Wrap in HTML template
        full_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    font-size: 11pt;
                    line-height: 1.4;
                    margin: 0.75in 1in;
                }}
                h1 {{ font-size: 14pt; margin-bottom: 0.5em; }}
                h2 {{ font-size: 12pt; margin-bottom: 0.5em; }}
                hr {{ border: none; border-top: 1px solid #333; margin: 1em 0; }}
                p {{ margin: 0.5em 0; }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Generate PDF
        HTML(string=full_html).write_pdf(output_path)
        logger.info("pdf_generated", path=str(output_path))
        
        return output_path
        
    except ImportError:
        logger.warning("weasyprint_not_installed", message="Saving as .txt instead")
        txt_path = output_path.with_suffix(".txt")
        txt_path.write_text(content)
        return txt_path


def send_fax_telnyx(to_number: str, pdf_path: Path) -> dict:
    """Send fax via Telnyx API."""
    # First, we need to upload or provide URL to the PDF
    # For now, we'll use a local file approach where we upload to a temporary URL
    # In production, you'd upload to S3/GCS and use that URL
    
    # For Telnyx, you need a publicly accessible URL
    # This is a simplified example - in production, upload to cloud storage first
    
    connection_id = os.getenv("TELNYX_FAX_APP_ID")
    from_number = os.getenv("TELNYX_FAX_NUMBER")
    
    if not all([connection_id, from_number, telnyx.api_key]):
        raise ValueError("Missing Telnyx configuration. Check .env file.")
    
    # Note: In a real implementation, you would:
    # 1. Upload PDF to cloud storage (S3, GCS, etc.)
    # 2. Get public URL
    # 3. Pass that URL to media_url
    
    # For local testing, you'd need to use ngrok or similar to expose the file
    media_url = f"https://your-server.com/files/{pdf_path.name}"  # Placeholder
    
    logger.info("sending_fax", to=to_number, from_=from_number, pdf=str(pdf_path))
    
    try:
        fax = telnyx.Fax.create(
            connection_id=connection_id,
            to=to_number,
            from_=from_number,
            media_url=media_url,
            quality="high"
        )
        
        result = {
            "fax_id": fax.id,
            "status": fax.status,
            "to": to_number,
            "from": from_number,
            "created_at": datetime.now().isoformat()
        }
        
        logger.info("fax_sent", **result)
        return result
        
    except telnyx.error.TelnyxError as e:
        logger.error("telnyx_error", error=str(e))
        raise


def save_to_staging(content: str, pdf_path: Optional[Path], metadata: dict) -> Path:
    """Save generated fax to staging for review."""
    staging_dir = PROJECT_ROOT / "staging" / "generated_faxes"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_{metadata.get('template', 'unknown')}"
    
    # Save content preview
    preview_path = staging_dir / f"{base_name}_preview.md"
    preview_path.write_text(content)
    
    # Save metadata
    metadata_path = staging_dir / f"{base_name}_metadata.json"
    metadata["content_path"] = str(preview_path)
    metadata["pdf_path"] = str(pdf_path) if pdf_path else None
    metadata["staged_at"] = datetime.now().isoformat()
    metadata_path.write_text(json.dumps(metadata, indent=2))
    
    logger.info("staged", preview=str(preview_path), metadata=str(metadata_path))
    
    return preview_path


def save_to_outbox(pdf_path: Path, metadata: dict) -> Path:
    """Save sent fax to outbox for archival."""
    outbox_dir = PROJECT_ROOT / "data" / "outbox"
    outbox_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest_name = f"{timestamp}_{metadata.get('fax_id', 'unknown')}.pdf"
    dest_path = outbox_dir / dest_name
    
    # Copy PDF to outbox
    import shutil
    shutil.copy(pdf_path, dest_path)
    
    # Save metadata
    metadata_path = dest_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, indent=2))
    
    logger.info("saved_to_outbox", path=str(dest_path))
    
    return dest_path


def main():
    parser = argparse.ArgumentParser(description="Send Fax via Telnyx")
    parser.add_argument("--to", required=True, help="Destination fax number (E.164 format)")
    parser.add_argument("--template", required=True, help="Template ID to use")
    parser.add_argument("--var", action="append", help="Template variable (key=value)", default=[])
    parser.add_argument("--dry-run", action="store_true", help="Preview only, don't send")
    args = parser.parse_args()
    
    # Parse variables
    variables = {}
    for var in args.var:
        if "=" in var:
            key, value = var.split("=", 1)
            variables[key] = value
    
    logger.info("starting", to=args.to, template=args.template, dry_run=args.dry_run)
    
    try:
        # Load and render template
        template_content, template_config = load_template(args.template)
        rendered_content = render_template(template_content, variables)
        
        # Validate TCPA compliance
        compliance_errors = validate_tcpa_compliance(rendered_content, args.to)
        if compliance_errors:
            logger.error("compliance_failed", errors=compliance_errors)
            print("\n⚠️  COMPLIANCE ERRORS:")
            for error in compliance_errors:
                print(f"   - {error}")
            print("\nFax not sent. Fix compliance issues and try again.")
            sys.exit(1)
        
        print("\n✅ Compliance check passed")
        
        # Generate PDF if not dry-run
        pdf_path = None
        if not args.dry_run:
            pdf_dir = PROJECT_ROOT / "staging" / "generated_faxes"
            pdf_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = pdf_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.template}.pdf"
            generate_pdf(rendered_content, pdf_path)
        
        # Save to staging
        metadata = {
            "template": args.template,
            "to": args.to,
            "variables": variables,
            "dry_run": args.dry_run
        }
        staging_path = save_to_staging(rendered_content, pdf_path, metadata)
        
        if args.dry_run:
            print("\n📝 DRY RUN - Fax content preview:")
            print("=" * 60)
            print(rendered_content)
            print("=" * 60)
            print(f"\n📁 Preview saved to: {staging_path}")
            print("\nTo actually send, run without --dry-run flag")
        else:
            # Send the fax
            result = send_fax_telnyx(args.to, pdf_path)
            
            # Save to outbox
            save_to_outbox(pdf_path, {**metadata, **result})
            
            # Log to GHL if configured
            if os.getenv("GHL_OUTBOUND_WEBHOOK_URL"):
                try:
                    notify_ghl_outbound(result, args.to)
                    print("✅ Logged to GoHighLevel")
                except Exception as e:
                    logger.error("ghl_logging_failed", error=str(e))
            
            print("\n✅ Fax sent successfully!")
            print(f"   Fax ID: {result['fax_id']}")
            print(f"   To: {result['to']}")
            print(f"   Status: {result['status']}")
        
    except Exception as e:
        logger.exception("error", error=str(e))
        print(f"\n❌ Error: {e}")
        sys.exit(1)


def notify_ghl_outbound(fax_result: dict, to_number: str):
    """
    Send webhook to GHL to record the outbound fax.
    
    This requires a GHL Automation Workflow:
    Trigger: Inbound Webhook
    Action: Add Note / Create Task / Send SMS
    """
    import requests
    
    webhook_url = os.getenv("GHL_OUTBOUND_WEBHOOK_URL")
    if not webhook_url:
        return

    payload = {
        "event": "fax_sent",
        "direction": "outbound",
        "to_number": to_number,
        "fax_id": fax_result.get("fax_id"),
        "status": fax_result.get("status"),
        "timestamp": datetime.now().isoformat(),
        "details": f"Fax sent via CLI/HotFolder. ID: {fax_result.get('fax_id')}"
    }
    
    requests.post(webhook_url, json=payload, timeout=5)
    logger.info("ghl_outbound_logged", url=webhook_url)



if __name__ == "__main__":
    main()
