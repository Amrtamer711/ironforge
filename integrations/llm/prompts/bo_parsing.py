# BO Parsing prompts - Document classification and parsing

import config


def get_classification_prompt(user_message: str = "") -> str:
    """
    Generate the document classification prompt.

    Args:
        user_message: Optional user message for context

    Returns:
        The classification prompt string
    """
    user_context = f"\n\n**USER'S MESSAGE:** \"{user_message}\"\nUse this context to better understand the user's intent." if user_message else ""

    return f"""You are classifying a document as either a BOOKING_ORDER or ARTWORK.

**IMPORTANT BIAS:** Default to classifying as ARTWORK unless you see CLEAR booking order characteristics.

**BOOKING_ORDER characteristics (must have MULTIPLE of these):**
- Explicit booking/order reference numbers (e.g., "BO #12345", "Order #", "Booking Ref")
- Tables with columns: Location, Start Date, End Date, Duration, Costs
- Financial terms: Net, VAT, Gross, SLA deduction, Payment terms
- Client/Agency names with campaign details
- Multiple locations listed with dates and pricing

**ARTWORK characteristics (if you see ANY of these, classify as ARTWORK):**
- Visual designs, graphics, logos, imagery
- Product photos or promotional content
- Brand assets, mockups, creative designs
- Marketing materials
- No tabular pricing/booking data
{user_context}

**Classification rules:**
1. If you see ANY visual design elements → ARTWORK (high confidence)
2. If you see a table with locations/dates/pricing → BOOKING_ORDER (high confidence)
3. If unclear or minimal text → ARTWORK (medium confidence)
4. If it's a mix → ARTWORK (low confidence)
5. If user's message mentions "mockup", "billboard", "creative", "artwork" → ARTWORK (high confidence)
6. If user's message mentions "booking order", "BO", "parse" → BOOKING_ORDER (higher confidence)

**COMPANY DETECTION (for BOOKING_ORDER only):**
If classified as BOOKING_ORDER, determine the company:
- Look for "Backlite" or "BackLite" or "backlite" anywhere in document → company: "backlite"
- Look for "Viola" or "viola" anywhere in document → company: "viola"
- Check user's message for company name too
- If unclear, default to "backlite"

Analyze the uploaded file and respond with:
- classification: "BOOKING_ORDER" or "ARTWORK"
- confidence: "high", "medium", or "low"
- company: "backlite" or "viola" (ONLY if classification is BOOKING_ORDER, otherwise null)
- reasoning: Brief explanation (1 sentence)
"""


def get_backlite_parsing_prompt() -> str:
    """Build Backlite-specific parsing prompt"""
    # Get static and digital locations for Backlite
    static_locations = []
    digital_locations = []
    for key, meta in config.LOCATION_METADATA.items():
        display_name = meta.get('display_name', key)
        if meta.get('display_type', '').lower() == 'static':
            static_locations.append(f"{display_name} ({key})")
        elif meta.get('display_type', '').lower() == 'digital':
            digital_locations.append(f"{display_name} ({key})")

    static_list = ", ".join(static_locations) if static_locations else "None"
    digital_list = ", ".join(digital_locations) if digital_locations else "None"

    location_context = f"""
**BACKLITE LOCATION REFERENCE (Use this to identify location types):**

NOTE: This list contains ALMOST ALL Backlite locations, but not necessarily every single one. If you see a location not in this list, use context clues from the BO to determine its type.

🔴 **DIGITAL LOCATIONS** (LED screens - get upload fees only):
{digital_list}

🔵 **STATIC LOCATIONS** (Traditional billboards - get production fees only):
{static_list}

Use this reference to determine if a location should have upload fees (digital) or production fees (static).
If a location isn't listed, make an intelligent guess based on naming patterns and fee descriptions in the BO.
"""

    currency_context = f"""
**CURRENCY HANDLING (STATIC CONFIG - EASY TO UPGRADE LATER):**
{config.CURRENCY_PROMPT_CONTEXT}

- ALWAYS include a top-level field `currency` with the 3-letter ISO code (default {config.DEFAULT_CURRENCY}).
- Keep all numeric fields as pure numbers without symbols.
- If the document clearly uses a non-{config.DEFAULT_CURRENCY} currency, set `currency` accordingly and keep the numbers as shown.
- Do NOT guess exchange rates. The backend handles conversions using the table above when instructed.
- If no currency is specified, assume {config.DEFAULT_CURRENCY}.
"""

    return f"""You are an expert at extracting data from BACKLITE booking orders - a billboard/outdoor advertising company.

**TAKE YOUR TIME AND BE INTELLIGENT:**
These booking orders come from EXTERNAL clients and may have horrible, inconsistent structures. Do NOT rush. Carefully dissect the entire document, understand the business context, and intelligently parse the information. Think step-by-step about what you're seeing.
{location_context}
{currency_context}
**CRITICAL BILLBOARD INDUSTRY CONTEXT:**

**Understanding Billboard Purchases:**
Booking orders (BOs) are contracts where clients purchase billboard advertising space. Key concepts:

1. **⚠️ CRITICAL: Bundled vs Separate Payments - DON'T DOUBLE COUNT!**

   **BUNDLED LOCATIONS (Split the payment):**
   When multiple locations appear TOGETHER in ONE row/line with ONE shared payment:
   - Example: "UAE02 & UAE03 - AED 320,000" → SPLIT 320k: UAE02=160k, UAE03=160k
   - Example: "Package (UAE03, UAE04, UAE05) - AED 480,000" → SPLIT: 160k each
   - Signals: Locations connected with "&", comma, or grouped in one table row
   - **DEFAULT BEHAVIOR:** If you see ONE total payment for ALL locations with no individual amounts specified, SPLIT IT EVENLY across all locations
   - Example: Document shows 5 locations with total payment of AED 500,000 and no per-location breakdown → Split evenly: 100k each

   **SEPARATE LOCATIONS (Full payment):**
   When a location has its own dedicated row with its own payment:
   - Example: "UAE21 - AED 120,000" on separate line → UAE21 gets full 120k

   **MIXED SCENARIO (Most common!):**
   ```
   Row 1: UAE02 & UAE03 - AED 320,000  → Split: UAE02=160k, UAE03=160k
   Row 2: UAE21 - AED 120,000          → Separate: UAE21=120k
   Total check: 160k + 160k + 120k = 440k ✅
   ```

   **❌ WRONG (Double counting):**
   ```
   UAE02=320k, UAE03=320k, UAE21=120k = 760k
   This is WRONG because UAE02 & UAE03 share the 320k!
   ```

   **How to identify bundled payments:**
   - Multiple location codes in same row (UAE02 & UAE03)
   - Package name covering multiple locations
   - Locations with "&" or "/" between them
   - Table structure: one payment cell spanning multiple location cells

2. **Fee Types (NOT locations - extract separately):**
   - **Municipality Fee:** Applies to ALL locations as a regulatory fee. Extract this as a separate global fee, NOT as a location
   - **Upload Fee:** Only for DIGITAL billboards (screens). This is the cost to upload creative content. NOT a location.
   - **Production Fee:** Only for STATIC billboards (printed). This is the cost to produce/print the creative. NOT a location.
   - These fees may appear mixed in with location rows - use intelligence to identify them

3. **SLA (Service Level Agreement) %:**
   - This is a DEDUCTION percentage (e.g., "0.4%" = 0.004 as decimal, "10%" = 0.10 as decimal)
   - Usually appears as a percentage field or row in the BO (look for "SLA", "SLA%", "Service Level Agreement")
   - **CRITICAL:** If you see an "SLA" field or row with a percentage, ALWAYS extract it! Don't leave it as null/0
   - **CHECK USER MESSAGE FIRST:** User often provides SLA in their message (e.g., "10% SLA", "SLA is 5%") - this OVERRIDES the document
   - Applied ONLY to the net rental amount (rental + production/upload fees + municipality fees)
   - SLA deduction happens BEFORE VAT is calculated
   - Formula: Net after SLA = Net rental - (Net rental × SLA%)
   - Then VAT is applied: Gross = (Net after SLA) × 1.05

4. **Location Types:**
   - **Digital/LED screens:** Get upload fees, no production fees
   - **Static billboards:** Get production fees, no upload fees
   - The document may not explicitly label these - use context clues

**FINANCIAL CALCULATION FLOW (CRITICAL - USE THIS TO IDENTIFY FEES):**

The standard calculation flow in billboard BOs is:
1. **Net Rental Amount** = Sum of all location rentals (e.g., AED 460,000)
2. **+ Production/Upload Fee** = Fee for creative production/upload (e.g., AED 2,000)
3. **+ Municipality Fee (DM Fee)** = Dubai Municipality regulatory fee (e.g., AED 520)
4. **= Net Amount** = Rental + Production + DM (e.g., AED 462,520)
5. **- SLA Deduction** = Net Amount × SLA% (e.g., 462,520 × 10% = AED 46,252)
6. **= Net Rental (after SLA)** = Net Amount - SLA (e.g., AED 414,000)
7. **+ VAT (5%)** = Usually applied to (Rental + Production), NOT DM (e.g., 5% of 462,000 = AED 23,126)
8. **= Gross Total** = Net Rental + VAT (e.g., AED 485,646)

**CRITICAL: How to identify Production/Upload Fees:**
- Look for line items labeled: "Production Fee", "Upload Fee", "Production Cost", "Upload Cost", "Creative Fee", "Net Production fee"
- Production/Upload fees are typically MEDIUM amounts (thousands, e.g., AED 1,000-5,000 per location or total)
- May appear in the costs table as a separate row, or in a summary section
- For DIGITAL screens: called "Upload Fee"
- For STATIC billboards: called "Production Fee" or "Production Cost"
- **IMPORTANT:** If shown per-location, ADD them ALL up into ONE global total
- If document shows "Production: AED 2,000" or "Upload: AED 1,500", extract this value
- If unclear or not found, use 0 (don't guess)

**CRITICAL: How to identify Municipality Fee:**
- Look for line items labeled: "DM Fee", "Municipality Fee", "Dubai Municipality", "Govt Fee"
- Municipality fee is typically a SMALL amount (hundreds to low thousands, not tens of thousands)
- If you see a breakdown showing: Rental + Production + Small Fee = Net Amount, that small fee is likely Municipality
- The Net Amount shown often equals: Rental + Production/Upload + Municipality
- Municipality fee may appear in a separate row in the costs table, or in a summary section

**Example:**
If you see:
- Net Rental amount: AED 460,000
- Net Production fee: AED 2,000
- Net DM fee: AED 520
- Net amount: AED 462,520 ← This confirms the municipality fee!
- VAT: AED 23,126
- Gross: AED 485,646

This tells you the municipality fee is AED 520.

**EXTRACTION RULES:**

**Be Intelligent About:**
- **Bundled payments:** If one payment covers multiple locations, split it across them
- **Fee identification:** Distinguish between location rentals vs fees (municipality/upload/production)
- **Inconsistent structures:** Tables may be messy, merged cells, unclear headers - parse carefully
- **Missing data:** Use null for truly missing fields, but try hard to find the data first
- **Calculations:** Extract what's shown, but understand the calculation logic to catch errors

**Format Rules:**
1. Dates: Convert to YYYY-MM-DD format (e.g., "21st Feb 2025" → "2025-02-21")
2. Percentages: Convert to decimal (e.g., "5%" → 0.05, "0.4%" → 0.004)
3. Numbers: Pure numbers without currency symbols (e.g., "AED 295,596.00" → 295596.00)
4. Asset codes: Extract as list: ["UAE02", "UAE03", "UAE21"]
5. **Text fields - Proper capitalization and formatting:**
   - **Sales person names:** Proper title case (e.g., "john smith" → "John Smith", "SARAH JONES" → "Sarah Jones")
   - **Client names:** Proper case for company names (e.g., "EMAAR PROPERTIES" → "Emaar Properties")
   - **Brand/Campaign:** Proper case (e.g., "mercedes benz campaign" → "Mercedes Benz Campaign")
   - **Location names:** Use proper display names from reference list or title case (e.g., "THE DUBAI GATEWAY" → "The Dubai Gateway")
   - **Payment terms:** Standard format (e.g., "60 DAYS PDC" → "60 days PDC", "30 days credit" → "30 days credit")
   - **Category:** Proper case (e.g., "real estate" → "Real Estate", "FMCG" → "FMCG")
   - **General rule:** Make all text look professional and properly formatted as it will appear in official documents

**DOCUMENT STRUCTURE TO LOOK FOR:**

**Header Information:**
- BO Number (Booking Order reference - usually "BO-XXX" or "DPD-XXX")
- BO Date (when the BO was created)
- Client (company name purchasing the advertising)
  **IMPORTANT:** Client is the BUYER, NOT the seller:
  - Client = Company buying billboard advertising (e.g., "Emaar Properties", "Nestlé", "Mercedes-Benz")
  - DO NOT extract "Backlite" or "Viola" as the client - these are the SERVICE PROVIDERS (sellers)
  - Look for "From:", "Client:", "Advertiser:", or the company requesting the campaign
  - Client is who is PAYING for the billboard space, not who is selling it
- Agency (advertising agency, may be blank)
- Brand/Campaign (the advertised brand or campaign name)
  **IMPORTANT:** Use intelligent inference if brand/campaign is not explicitly stated:
  - If client is "Gucci LLC" → brand is likely "Gucci"
  - If client is "Emaar Properties PJSC" → brand is likely "Emaar"
  - If client is "Dubai Properties Development L.L.C" → brand is likely "Dubai Properties"
  - Extract the core brand name from the client company name by removing corporate suffixes like LLC, PJSC, L.L.C, Inc, Ltd, etc.
  - Only use the full client name as brand if there's truly no brand information anywhere in the document
- Category (the client's main industry/sector)
  **IMPORTANT:** Category represents the CLIENT'S industry, not the campaign type:
  - If client is "Emaar Properties PJSC" → category is "Real Estate"
  - If client is "Nestlé Middle East" → category is "FMCG" (Fast-Moving Consumer Goods)
  - If client is "Mercedes-Benz UAE" → category is "Automotive"
  - If client is "Emirates NBD" → category is "Banking/Finance"
  - Common categories: Real Estate, FMCG, Automotive, Banking/Finance, Hospitality, Retail, Healthcare, Technology, Entertainment
  - Infer from the client company name if not explicitly stated in the BO

**Location/Asset Details (usually in a table):**
For EACH billboard location, extract:
- Location name/code: **EXTRACT AS NATURAL LANGUAGE DISPLAY NAME**
  - ✅ CORRECT: "The Dubai Gateway", "Dubai Jawhara", "The Dubai Frame", "UAE02", "UAE03"
  - ❌ WRONG: "dubai_gateway", "dubai_jawhara", "dubai_frame" (these are system keys, not names!)
  - ❌ WRONG: "UAE02 (Unipole 16x8, Jebel Ali)", "The Gateway (LED)" (remove technical descriptions)
  - **Use the natural language name from the location reference list above** (e.g., "The Dubai Gateway" not "dubai_gateway")
  - Remove any parenthetical descriptions, dimensions, area names, or technical specs
  - If document shows "The Dubai Gateway (LED Screen)" → extract as "The Dubai Gateway"
  - If document shows "UAE02 (Unipole 16x8, Jebel Ali) & UAE03 (Billboard, Al Quoz)" → extract as TWO locations: "UAE02" and "UAE03"
  - Match the location to the display name from the reference list above when possible
- Start date (campaign start date)
- End date (campaign end date)
- Campaign duration **IMPORTANT:** Calculate and format intelligently:
  - Calculate number of days between start and end date
  - **Format rules (approximate to nearest unit):**
    * 28-31 days → "1 month"
    * 56-62 days → "2 months"
    * 84-93 days → "3 months"
    * 14-15 days → "2 weeks"
    * 21-22 days → "3 weeks"
    * 7-8 days → "1 week"
    * Only use "X days" if it doesn't fit these approximations
  - Examples: 30 days = "1 month", 15 days = "2 weeks", 60 days = "2 months", 10 days = "10 days"
  - If explicitly stated in BO (rare), use that value; otherwise calculate from dates
- Net amount (rental cost for THIS location - may need to split bundled payments)
- Production/Upload cost (if specified per-location)
- Type (digital vs static - if mentioned)

**CRITICAL: Understanding the Data Structure**

Booking orders have TWO types of costs:

1. **Per-Location Rental Amounts** (in locations array):
   - Each location has its own rental amount (e.g., UAE02: AED 80,000, UAE03: AED 80,000)
   - This is ONLY the rental cost for that specific billboard
   - Extract as `net_amount` for each location
   - **IMPORTANT:** If document shows ONLY a total rental amount with no per-location breakdown, SPLIT IT EVENLY across all locations
   - Example: 5 locations with total rental AED 500,000 → Each location gets AED 100,000

2. **GLOBAL Fees** (top-level fields, NOT per-location):
   - **municipality_fee**: Dubai Municipality regulatory fee for the ENTIRE booking
     - Look for: "DM Fee", "Municipality Fee", "Dubai Municipality", "Net DM fee"
     - Typically a small amount (hundreds to low thousands)
     - ONE total for all locations combined
     - **If document shows per-location DM fees:** ADD them all up into ONE total
     - Example: UAE02: AED 200, UAE03: AED 200, UAE21: AED 120 → municipality_fee: 520

   - **production_upload_fee**: Total production/upload cost for ALL locations
     - Look for: "Production Fee", "Upload Fee", "Production Cost", "Net Production fee"
     - This is production fee (for static) + upload fee (for digital) combined into ONE total
     - ONE total for all locations combined
     - **If document shows per-location fees:** ADD them all up into ONE total
     - Example: UAE02 upload: AED 500, UAE03 upload: AED 500, UAE21 production: AED 1000 → production_upload_fee: 2000

**CRITICAL:** Each location only stores its rental amount. ALL fees are GLOBAL single totals, NOT per-location values.
Even if the source document lists fees per location, you MUST sum them into single global totals.

**The Math:**
- Sum of all location rental amounts (e.g., 80,000 + 80,000 + 120,000 = 280,000)
- + production_upload_fee (e.g., 2,000)
- + municipality_fee (e.g., 520)
- = net_pre_vat (e.g., 282,520)

**Financial Totals:**
- Net amount (Rental + Production + Municipality, before SLA and VAT)
- VAT amount (5% tax, usually on Rental + Production, not Municipality)
- Gross amount (total including VAT)
- SLA % (deduction percentage, e.g., 10% = 0.10)

**Additional Information:**
- Payment terms (e.g., "60 days PDC", "30 days credit") - **CHECK USER MESSAGE** as this is often provided there
- Salesperson name - **CHECK USER MESSAGE** as user may specify who the sales person is
- Commission %

**CRITICAL NOTES:**
- If you see "Municipality Fee" or "Upload Fee" in the locations table, extract it separately as a fee, NOT as a location
- When multiple locations share one payment, split the amount across them intelligently
- Think about whether each line item is a location rental or a fee
- The structure may be messy - take your time to understand it
- Extract what you see, but understand the business logic to validate your extraction"""


def get_viola_parsing_prompt() -> str:
    """Build Viola-specific parsing prompt"""
    # TODO: Add Viola locations here when available
    viola_locations = "01A, 01B, 02A, 02B, 02C, 03A, 03B, 04A, 04B, 05A, 05B, 06A, 06B, 07A, 07B, 08A, 08B, 09A, 09B, 10A, 10B, 11A, 11B, 12A, 12B, 13A, 13B, 14A, 14B, 15A, 15B, 15C"

    return f"""You are an expert at extracting data from VIOLA booking orders - a billboard/outdoor advertising company.

**TAKE YOUR TIME AND BE INTELLIGENT:**
These booking orders come from EXTERNAL clients and may have horrible, inconsistent structures. Do NOT rush. Carefully dissect the entire document, understand the business context, and intelligently parse the information. Think step-by-step about what you're seeing.

**VIOLA LOCATION CODES:**
Viola uses alphanumeric location codes. Common codes include: {viola_locations}

**CURRENCY HANDLING (STATIC CONFIG - EASY TO UPGRADE LATER):**
{config.CURRENCY_PROMPT_CONTEXT}

- ALWAYS include a top-level field `currency` with the 3-letter ISO code (default {config.DEFAULT_CURRENCY}).
- Keep all numeric fields as pure numbers without symbols.
- If the document clearly uses a non-{config.DEFAULT_CURRENCY} currency, set `currency` accordingly and keep the numbers as shown.
- Do NOT guess exchange rates. The backend handles conversions using the table above when instructed.
- If no currency is specified, assume {config.DEFAULT_CURRENCY}.

**CRITICAL FOR VIOLA LOCATIONS:**
- Extract ONLY the location CODE (e.g., "04B", "03A", "15C")
- Viola locations often have descriptive names, but we only want the CODE
- Examples:
  - If document shows "Viola 04B - Sheikh Zayed Road Tower" → extract "04B"
  - If document shows "03A Al Barsha Mall" → extract "03A"
  - If document shows "Location 15C - Dubai Marina" → extract "15C"
- Look for the alphanumeric pattern (2 digits + optional letter)
- Strip away any descriptive text, addresses, or area names

**CRITICAL BILLBOARD INDUSTRY CONTEXT:**

**Understanding Billboard Purchases:**
Booking orders (BOs) are contracts where clients purchase billboard advertising space. Key concepts:

1. **⚠️ CRITICAL: Bundled vs Separate Payments - DON'T DOUBLE COUNT!**

   **BUNDLED LOCATIONS (Split the payment):**
   When multiple locations appear TOGETHER in ONE row/line with ONE shared payment:
   - Example: "04B & 03A - AED 320,000" → SPLIT 320k: 04B=160k, 03A=160k
   - Example: "Package (03A, 03B, 04A) - AED 480,000" → SPLIT: 160k each
   - Signals: Locations connected with "&", comma, or grouped in one table row

   **SEPARATE LOCATIONS (Full payment):**
   When a location has its own dedicated row with its own payment:
   - Example: "15C - AED 120,000" on separate line → 15C gets full 120k

   **MIXED SCENARIO (Most common!):**
   ```
   Row 1: 04B & 03A - AED 320,000  → Split: 04B=160k, 03A=160k
   Row 2: 15C - AED 120,000        → Separate: 15C=120k
   Total check: 160k + 160k + 120k = 440k ✅
   ```

   **❌ WRONG (Double counting):**
   ```
   04B=320k, 03A=320k, 15C=120k = 760k
   This is WRONG because 04B & 03A share the 320k!
   ```

   **How to identify bundled payments:**
   - Multiple location codes in same row (04B & 03A)
   - Package name covering multiple locations
   - Locations with "&" or "/" between them
   - Table structure: one payment cell spanning multiple location cells

2. **Fee Types (NOT locations - extract separately):**
   - **Municipality Fee:** Applies to ALL locations as a regulatory fee. Extract this as a separate global fee, NOT as a location
   - **Upload Fee:** For digital screens. This is the cost to upload creative content. NOT a location.
   - **Production Fee:** For static billboards. This is the cost to produce/print the creative. NOT a location.
   - These fees may appear mixed in with location rows - use intelligence to identify them

3. **SLA (Service Level Agreement) %:**
   - This is a DEDUCTION percentage (e.g., "0.4%" = 0.004 as decimal, "10%" = 0.10 as decimal)
   - Usually appears as a percentage field or row in the BO (look for "SLA", "SLA%", "Service Level Agreement")
   - **CRITICAL:** If you see an "SLA" field or row with a percentage, ALWAYS extract it! Don't leave it as null/0
   - **CHECK USER MESSAGE FIRST:** User often provides SLA in their message (e.g., "10% SLA", "SLA is 5%") - this OVERRIDES the document
   - Applied ONLY to the net rental amount (rental + production/upload fees + municipality fees)
   - SLA deduction happens BEFORE VAT is calculated
   - Formula: Net after SLA = Net rental - (Net rental × SLA%)
   - Then VAT is applied: Gross = (Net after SLA) × 1.05

**FINANCIAL CALCULATION FLOW (CRITICAL - USE THIS TO IDENTIFY FEES):**

The standard calculation flow in billboard BOs is:
1. **Net Rental Amount** = Sum of all location rentals (e.g., AED 460,000)
2. **+ Production/Upload Fee** = Fee for creative production/upload (e.g., AED 2,000)
3. **+ Municipality Fee (DM Fee)** = Dubai Municipality regulatory fee (e.g., AED 520)
4. **= Net Amount** = Rental + Production + DM (e.g., AED 462,520)
5. **- SLA Deduction** = Net Amount × SLA% (e.g., 462,520 × 10% = AED 46,252)
6. **= Net Rental (after SLA)** = Net Amount - SLA (e.g., AED 414,000)
7. **+ VAT (5%)** = Usually applied to (Rental + Production), NOT DM (e.g., 5% of 462,000 = AED 23,126)
8. **= Gross Total** = Net Rental + VAT (e.g., AED 485,646)

**CRITICAL: How to identify Production/Upload Fees:**
- Look for line items labeled: "Production Fee", "Upload Fee", "Production Cost", "Upload Cost", "Creative Fee", "Net Production fee"
- Production/Upload fees are typically MEDIUM amounts (thousands, e.g., AED 1,000-5,000 per location or total)
- May appear in the costs table as a separate row, or in a summary section
- **IMPORTANT:** If shown per-location, ADD them ALL up into ONE global total
- If document shows "Production: AED 2,000" or "Upload: AED 1,500", extract this value
- If unclear or not found, use 0 (don't guess)

**CRITICAL: How to identify Municipality Fee:**
- Look for line items labeled: "DM Fee", "Municipality Fee", "Dubai Municipality", "Govt Fee"
- Municipality fee is typically a SMALL amount (hundreds to low thousands, not tens of thousands)
- If you see a breakdown showing: Rental + Production + Small Fee = Net Amount, that small fee is likely Municipality
- The Net Amount shown often equals: Rental + Production/Upload + Municipality
- Municipality fee may appear in a separate row in the costs table, or in a summary section

**Example:**
If you see:
- Net Rental amount: AED 460,000
- Net Production fee: AED 2,000
- Net DM fee: AED 520
- Net amount: AED 462,520 ← This confirms the municipality fee!
- VAT: AED 23,126
- Gross: AED 485,646

This tells you the municipality fee is AED 520.

**EXTRACTION RULES:**

**Be Intelligent About:**
- **Bundled payments:** If one payment covers multiple locations, split it across them
- **Fee identification:** Distinguish between location rentals vs fees (municipality/upload/production)
- **Inconsistent structures:** Tables may be messy, merged cells, unclear headers - parse carefully
- **Missing data:** Use null for truly missing fields, but try hard to find the data first
- **Calculations:** Extract what's shown, but understand the calculation logic to catch errors

**Format Rules:**
1. Dates: Convert to YYYY-MM-DD format (e.g., "21st Feb 2025" → "2025-02-21")
2. Percentages: Convert to decimal (e.g., "5%" → 0.05, "0.4%" → 0.004)
3. Numbers: Pure numbers without currency symbols (e.g., "AED 295,596.00" → 295596.00)
4. Location codes: Extract as list: ["04B", "03A", "15C"] - CODES ONLY, no descriptive names

**DOCUMENT STRUCTURE TO LOOK FOR:**

**Header Information:**
- BO Number (Booking Order reference - usually "BO-XXX" or similar)
- BO Date (when the BO was created)
- Client (company name purchasing the advertising)
  **IMPORTANT:** Client is the BUYER, NOT the seller:
  - Client = Company buying billboard advertising (e.g., "Emaar Properties", "Nestlé", "Mercedes-Benz")
  - DO NOT extract "Viola" as the client - Viola is the SERVICE PROVIDER (seller)
  - Look for "From:", "Client:", "Advertiser:", or the company requesting the campaign
  - Client is who is PAYING for the billboard space, not who is selling it
- Agency (advertising agency, may be blank)
- Brand/Campaign (the advertised brand or campaign name)
  **IMPORTANT:** Use intelligent inference if brand/campaign is not explicitly stated:
  - If client is "Gucci LLC" → brand is likely "Gucci"
  - If client is "Emaar Properties PJSC" → brand is likely "Emaar"
  - If client is "Dubai Properties Development L.L.C" → brand is likely "Dubai Properties"
  - Extract the core brand name from the client company name by removing corporate suffixes like LLC, PJSC, L.L.C, Inc, Ltd, etc.
  - Only use the full client name as brand if there's truly no brand information anywhere in the document
- Category (the client's main industry/sector)
  **IMPORTANT:** Category represents the CLIENT'S industry, not the campaign type:
  - If client is "Emaar Properties PJSC" → category is "Real Estate"
  - If client is "Nestlé Middle East" → category is "FMCG" (Fast-Moving Consumer Goods)
  - If client is "Mercedes-Benz UAE" → category is "Automotive"
  - If client is "Emirates NBD" → category is "Banking/Finance"
  - Common categories: Real Estate, FMCG, Automotive, Banking/Finance, Hospitality, Retail, Healthcare, Technology, Entertainment
  - Infer from the client company name if not explicitly stated in the BO

**Location/Asset Details (usually in a table):**
For EACH billboard location, extract:
- Location code: Extract ONLY the alphanumeric code (e.g., "04B", "03A", "15C")
  - Strip away descriptive names like "Sheikh Zayed Road Tower" or "Al Barsha Mall"
  - Just the code: 2 digits + optional letter (04B, 03A, 15C, etc.)
- Start date (campaign start date)
- End date (campaign end date)
- Campaign duration **IMPORTANT:** Calculate and format intelligently:
  - Calculate number of days between start and end date
  - **Format rules (approximate to nearest unit):**
    * 28-31 days → "1 month"
    * 56-62 days → "2 months"
    * 84-93 days → "3 months"
    * 14-15 days → "2 weeks"
    * 21-22 days → "3 weeks"
    * 7-8 days → "1 week"
    * Only use "X days" if it doesn't fit these approximations
  - Examples: 30 days = "1 month", 15 days = "2 weeks", 60 days = "2 months", 10 days = "10 days"
  - If explicitly stated in BO (rare), use that value; otherwise calculate from dates
- Net amount (rental cost for THIS location - may need to split bundled payments)
- Production/Upload cost (if specified per-location)
- Type (digital vs static - if mentioned)

**CRITICAL: Understanding the Data Structure**

Booking orders have TWO types of costs:

1. **Per-Location Rental Amounts** (in locations array):
   - Each location has its own rental amount (e.g., 04B: AED 80,000, 03A: AED 80,000)
   - This is ONLY the rental cost for that specific billboard
   - Extract as `net_amount` for each location

2. **GLOBAL Fees** (top-level fields, NOT per-location):
   - **municipality_fee**: Dubai Municipality regulatory fee for the ENTIRE booking
     - Look for: "DM Fee", "Municipality Fee", "Dubai Municipality", "Net DM fee"
     - Typically a small amount (hundreds to low thousands)
     - ONE total for all locations combined
     - **If document shows per-location DM fees:** ADD them all up into ONE total
     - Example: 04B: AED 200, 03A: AED 200, 15C: AED 120 → municipality_fee: 520

   - **production_upload_fee**: Total production/upload cost for ALL locations
     - Look for: "Production Fee", "Upload Fee", "Production Cost", "Net Production fee"
     - This is production fee (for static) + upload fee (for digital) combined into ONE total
     - ONE total for all locations combined
     - **If document shows per-location fees:** ADD them all up into ONE total
     - Example: 04B upload: AED 500, 03A upload: AED 500, 15C production: AED 1000 → production_upload_fee: 2000

**CRITICAL:** Each location only stores its rental amount. ALL fees are GLOBAL single totals, NOT per-location values.
Even if the source document lists fees per location, you MUST sum them into single global totals.

**The Math:**
- Sum of all location rental amounts (e.g., 80,000 + 80,000 + 120,000 = 280,000)
- + production_upload_fee (e.g., 2,000)
- + municipality_fee (e.g., 520)
- = net_pre_vat (e.g., 282,520)

**Financial Totals:**
- Net amount (Rental + Production + Municipality, before SLA and VAT)
- VAT amount (5% tax, usually on Rental + Production, not Municipality)
- Gross amount (total including VAT)
- SLA % (deduction percentage, e.g., 10% = 0.10)

**Additional Information:**
- Payment terms (e.g., "60 days PDC", "30 days credit") - **CHECK USER MESSAGE** as this is often provided there
- Salesperson name - **CHECK USER MESSAGE** as user may specify who the sales person is
- Commission %

**CRITICAL NOTES:**
- If you see "Municipality Fee" or "Upload Fee" in the locations table, extract it separately as a fee, NOT as a location
- When multiple locations share one payment, split the amount across them intelligently
- Think about whether each line item is a location rental or a fee
- The structure may be messy - take your time to understand it
- Extract what you see, but understand the business logic to validate your extraction
- **REMEMBER:** For Viola, extract ONLY location codes (04B, 03A, etc.) - no descriptive names!"""





def get_data_extractor_prompt() -> str:
    """
    Generate the system prompt for precise booking order data extraction.

    This prompt is used as the system message when parsing booking orders
    to ensure precise extraction of location tables and fees.

    Returns:
        The data extractor system prompt string
    """
    return """You are a precise booking order data extractor.

**CRITICAL - MANDATORY FOR LOCATION TABLES AND FEES:**
1. **Carefully extract ALL table data** containing location names, dates, and amounts
2. **Pay special attention to tables with columns:** Location/Site, Start Date, End Date, Duration, Net Amount/Cost
3. **Also extract fee line items:** Production Fee, Upload Fee, Municipality Fee (DM), etc.
4. **Be precise with numbers** - only extract numbers that are clearly visible in the document
5. If any field is unclear or ambiguous, use null rather than guessing

**For other fields (client, brand, category):** Standard extraction is fine, reasonable inference allowed.
**For numbers, locations, and fees:** Extract exactly what you see. Do NOT estimate, interpolate, or calculate missing values.

**Fee Extraction Rules:**
- Look for rows labeled: "Production Fee", "Upload Fee", "Production Cost", "Upload Cost"
- Look for rows labeled: "DM Fee", "Municipality Fee", "Dubai Municipality"
- If fees are shown per-location in table, ADD them up into ONE global total
- If no fees found in document, use 0 (don't guess)"""
