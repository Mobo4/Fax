#!/usr/bin/env python3
"""
AI Fax Content Generator

Generate personalized fax content using Claude/GPT with template context.

Usage:
    # Generate content for a specific provider
    python scripts/generate_fax.py --template referral_introduction \
        --provider-name "Dr. John Smith" \
        --provider-specialty "Optometrist" \
        --context "Focus on keratoconus patients"
    
    # Generate for multiple providers from list
    python scripts/generate_fax.py --template specialty_services \
        --list data/lists/optometrists.csv \
        --context "Announce new scleral lens fitting"
"""

import os
import sys
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml
import anthropic
import requests
from dotenv import load_dotenv
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


def get_sender_info() -> dict:
    """Get sender information from config or environment."""
    templates_config = load_config("templates")
    sender = templates_config.get("default_sender", {})
    
    return {
        "sender_name": sender.get("name", os.getenv("SENDER_NAME", "")),
        "sender_phone": sender.get("phone", os.getenv("SENDER_PHONE", "")),
        "sender_fax": sender.get("fax", os.getenv("SENDER_FAX", "")),
        "sender_address": sender.get("address", os.getenv("SENDER_ADDRESS", "")),
        "sender_email": sender.get("email", os.getenv("SENDER_EMAIL", "")),
        "opt_out_email": sender.get("opt_out_email", os.getenv("SENDER_OPTOUT_EMAIL", "")),
    }


def generate_fax_content_claude(
    template_content: str,
    template_config: dict,
    provider_info: dict,
    campaign_context: str,
    sender_info: dict
) -> str:
    """Generate personalized fax content using Claude API."""
    
    # Get AI generation config
    templates_config = load_config("templates")
    ai_config = templates_config.get("ai_generation", {})
    system_prompt = ai_config.get("system_prompt", "You are a professional medical copywriter.")
    max_tokens = ai_config.get("parameters", {}).get("max_tokens", 1000)
    temperature = ai_config.get("parameters", {}).get("temperature", 0.7)

    user_prompt = f"""
Generate personalized fax content based on the following template and context.

## TEMPLATE (use as structure guide, personalize the content):
{template_content}

## PROVIDER INFORMATION:
- Name: {provider_info.get('name', 'Healthcare Provider')}
- Specialty: {provider_info.get('specialty', 'General Practice')}
- Practice: {provider_info.get('practice', 'N/A')}
- Location: {provider_info.get('location', 'N/A')}

## CAMPAIGN CONTEXT (specific goals for this fax):
{campaign_context}

## SENDER INFORMATION (must include in fax):
- Practice: {sender_info['sender_name']}
- Phone: {sender_info['sender_phone']}
- Fax: {sender_info['sender_fax']}
- Address: {sender_info['sender_address']}
- Email: {sender_info['sender_email']}
- Opt-out Email: {sender_info['opt_out_email']}

## REQUIREMENTS:
1. Professional healthcare communication tone
2. MUST include opt-out notice at the bottom (TCPA required)
3. MUST include sender identification (name, phone, address)
4. Clear value proposition for the provider
5. Specific call to action
6. Keep to 1 page maximum (under 400 words)
7. Use Markdown formatting
8. Personalize based on provider specialty and context

Generate the complete fax content in Markdown format:
"""
    messages = [{"role": "user", "content": user_prompt}]

    # DeepSeek primary (OpenAI-compatible)
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        resp = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"},
            json={"model": "deepseek-chat", "messages": messages,
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"]

    # Anthropic fallback
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        raise ValueError("No LLM API key set (DEEPSEEK_API_KEY or ANTHROPIC_API_KEY)")
    client = anthropic.Anthropic(api_key=anthropic_key)
    response = client.messages.create(
        model=ai_config.get("model", "claude-3-5-sonnet-20241022"),
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


def validate_generated_content(content: str, sender_info: dict) -> list[str]:
    """Validate that generated content meets TCPA requirements."""
    errors = []
    
    # Check opt-out notice
    opt_out_keywords = ["opt-out", "optout", "unsubscribe", "remove", "stop receiving"]
    if not any(kw in content.lower() for kw in opt_out_keywords):
        errors.append("Missing opt-out notice")
    
    # Check sender identification
    if sender_info["sender_name"] not in content:
        errors.append("Missing sender name")
    
    if sender_info["sender_phone"] not in content:
        errors.append("Missing sender phone")
    
    # Word count check (approximate page length)
    word_count = len(content.split())
    if word_count > 600:
        errors.append(f"Content too long ({word_count} words, recommend under 400)")
    
    return errors


def save_generated_content(
    content: str,
    provider_info: dict,
    template_id: str,
    campaign_context: str
) -> Path:
    """Save generated content to staging for review."""
    staging_dir = PROJECT_ROOT / "staging" / "generated_faxes"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    provider_slug = provider_info.get("name", "unknown").replace(" ", "_").replace(".", "")[:20]
    base_name = f"{timestamp}_{template_id}_{provider_slug}"
    
    # Save content
    content_path = staging_dir / f"{base_name}.md"
    content_path.write_text(content)
    
    # Save metadata
    metadata = {
        "template_id": template_id,
        "provider": provider_info,
        "campaign_context": campaign_context,
        "generated_at": datetime.now().isoformat(),
        "content_path": str(content_path),
        "word_count": len(content.split()),
        "status": "pending_review"
    }
    
    metadata_path = staging_dir / f"{base_name}_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    
    return content_path


def load_provider_list(list_path: Path) -> list[dict]:
    """Load providers from CSV file."""
    import csv
    
    providers = []
    with open(list_path, newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            providers.append({
                "name": row.get("name", row.get("provider_name", "")),
                "specialty": row.get("specialty", ""),
                "practice": row.get("practice", row.get("practice_name", "")),
                "fax": row.get("fax", ""),
                "location": row.get("city", "") + ", " + row.get("state", "")
            })
    
    return providers


def main():
    parser = argparse.ArgumentParser(description="Generate AI-powered fax content")
    parser.add_argument("--template", required=True, help="Template ID")
    parser.add_argument("--provider-name", help="Provider name (for single generation)")
    parser.add_argument("--provider-specialty", help="Provider specialty")
    parser.add_argument("--practice-name", help="Practice name")
    parser.add_argument("--list", help="Path to provider list CSV (for batch generation)")
    parser.add_argument("--context", default="General outreach", help="Campaign context/goal")
    parser.add_argument("--limit", type=int, default=5, help="Limit batch generation count")
    args = parser.parse_args()
    
    # Load template
    template_content, template_config = load_template(args.template)
    sender_info = get_sender_info()
    
    # Check for API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ Error: ANTHROPIC_API_KEY not set in .env file")
        sys.exit(1)
    
    providers = []
    
    if args.list:
        # Batch mode from list
        list_path = Path(args.list)
        if not list_path.exists():
            print(f"❌ List file not found: {list_path}")
            sys.exit(1)
        providers = load_provider_list(list_path)[:args.limit]
        
    elif args.provider_name:
        # Single provider mode
        providers = [{
            "name": args.provider_name,
            "specialty": args.provider_specialty or "",
            "practice": args.practice_name or "",
            "location": ""
        }]
    else:
        print("❌ Either --provider-name or --list is required")
        sys.exit(1)
    
    print(f"\n🤖 Generating {len(providers)} fax(es) with template: {args.template}")
    print(f"📋 Context: {args.context}\n")
    
    generated = []
    
    for i, provider in enumerate(providers, 1):
        print(f"[{i}/{len(providers)}] Generating for {provider['name']}...")
        
        try:
            # Generate content
            content = generate_fax_content_claude(
                template_content=template_content,
                template_config=template_config,
                provider_info=provider,
                campaign_context=args.context,
                sender_info=sender_info
            )
            
            # Validate
            errors = validate_generated_content(content, sender_info)
            if errors:
                print(f"   ⚠️  Validation warnings: {errors}")
            
            # Save to staging
            content_path = save_generated_content(
                content=content,
                provider_info=provider,
                template_id=args.template,
                campaign_context=args.context
            )
            
            generated.append({
                "provider": provider["name"],
                "path": str(content_path),
                "errors": errors
            })
            
            print(f"   ✅ Saved to: {content_path}")
            
        except Exception as e:
            logger.error("generation_failed", provider=provider["name"], error=str(e))
            print(f"   ❌ Error: {e}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"✅ Generated {len(generated)} fax(es)")
    print(f"📁 Output: staging/generated_faxes/")
    print(f"\nNext steps:")
    print(f"  1. Review generated content in staging/generated_faxes/")
    print(f"  2. Run send_fax.py with --dry-run to preview")
    print(f"  3. Send with send_fax.py (no --dry-run)")


if __name__ == "__main__":
    main()
