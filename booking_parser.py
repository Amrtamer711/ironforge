"""
Booking Order Parser for MMG Backlite and Viola
Handles classification and parsing of booking order documents using OpenAI Responses API
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import config

logger = logging.getLogger("proposal-bot")

# File storage directories
BOOKING_ORDERS_BASE = Path("/data/booking_orders") if os.path.exists("/data") else Path(__file__).parent / "booking_orders"
ORIGINAL_DIR = BOOKING_ORDERS_BASE / "original_bos"
PARSED_DIR = BOOKING_ORDERS_BASE / "parsed_bos"

# BO Template files (for future use - not currently used)
# These are the actual branded templates for Backlite and Viola
# Currently using simple Excel generation, will switch to template-based when ready
TEMPLATES_DIR = Path(__file__).parent / "bo_templates"
TEMPLATE_BACKLITE = TEMPLATES_DIR / "backlite_bo_template.xlsx"
TEMPLATE_VIOLA = TEMPLATES_DIR / "viola_bo_template.xlsx"

# Ensure directories exist
ORIGINAL_DIR.mkdir(parents=True, exist_ok=True)
PARSED_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class ParseResult:
    """Result from parsing a booking order"""
    data: Dict[str, Any]
    warnings: List[str]
    missing_required: List[str]
    needs_review: bool


class BookingOrderParser:
    """Parser for booking order documents with company-specific rules"""

    def __init__(self, company: str = "backlite"):
        self.company = company
        self.required_global = ["client", "net_pre_vat"]
        self.required_per_location = ["name", "start_date", "end_date", "net_amount"]

    def detect_file_type(self, file_path: Path) -> str:
        """Detect file type from extension"""
        suffix = file_path.suffix.lower()
        if suffix in [".xlsx", ".xls"]:
            return "excel"
        elif suffix == ".pdf":
            return "pdf"
        elif suffix in [".jpg", ".jpeg", ".png", ".gif", ".bmp"]:
            return "image"
        else:
            return "unknown"

    async def classify_document(self, file_path: Path, user_message: str = "") -> Dict[str, str]:
        """
        Classify document as BOOKING_ORDER or ARTWORK using OpenAI Responses API.
        Biased toward ARTWORK unless clear booking order fields present.

        Args:
            file_path: Path to the document file
            user_message: Optional user's message/prompt that accompanied the file upload
        """
        logger.info(f"[BOOKING PARSER] Classifying document: {file_path}")
        if user_message:
            logger.info(f"[BOOKING PARSER] User message context: {user_message}")

        # Upload file to OpenAI with purpose="user_data" (VendorAI pattern)
        try:
            with open(file_path, "rb") as f:
                file_obj = await config.openai_client.files.create(
                    file=f,
                    purpose="user_data"
                )
            file_id = file_obj.id
            logger.info(f"[BOOKING PARSER] Uploaded file to OpenAI: {file_id}")
        except Exception as e:
            logger.error(f"[BOOKING PARSER] Failed to upload file: {e}")
            return {"classification": "UNKNOWN", "confidence": "low", "reasoning": str(e)}

        # Classification prompt - BIASED toward ARTWORK
        user_context = f"\n\n**USER'S MESSAGE:** \"{user_message}\"\nUse this context to better understand the user's intent." if user_message else ""

        classification_prompt = f"""You are classifying a document as either a BOOKING_ORDER or ARTWORK.

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

Analyze the uploaded file and respond with:
- classification: "BOOKING_ORDER" or "ARTWORK"
- confidence: "high", "medium", or "low"
- reasoning: Brief explanation (1 sentence)
"""

        try:
            # Use VendorAI syntax: {"type": "input_file", "file_id": ...} and {"type": "input_text", "text": ...}
            response = await config.openai_client.responses.create(
                model=config.OPENAI_MODEL,
                input=[
                    {"role": "system", "content": "You are a document classifier. Analyze the file and provide classification."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": file_id},
                            {"type": "input_text", "text": classification_prompt}
                        ]
                    }
                ],
                store=False
            )

            if not response.output or len(response.output) == 0:
                logger.warning("[BOOKING PARSER] Empty classification response")
                return {"classification": "ARTWORK", "confidence": "low", "reasoning": "No response from model"}

            # Parse response text using output_text
            # This gets the final text output after any tool calls
            result_text = response.output_text
            logger.info(f"[BOOKING PARSER] Classification response: {result_text}")

            # Extract classification from response
            result_lower = result_text.lower()
            if "booking" in result_lower and "order" in result_lower:
                classification = "BOOKING_ORDER"
            else:
                classification = "ARTWORK"

            if "high" in result_lower:
                confidence = "high"
            elif "medium" in result_lower:
                confidence = "medium"
            else:
                confidence = "low"

            return {
                "classification": classification,
                "confidence": confidence,
                "reasoning": result_text[:200]
            }

        except Exception as e:
            logger.error(f"[BOOKING PARSER] Classification error: {e}", exc_info=True)
            return {"classification": "ARTWORK", "confidence": "low", "reasoning": f"Error: {str(e)}"}
        finally:
            # Cleanup uploaded file
            try:
                await config.openai_client.files.delete(file_id)
            except:
                pass

    async def parse_file(self, file_path: Path, file_type: str) -> ParseResult:
        """
        Parse booking order file using OpenAI Responses API with structured JSON output.
        No hallucinations - only extract what's clearly present.
        """
        logger.info(f"[BOOKING PARSER] Parsing {file_type} file: {file_path}")

        # Upload file to OpenAI with purpose="user_data" (VendorAI pattern)
        try:
            with open(file_path, "rb") as f:
                file_obj = await config.openai_client.files.create(
                    file=f,
                    purpose="user_data"
                )
            file_id = file_obj.id
            logger.info(f"[BOOKING PARSER] Uploaded file for parsing: {file_id}")
        except Exception as e:
            logger.error(f"[BOOKING PARSER] Failed to upload file for parsing: {e}")
            raise

        # Parsing prompt for structured extraction (no schema in prompt)
        parsing_prompt = self._build_parsing_prompt()

        try:
            # Use structured outputs with JSON schema + code_interpreter for better table parsing
            response = await config.openai_client.responses.create(
                model=config.OPENAI_MODEL,
                input=[
                    {"role": "system", "content": "You are a booking order data extractor. Extract ONLY what is clearly visible. Use null for missing fields. No hallucinations."},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_file", "file_id": file_id},
                            {"type": "input_text", "text": parsing_prompt}
                        ]
                    }
                ],
                tools=[
                    {
                        "type": "code_interpreter",
                        "container": {
                            "type": "auto"
                        }
                    }
                ],
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "booking_order_extraction",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "bo_number": {"type": ["string", "null"]},
                                "bo_date": {"type": ["string", "null"]},
                                "client": {"type": ["string", "null"]},
                                "agency": {"type": ["string", "null"]},
                                "brand_campaign": {"type": ["string", "null"]},
                                "category": {"type": ["string", "null"]},
                                "asset": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "array", "items": {"type": "string"}},
                                        {"type": "null"}
                                    ]
                                },
                                "payment_terms": {"type": ["string", "null"]},
                                "sales_person": {"type": ["string", "null"]},
                                "commission_pct": {"type": ["number", "null"]},
                                "sla_pct": {"type": ["number", "null"]},
                                "net_pre_vat": {"type": ["number", "null"]},
                                "vat_value": {"type": ["number", "null"]},
                                "gross_amount": {"type": ["number", "null"]},
                                "notes": {"type": ["string", "null"]},
                                "locations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "asset": {"type": ["string", "null"]},
                                            "start_date": {"type": "string"},
                                            "end_date": {"type": "string"},
                                            "campaign_duration": {"type": "string"},
                                            "campaign_cost": {"type": ["number", "null"]},
                                            "production_upload_cost": {"type": ["number", "null"]},
                                            "dm_fee": {"type": ["number", "null"]},
                                            "net_amount": {"type": "number"}
                                        },
                                        "required": ["name", "start_date", "end_date", "campaign_duration", "net_amount", "asset", "campaign_cost", "production_upload_cost", "dm_fee"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["bo_number", "bo_date", "client", "agency", "brand_campaign", "category", "asset", "payment_terms", "sales_person", "commission_pct", "sla_pct", "net_pre_vat", "vat_value", "gross_amount", "notes", "locations"],
                            "additionalProperties": False
                        }
                    }
                },
                store=False
            )

            if not response.output or len(response.output) == 0:
                raise ValueError("Empty parsing response from model")

            # Extract JSON from structured output using output_text
            # This gets the final text output after any tool calls
            result_text = response.output_text
            logger.info(f"[BOOKING PARSER] Parse response length: {len(result_text)} chars")
            logger.info(f"[BOOKING PARSER] Parse response text: {result_text[:500]}...")  # Log first 500 chars

            # Parse JSON (should be valid JSON from structured outputs)
            parsed_data = json.loads(result_text)

            # Post-process and validate
            processed = self._post_process_data(parsed_data)
            warnings = self._generate_warnings(processed)
            missing = self._check_missing_required(processed)
            needs_review = len(warnings) > 0 or len(missing) > 0

            return ParseResult(
                data=processed,
                warnings=warnings,
                missing_required=missing,
                needs_review=needs_review
            )

        except Exception as e:
            logger.error(f"[BOOKING PARSER] Parsing error: {e}", exc_info=True)
            raise
        finally:
            # Cleanup uploaded file
            try:
                await config.openai_client.files.delete(file_id)
            except:
                pass

    def _build_parsing_prompt(self) -> str:
        """Build the parsing prompt with field requirements"""
        return f"""You are extracting data from a booking order document for {self.company.upper()}.

**YOUR TASK:**
Extract ALL visible information from this booking order. Be precise and thorough. Do NOT make up values.

**CRITICAL EXTRACTION RULES:**
1. Extract ONLY what is clearly visible in the document
2. Use null for any field that is missing or unclear
3. For dates: Convert to YYYY-MM-DD format (e.g., "21st February 2025" → "2025-02-21")
4. For percentages: Convert to decimal (e.g., "5%" → 0.05, "0.4%" → 0.004)
5. For numbers: Extract as pure numbers without currency symbols (e.g., "295,596.00" → 295596.00)
6. Do NOT calculate or estimate - only extract what you see

**DOCUMENT STRUCTURE TO LOOK FOR:**

**Header Information:**
- BO Number (Booking Order reference number - usually starts with "BO-" or "DPD-")
- BO Date (the date the booking order was created)
- Client (company/organization name)
- Agency (may be blank/empty)
- Brand/Campaign (campaign or brand name)
- Category (e.g., "Real Estate", "FMCG", "Automotive")

**Asset Information:**
- Asset(s): The billboard/screen codes or names (e.g., "UAE02", "SZR - Timaz Screen")
- Can be a single asset OR multiple assets (extract as list if multiple)
- May appear in header OR per-location in a table

**Location Details (usually in a table):**
Look for a table with columns showing different locations/sites. For EACH location, extract:
- Location name (site/screen identifier)
- Start date (campaign start date for this location)
- End date (campaign end date for this location)
- Campaign duration (e.g., "1 month", "30 days")
- Asset (if specified per-location, otherwise use global asset)

**Cost Breakdown Per Location:**
For each location, look for these cost components:
- Campaign cost / Media cost / Net amount (the main advertising cost)
- Production cost / Upload cost (may be labeled "Production/Upload Cost", can be 0 or N/A)
- DM Fee / Digital Marketing Fee (additional fee, can be 0 or N/A)

IMPORTANT: The location's net_amount should be the TOTAL for that location.

**Financial Totals (bottom of document):**
- Net amount / Net excl. VAT (total before VAT) - extract if shown
- VAT amount (Value Added Tax) - extract if shown
- Gross amount (total including VAT) - extract if shown
- SLA / SLA% (Service Level Agreement percentage) - extract if shown

**Additional Information:**
- Payment terms (e.g., "60 days PDC", "30 days credit")
- Sales person name
- Commission % (salesperson commission percentage)

**IMPORTANT NOTES:**
- If you see multiple locations in a table, create one object per location in the "locations" array
- Each location should have its own dates, costs, and duration
- The net_amount for each location is the sum of that location's costs
- If a document shows "N/A" or blank for a cost field, use null
- Asset codes like "UAE02", "UAE03", "UAE21" should be extracted as a list: ["UAE02", "UAE03", "UAE21"]"""

    def _extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response (may have markdown code blocks)"""
        # Remove markdown code blocks if present
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[BOOKING PARSER] Failed to parse JSON: {e}")
            logger.error(f"[BOOKING PARSER] Response text: {text[:500]}")
            raise ValueError(f"Invalid JSON in response: {e}")

    def _post_process_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Post-process parsed data: normalize, calculate derived fields"""
        # Calculate derived fields
        net = data.get("net_pre_vat")
        vat = data.get("vat_value")
        gross = data.get("gross_amount")
        sla_pct = data.get("sla_pct", 0) or 0

        if net is not None:
            # Calculate VAT if missing (5% standard in UAE)
            if vat is None:
                data["vat_calc"] = round(net * 0.05, 2)
            else:
                data["vat_calc"] = vat

            # Calculate gross if missing
            if gross is None:
                data["gross_calc"] = round(net + data["vat_calc"], 2)
            else:
                data["gross_calc"] = gross

            # Calculate SLA deduction
            data["sla_deduction"] = round(net * sla_pct, 2)
            data["net_excl_sla_calc"] = round(net - data["sla_deduction"], 2)

        # Normalize dates
        for location in data.get("locations", []):
            for date_field in ["start_date", "end_date"]:
                if location.get(date_field):
                    location[date_field] = self._normalize_date(location[date_field])

        return data

    def _normalize_date(self, date_str: str) -> str:
        """Try to normalize date to YYYY-MM-DD format"""
        if not date_str:
            return None

        # Try common formats
        for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except:
                continue

        # Return original if can't parse
        return date_str

    def _generate_warnings(self, data: Dict[str, Any]) -> List[str]:
        """Generate warnings about inconsistencies"""
        warnings = []

        # Check totals consistency
        net = data.get("net_pre_vat")
        vat_calc = data.get("vat_calc")
        gross_calc = data.get("gross_calc")
        gross_stated = data.get("gross_amount")

        if gross_stated and gross_calc and abs(gross_stated - gross_calc) > 0.01:
            warnings.append(f"Gross amount mismatch: stated {gross_stated} vs calculated {gross_calc}")

        # Check location totals sum
        if net and data.get("locations"):
            location_total = sum(loc.get("net_amount", 0) for loc in data["locations"])
            if abs(location_total - net) > 0.01:
                warnings.append(f"Location totals ({location_total}) don't match global net ({net})")

        return warnings

    def _check_missing_required(self, data: Dict[str, Any]) -> List[str]:
        """Check for missing required fields"""
        missing = []

        # Check global required
        for field in self.required_global:
            if not data.get(field):
                missing.append(f"Global field: {field}")

        # Check per-location required
        for i, location in enumerate(data.get("locations", [])):
            for field in self.required_per_location:
                if not location.get(field):
                    missing.append(f"Location {i+1}: {field}")

        return missing

    def format_for_slack(self, data: Dict[str, Any], bo_ref: str) -> str:
        """Format booking order data for Slack display"""
        lines = [
            f"**Booking Order:** {bo_ref}",
            f"**Client:** {data.get('client', 'N/A')}",
            f"**Campaign:** {data.get('brand_campaign', 'N/A')}",
            f"**Net (pre-VAT):** AED {data.get('net_pre_vat', 0):,.2f}",
            f"**VAT (5%):** AED {data.get('vat_calc', 0):,.2f}",
            f"**Gross Total:** AED {data.get('gross_calc', 0):,.2f}",
        ]

        if data.get("sla_pct"):
            lines.append(f"**SLA Deduction:** AED {data.get('sla_deduction', 0):,.2f} ({data['sla_pct']*100:.1f}%)")
            lines.append(f"**Net (excl SLA):** AED {data.get('net_excl_sla_calc', 0):,.2f}")

        if data.get("locations"):
            lines.append(f"\n**Locations:** {len(data['locations'])}")
            for loc in data["locations"][:5]:  # Show first 5
                lines.append(f"  • {loc.get('name', 'Unknown')}: {loc.get('start_date', '?')} to {loc.get('end_date', '?')}")

        return "\n".join(lines)

    async def generate_excel(self, data: Dict[str, Any], bo_ref: str) -> Path:
        """
        Generate standardized Excel output - single sheet, field/value format

        NOTE: This is a simple format for initial testing.
        TODO: Switch to using branded templates (TEMPLATE_BACKLITE or TEMPLATE_VIOLA)
              when ready to use the actual company-specific formats in bo_templates/
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Booking Order"

        # Header style
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        # Add headers
        ws["A1"] = "Field"
        ws["B1"] = "Value"
        ws["A1"].fill = header_fill
        ws["A1"].font = header_font
        ws["B1"].fill = header_fill
        ws["B1"].font = header_font

        # Global fields
        row = 2
        fields = [
            ("BO Reference", bo_ref),
            ("BO Number", data.get("bo_number")),
            ("BO Date", data.get("bo_date")),
            ("Client", data.get("client")),
            ("Agency", data.get("agency")),
            ("Brand/Campaign", data.get("brand_campaign")),
            ("Category", data.get("category")),
            ("Asset", data.get("asset")),
            ("Net (pre-VAT)", data.get("net_pre_vat")),
            ("VAT Value", data.get("vat_value")),
            ("VAT Calculated", data.get("vat_calc")),
            ("Gross Amount", data.get("gross_amount")),
            ("Gross Calculated", data.get("gross_calc")),
            ("SLA %", data.get("sla_pct")),
            ("SLA Deduction", data.get("sla_deduction")),
            ("Net (excl SLA)", data.get("net_excl_sla_calc")),
            ("Payment Terms", data.get("payment_terms")),
            ("Sales Person", data.get("sales_person")),
            ("Commission %", data.get("commission_pct")),
            ("Notes", data.get("notes")),
        ]

        for field, value in fields:
            ws[f"A{row}"] = field
            # Convert lists to comma-separated strings for Excel
            if isinstance(value, list):
                value = ", ".join(str(v) for v in value)
            ws[f"B{row}"] = value if value is not None else ""
            row += 1

        # Locations
        if data.get("locations"):
            row += 1
            ws[f"A{row}"] = "LOCATIONS"
            ws[f"A{row}"].font = Font(bold=True, size=12)
            row += 1

            for i, loc in enumerate(data["locations"], 1):
                ws[f"A{row}"] = f"Location {i}: {loc.get('name', 'Unknown')}"
                ws[f"A{row}"].font = Font(bold=True)
                row += 1

                loc_fields = [
                    ("  Asset", loc.get("asset")),
                    ("  Start Date", loc.get("start_date")),
                    ("  End Date", loc.get("end_date")),
                    ("  Duration", loc.get("campaign_duration")),
                    ("  Production/Upload Cost", loc.get("production_upload_cost")),
                    ("  DM Fee", loc.get("dm_fee")),
                    ("  Net Amount", loc.get("net_amount")),
                ]

                for field, value in loc_fields:
                    ws[f"A{row}"] = field
                    # Convert lists to comma-separated strings for Excel
                    if isinstance(value, list):
                        value = ", ".join(str(v) for v in value)
                    ws[f"B{row}"] = value if value is not None else ""
                    row += 1

                row += 1

        # Adjust column widths
        ws.column_dimensions["A"].width = 30
        ws.column_dimensions["B"].width = 40

        # Save
        output_path = PARSED_DIR / f"{bo_ref}.xlsx"
        wb.save(output_path)
        logger.info(f"[BOOKING PARSER] Generated Excel: {output_path}")

        return output_path
