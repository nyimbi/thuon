---
name: tender_scout
description: Search African government procurement tenders and RFPs across 15 countries by sector and deadline
version: "1.0"
keywords:
  - tender
  - procurement
  - bid
  - government contract
  - RFP
  - RFQ
  - public tender
  - Kenya tender
  - government opportunity
  - supply contract
thuon:
  capability: tender_scout
  module: capabilities.tender_scout
  class: TenderScout
  method: search
  deps: [search_engine]
  category: strategy
  params:
    - name: sector
      type: str
      required: false
      default: ""
    - name: countries
      type: list
      required: false
      default: ["Kenya"]
    - name: keywords
      type: list
      required: false
      default: []
---

## Tender Scout

Use this skill when the user asks for:
- "find tenders", "procurement opportunities", "government bids"
- "RFP search", "RFQ", "ITT" (invitation to tender)
- "ICT tenders Kenya", "construction tenders East Africa"
- "find government contracts"

Searches tender portals and procurement databases across 15 African countries.

### Supported countries
Kenya, Uganda, Tanzania, Rwanda, Ethiopia, Nigeria, Ghana, South Africa,
Mozambique, Zambia, Zimbabwe, Malawi, DRC, Senegal, Ivory Coast.

### Sector examples
ICT, construction, health, education, agriculture, energy, finance, consulting,
transport, water, security.
