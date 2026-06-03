---
template_id: specialty_services
category: announcement
compliance:
  requires_consent: true
  opt_out_required: true
  max_pages: 2
variables:
  - provider_name
  - service_name
  - service_description
---

# FAX TRANSMISSION

**TO:** {{ provider_name | default("Healthcare Provider", true) }}  
**FROM:** {{ sender_name }}  
**DATE:** {{ current_date }}  
**RE:** Specialty Service Announcement – {{ service_name | default("Advanced Eye Care Services", true) }}

---

Dear {{ provider_name | default("Doctor", true) }},

We are pleased to announce **{{ service_name | default("new specialty services", true) }}** now available at {{ sender_name }}.

## Service Overview

{{ service_description | default("Our practice has expanded to offer cutting-edge treatments for patients with complex eye care needs.", true) }}

## Services We Offer

### Scleral Contact Lenses
- Custom-designed for irregular corneas
- Solutions for keratoconus, post-LASIK, and post-transplant patients
- Breakthrough "90-Degree Rule" fitting technique for improved comfort

### Keratoconus Management
- Early detection and monitoring
- Contact lens solutions from early to advanced stages
- Coordination with corneal specialists for cross-linking when appropriate

### Dry Eye Disease Treatment
- Comprehensive dry eye evaluation
- Advanced treatments including IPL, LipiFlow, and autologous serum
- Customized treatment protocols

### Complex Contact Lens Cases
- Failed previous attempts? We specialize in these patients
- Multifocal scleral lenses for presbyopia with irregular corneas
- Post-surgical rehabilitation lenses

## Patient Referral Process

Referring a patient is simple:

1. **Fax** patient information to {{ sender_fax }}
2. **Call** our referral line at {{ sender_phone }}
3. **Email** referrals to {{ sender_email }}

**We provide:**
- Appointment within 1-2 weeks (urgent cases seen sooner)
- Detailed consultation notes faxed back to you
- Ongoing communication about patient progress

## Contact Us

📞 {{ sender_phone }}  
📠 {{ sender_fax }}  
📧 {{ sender_email }}  
📍 {{ sender_address }}

---

We look forward to working together to provide exceptional care for your patients with complex vision needs.

Sincerely,

**{{ sender_name }}**

---

**OPT-OUT NOTICE:** To stop receiving faxes from us, please call {{ sender_phone }}, reply to this fax with "REMOVE" written on it, or email {{ opt_out_email }}. Your request will be honored within 10 business days.
