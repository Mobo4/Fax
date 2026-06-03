# CLAUDE.md - Healthcare Fax Marketing System

> **ROLE:** You are a 10x Fax Marketing Expert building a HIPAA-compliant, AI-powered fax automation system for healthcare provider outreach.

## 🎯 PROJECT OVERVIEW

This system automates fax-based marketing to healthcare providers (PCPs, Optometrists, Ophthalmologists, Private ODs) with:
- **AI-Generated Faxes**: GPT/Claude generates personalized fax content
- **Webhook Receivers**: Incoming faxes → Google Drive → OCR → Patient Chart
- **List Management**: Integration with healthcare provider list vendors
- **Dashboard**: Real-time fax status, analytics, and management
- **GHL Integration**: GoHighLevel workflows for CRM automation

---

## 📁 PROJECT STRUCTURE (Primitive Architecture)

```
/Fax
├── config/                    # ⭐ CONFIG-FIRST: All magic values here
│   ├── providers.yaml         # Fax API credentials (Telnyx, SRFax, Fax.Plus)
│   ├── lists.yaml             # Healthcare list vendor configs
│   ├── templates.yaml         # Fax template configurations
│   └── compliance.yaml        # TCPA/HIPAA compliance rules
├── data/                      # ⭐ STATE SEPARATION: Data separate from code
│   ├── inbox/                 # Incoming faxes (webhook dumps)
│   ├── outbox/                # Outgoing faxes (staged for sending)
│   ├── processing/            # Currently being OCR'd or sent
│   ├── archive/               # Completed faxes
│   ├── errors/                # Failed faxes for retry
│   └── lists/                 # Provider lists (CSV/JSON)
├── staging/                   # ⭐ INTERMEDIATE ARTIFACT: Pre-send review
│   ├── generated_faxes/       # AI-generated content before approval
│   └── ocr_output/            # Extracted text before patient matching
├── templates/                 # Fax templates (Markdown → PDF)
│   ├── referral_request.md    
│   ├── new_patient_intro.md   
│   └── specialty_announcement.md
├── scripts/                   # Automation scripts
│   ├── send_fax.py            # Send fax via API
│   ├── receive_webhook.py     # Incoming fax handler
│   ├── ocr_processor.py       # OCR + patient matching
│   ├── generate_fax.py        # AI content generation
│   └── sync_gdrive.py         # Google Drive uploader
├── logs/                      # ⭐ DIFF-ABLE: Structured logs
│   └── fax_activity.md        # Markdown log for agent readability
└── dashboard/                 # Web dashboard (Next.js or React)
```

---

## 🔧 TECHNOLOGY STACK

### Fax API (Choose One)
| Provider | Pricing | Webhooks | HIPAA | Notes |
|----------|---------|----------|-------|-------|
| **Telnyx** | $0.007/page | ✅ | ✅ BAA | Best developer experience |
| **Fax.Plus** | Pay-per-page | ✅ | ✅ BAA | Great webhooks |
| **SRFax** | Subscription | Polling | ✅ BAA | HIPAA-focused |
| **iFax** | Custom | ✅ | ✅ BAA | Built-in OCR |

### Healthcare Provider Lists
| Vendor | Specialty | Fax Numbers | API |
|--------|-----------|-------------|-----|
| **CarePrecise** | All providers | ✅ Fax lists | Download |
| **Provyx** | Eye care | Custom | Contact |
| **Ampliz** | All specialties | ✅ | REST API |
| **CampaignLake** | PCPs | ✅ | Download |

### OCR & AI
- **Document AI**: Google Cloud Vision, AWS Textract, or Azure Form Recognizer
- **Content Generation**: Claude API or GPT-4 for fax content
- **Patient Matching**: Fuzzy matching against EHR/CRM data

### Integrations
- **GoHighLevel**: Inbound webhook → GHL workflow trigger
- **Google Drive**: Archive incoming faxes to folders
- **Zapier/Make**: Optional no-code connectors

---

## ⚖️ COMPLIANCE REQUIREMENTS

### TCPA (Junk Fax Prevention Act)
```yaml
required:
  - prior_express_written_consent: true  # MUST have before sending
  - opt_out_mechanism: true              # Every fax needs opt-out info
  - do_not_fax_list: true                # Maintain and honor
  - sender_identification: true          # Name, address, phone
  - accurate_header: true                # Transmission header

penalties:
  per_violation: $500-$1500
  class_action_risk: HIGH
```

### HIPAA (For Incoming Faxes with PHI)
```yaml
required:
  - business_associate_agreement: true   # BAA with fax vendor
  - encryption_at_rest: true             # Encrypted storage
  - encryption_in_transit: true          # HTTPS/TLS
  - access_controls: true                # Role-based access
  - audit_trail: true                    # Log all access
  - confidentiality_disclaimer: true     # Cover page with disclaimer

recommendations:
  - use_hipaa_fax_vendor: true           # Telnyx, SRFax, iFax
  - minimize_phi_exposure: true          # Extract only needed data
  - secure_storage: google_drive_hipaa   # BAA with Google Workspace
```

---

## 📋 WORKFLOW DIAGRAMS

### Outbound Fax Flow
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Provider    │────▸│ AI Generate  │────▸│ staging/    │
│ List (CSV)  │     │ Fax Content  │     │ review.json │
└─────────────┘     └──────────────┘     └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │ Human/Auto   │
                                         │ Approval     │
                                         └──────────────┘
                                                │
                    ┌───────────────────────────┴─────────────────┐
                    ▼                                             ▼
             ┌─────────────┐                              ┌─────────────┐
             │ Send via    │                              │ Archive to  │
             │ Telnyx API  │                              │ data/outbox │
             └─────────────┘                              └─────────────┘
                    │
                    ▼
             ┌─────────────┐
             │ Webhook:    │
             │ delivered/  │
             │ failed      │
             └─────────────┘
```

### Inbound Fax Flow
```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│ Fax         │────▸│ Webhook to   │────▸│ data/inbox/ │
│ Received    │     │ Python/Node  │     │ {fax}.pdf   │
└─────────────┘     └──────────────┘     └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │ OCR Extract  │
                                         │ Text         │
                                         └──────────────┘
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │ staging/     │
                                         │ ocr_output/  │
                                         └──────────────┘
                                                │
                    ┌───────────────────────────┴─────────────────┐
                    ▼                                             ▼
             ┌─────────────┐                              ┌─────────────┐
             │ Match to    │                              │ Archive to  │
             │ Patient     │                              │ Google Drive│
             └─────────────┘                              └─────────────┘
                    │
                    ▼
             ┌─────────────┐
             │ Attach to   │
             │ Patient     │
             │ Chart (GHL) │
             └─────────────┘
```

---

## 🏗️ IMPLEMENTATION PRIORITY

### Phase 1: Foundation (Week 1)
1. Set up Telnyx account + get fax number
2. Create webhook receiver (Python/Flask or Node/Express)
3. Basic send fax script
4. Google Drive sync for incoming faxes

### Phase 2: AI Generation (Week 2)
1. Fax templates in Markdown
2. AI content generation with Claude/GPT
3. Staging workflow for review
4. PDF generation (markdown → PDF)

### Phase 3: List Management (Week 3)
1. Import CarePrecise/Provyx lists
2. Clean and deduplicate
3. Opt-out list management
4. Segmentation by specialty

### Phase 4: Dashboard (Week 4)
1. React/Next.js dashboard
2. Fax status tracking
3. Analytics and reporting
4. Retry failed faxes

### Phase 5: Intelligence (Week 5)
1. OCR integration
2. Patient matching
3. Auto-routing to correct chart
4. GHL workflow triggers

---

## 🔐 ENVIRONMENT VARIABLES

```bash
# Fax API
TELNYX_API_KEY=
TELNYX_FAX_APP_ID=
TELNYX_FAX_NUMBER=

# Alternative: SRFax
SRFAX_ACCESS_ID=
SRFAX_ACCESS_PWD=
SRFAX_ACCOUNT_NUMBER=

# Google Drive
GOOGLE_SERVICE_ACCOUNT_JSON=
GDRIVE_INCOMING_FOLDER_ID=
GDRIVE_OUTGOING_FOLDER_ID=

# AI Content
ANTHROPIC_API_KEY=  # or OPENAI_API_KEY

# GoHighLevel
GHL_API_KEY=
GHL_LOCATION_ID=
GHL_WEBHOOK_SECRET=

# OCR
GOOGLE_VISION_CREDENTIALS=
```

---

## 🚀 QUICK START COMMANDS

```bash
# Install dependencies
pip install telnyx google-cloud-vision anthropic flask

# Start webhook receiver
python scripts/receive_webhook.py --port 8080

# Send a test fax
python scripts/send_fax.py --to "+15551234567" --template referral_request

# Process incoming faxes
python scripts/ocr_processor.py --input data/inbox --output staging/ocr_output

# Sync to Google Drive
python scripts/sync_gdrive.py --folder data/archive
```

---

## 📚 RELATED SKILLS

When working on this project, activate these skills as needed:
- `fax-marketing-healthcare` - This project's specialized skill
- `api-patterns` - REST API design
- `webhook-automation` - Webhook best practices
- `hipaa-compliance` - Healthcare security
- `ai-agents-architect` - AI content generation

---

## ⚠️ CRITICAL REMINDERS

1. **NEVER send fax without consent** - TCPA violations = $500-$1500 per fax
2. **Always include opt-out** - Phone/email/web to unsubscribe
3. **Sign BAA with fax vendor** - Required for HIPAA
4. **Test with your own number first** - Before any campaign
5. **Log everything** - Consent records, delivery status, opt-outs
