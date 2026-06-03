---
template_id: referral_introduction
category: outreach
compliance:
  requires_consent: true
  opt_out_required: true
  max_pages: 1
variables:
  - provider_name
  - provider_specialty
  - practice_name
---

# FAX TRANSMISSION

**TO:** {{ provider_name }}{% if provider_specialty %}, {{ provider_specialty }}{% endif %}  
{% if practice_name %}**PRACTICE:** {{ practice_name }}{% endif %}  
**FROM:** {{ sender_name }}  
**DATE:** {{ current_date }}  
**RE:** Patient Care Collaboration Opportunity

---

Dear {{ provider_name | default("Doctor", true) }},

I am reaching out from **{{ sender_name }}** to introduce our specialized eye care services and explore opportunities for patient care collaboration.

## Our Specialty Services

- **Scleral Contact Lenses** – Custom-designed for keratoconus, post-surgical, and irregular cornea patients
- **Keratoconus Management** – Comprehensive treatment including cross-linking referrals
- **Dry Eye Treatment** – Advanced therapies including IPL and LipiFlow
- **Complex Contact Lens Fitting** – For patients who have "failed" in traditional lenses

## Why Partner With Us?

Many patients with complex vision needs fall through the cracks in traditional optometry. We specialize in providing solutions for these challenging cases, allowing you to offer your patients expanded care options.

**We make referrals easy:**
- Same-week appointments for urgent cases
- Detailed reports back to you after each visit
- Co-management arrangements available

## Next Steps

If you'd like to learn more about how we can support your patients, please contact us:

📞 **Phone:** {{ sender_phone }}  
📧 **Email:** {{ sender_email }}  
📠 **Fax:** {{ sender_fax }}

We would welcome the opportunity to discuss how we can work together to provide the best possible care for your patients.

Warm regards,

**{{ sender_name }}**  
{{ sender_address }}

---

**OPT-OUT NOTICE:** To be removed from our fax list, please call {{ sender_phone }}, fax this page to {{ sender_fax }} with "REMOVE" written on it, or email {{ opt_out_email }}. We will honor your request within 10 business days.
