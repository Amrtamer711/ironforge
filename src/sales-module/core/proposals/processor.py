"""
Proposal Processing Orchestrator.

Coordinates validation, rendering, and PDF generation for proposals.
"""

import asyncio
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any

from pptx import Presentation
from pypdf import PdfReader

import config
from core.services.template_service import TemplateService
from db.database import db
from generators.pdf import convert_pptx_to_pdf, merge_pdfs, remove_slides_and_convert_to_pdf

from .intro_outro import IntroOutroHandler
from .renderer import ProposalRenderer
from .validator import ProposalValidator


class ProposalProcessor:
    """
    Orchestrates proposal generation workflow.

    Responsibilities:
    - Coordinate validation, rendering, PDF generation
    - Handle intro/outro slide extraction
    - Merge PDFs for multi-proposal packages
    - Log proposals to database
    - Clean up temporary files
    """

    def __init__(
        self,
        validator: ProposalValidator,
        renderer: ProposalRenderer,
        intro_outro_handler: IntroOutroHandler,
        template_service: TemplateService,
    ):
        """
        Initialize processor with dependencies.

        Args:
            validator: ProposalValidator instance
            renderer: ProposalRenderer instance
            intro_outro_handler: IntroOutroHandler instance
            template_service: TemplateService instance (required)
        """
        self.validator = validator
        self.renderer = renderer
        self.intro_outro_handler = intro_outro_handler
        self.template_service = template_service
        self.logger = config.logger

        # Request-scoped cache for extracted intro/outro slides
        # Avoids re-extracting pages from the same PDF within a single request
        # Maps: pdf_name -> (intro_pdf_path, outro_pdf_path)
        self._extracted_slides_cache: dict[str, tuple[str, str]] = {}

    @staticmethod
    def _generate_timestamp_code() -> str:
        """
        Generate compact timestamp code for filenames (HHMMDMMYY).

        Format: HH (hour) MM (minute) D (day) M (month) YY (year)
        Example: 0729072511 = 07:29 AM on July 25, 2011
        Uses UAE timezone (UTC+4)

        Returns:
            Timestamp code string
        """
        uae_tz = timezone(timedelta(hours=4))
        now = datetime.now(uae_tz)
        return f"{now.strftime('%H%M')}{now.day}{now.month}{now.strftime('%y')}"

    @staticmethod
    def _extract_pages_from_pdf(pdf_path: str, pages: list[int]) -> str:
        """
        Extract specific pages from PDF.

        Args:
            pdf_path: Source PDF path
            pages: List of page numbers (0-indexed)

        Returns:
            Path to new PDF with extracted pages
        """
        reader = PdfReader(pdf_path)
        from pypdf import PdfWriter
        writer = PdfWriter()

        for page_num in pages:
            if page_num < len(reader.pages):
                writer.add_page(reader.pages[page_num])

        output_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        output_file.close()

        with open(output_file.name, 'wb') as f:
            writer.write(f)

        return output_file.name

    async def _create_intro_outro_slides(
        self,
        intro_outro_info: dict[str, Any]
    ) -> tuple[str, str]:
        """
        Create intro and outro slide PDFs.

        Strategy:
        1. Try to use pre-made PDF from Supabase Storage
        2. Fall back to PowerPoint extraction if not found

        Args:
            intro_outro_info: Location info dict from IntroOutroHandler

        Returns:
            Tuple of (intro_pdf_path, outro_pdf_path)
        """
        series = intro_outro_info.get('series', '')
        location_key = intro_outro_info.get('key', '')
        display_name = intro_outro_info.get('metadata', {}).get('display_name', location_key)

        self.logger.info("[PROCESSOR] Creating intro/outro slides")
        self.logger.info(f"[PROCESSOR] Selected location: '{display_name}' (key: {location_key})")
        self.logger.info(f"[PROCESSOR] Series: '{series}'")

        # Determine which pre-made PDF to use
        pdf_name = None
        is_landmark = intro_outro_info.get('is_landmark', False)
        is_non_landmark = intro_outro_info.get('is_non_landmark', False)

        if is_landmark or series == 'The Landmark Series':
            pdf_name = "landmark_series"
            self.logger.info("[PROCESSOR] LANDMARK SERIES - looking for pre-made PDF...")
        elif is_non_landmark:
            pdf_name = "rest"
            self.logger.info("[PROCESSOR] NON-LANDMARK - using rest.pdf...")
        elif 'Digital Icons' in series:
            pdf_name = "digital_icons"
            self.logger.info("[PROCESSOR] DIGITAL ICONS - looking for pre-made PDF...")
        else:
            self.logger.info(f"[PROCESSOR] No pre-made PDF mapping for series '{series}'")

        # Try to download pre-made PDF from storage
        # Extract company_hint from metadata for O(1) lookup
        metadata = intro_outro_info.get('metadata', {})
        company_hint = metadata.get('company_schema') or metadata.get('company')

        if pdf_name:
            # Check cache first for extracted slides
            if pdf_name in self._extracted_slides_cache:
                cached_intro, cached_outro = self._extracted_slides_cache[pdf_name]
                if os.path.exists(cached_intro) and os.path.exists(cached_outro):
                    self.logger.info(f"[PROCESSOR] Cache hit for extracted slides: {pdf_name}")
                    return cached_intro, cached_outro
                else:
                    # Cached files were deleted, remove from cache
                    del self._extracted_slides_cache[pdf_name]

            pdf_temp_path = await self.template_service.download_intro_outro_to_temp(
                pdf_name, company_hint=company_hint
            )
            if pdf_temp_path:
                self.logger.info(f"[PROCESSOR] PRE-MADE PDF FOUND: {pdf_name}")
                intro_pdf = self._extract_pages_from_pdf(pdf_temp_path, [0])
                reader = PdfReader(pdf_temp_path)
                last_page = len(reader.pages) - 1
                outro_pdf = self._extract_pages_from_pdf(pdf_temp_path, [last_page])
                # Clean up the temp PDF (but keep extracted pages)
                try:
                    os.unlink(pdf_temp_path)
                except OSError:
                    pass
                # Cache the extracted slides
                self._extracted_slides_cache[pdf_name] = (intro_pdf, outro_pdf)
                return intro_pdf, outro_pdf
            else:
                self.logger.info(f"[PROCESSOR] PRE-MADE PDF NOT FOUND: {pdf_name}")

        # Fall back to PowerPoint extraction
        self.logger.info("[PROCESSOR] FALLING BACK to PowerPoint extraction")

        # Download template from storage (company_hint already extracted above)
        template_path = await self.template_service.download_to_temp(
            location_key, company_hint=company_hint
        )
        if not template_path:
            # Last resort: try the path from intro_outro_info
            template_path = intro_outro_info.get('template_path')
            if not template_path or not os.path.exists(template_path):
                raise FileNotFoundError(f"Template not found for {location_key}")

        self.logger.info(f"[PROCESSOR] Using PowerPoint template: {template_path}")

        loop = asyncio.get_event_loop()

        # Create intro (first slide only)
        intro_pptx = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
        intro_pptx.close()
        shutil.copy2(template_path, intro_pptx.name)

        pres = Presentation(intro_pptx.name)
        xml_slides = pres.slides._sldIdLst
        slides_to_remove = list(xml_slides)[1:]
        for slide_id in slides_to_remove:
            xml_slides.remove(slide_id)
        pres.save(intro_pptx.name)

        intro_pdf = await loop.run_in_executor(None, convert_pptx_to_pdf, intro_pptx.name)

        # Create outro (last slide only)
        outro_pptx = tempfile.NamedTemporaryFile(delete=False, suffix=".pptx")
        outro_pptx.close()
        shutil.copy2(template_path, outro_pptx.name)

        pres = Presentation(outro_pptx.name)
        xml_slides = pres.slides._sldIdLst
        slides_to_remove = list(xml_slides)[:-1]
        for slide_id in slides_to_remove:
            xml_slides.remove(slide_id)
        pres.save(outro_pptx.name)

        outro_pdf = await loop.run_in_executor(None, convert_pptx_to_pdf, outro_pptx.name)

        # Clean up temp files
        try:
            os.unlink(intro_pptx.name)
            os.unlink(outro_pptx.name)
            # Clean up downloaded template if it was from storage
            if template_path != intro_outro_info.get('template_path'):
                os.unlink(template_path)
        except OSError as e:
            self.logger.warning(f"[PROCESSOR] Failed to cleanup temp files: {e}")

        return intro_pdf, outro_pdf

    async def process_separate(
        self,
        proposals_data: list[dict[str, Any]],
        submitted_by: str = "",
        client_name: str = "",
        payment_terms: str = "100% upfront",
        currency: str = None
    ) -> dict[str, Any]:
        """
        Process separate proposals (one PDF per location or merged).

        Args:
            proposals_data: List of proposal dicts
            submitted_by: User who submitted
            client_name: Client name
            payment_terms: Payment terms text
            currency: Currency code (e.g., 'USD', 'EUR')

        Returns:
            Dict with success status and file paths:
            - For single proposal: {success, is_single, pptx_path, pdf_path, location, ...}
            - For multiple: {success, is_single: False, individual_files, merged_pdf_path, ...}

        Example:
            >>> processor = ProposalProcessor(validator, renderer, intro_outro)
            >>> result = await processor.process_separate(
            ...     proposals_data,
            ...     submitted_by="user@example.com",
            ...     client_name="ABC Corp",
            ...     payment_terms="100% upfront",
            ...     currency="AED"
            ... )
        """
        self.logger.info("[PROCESSOR] Starting process_separate")
        self.logger.info(f"[PROCESSOR] Proposals: {len(proposals_data)}")
        self.logger.info(f"[PROCESSOR] Client: {client_name}, Submitted by: {submitted_by}")
        self.logger.info(f"[PROCESSOR] Payment terms: {payment_terms}")
        self.logger.info(f"[PROCESSOR] Currency: {currency or 'AED'}")

        # Validate proposals (async)
        validated_proposals, errors = await self.validator.validate_proposals(proposals_data)
        if errors:
            return {"success": False, "errors": errors}

        is_single = len(validated_proposals) == 1
        loop = asyncio.get_event_loop()

        # Get intro/outro info for multiple proposals
        intro_outro_info = None
        if len(validated_proposals) > 1:
            intro_outro_info = self.intro_outro_handler.get_intro_outro_location(validated_proposals)

        # Process each proposal
        async def process_single(idx: int, proposal: dict) -> dict:
            # Download template from storage
            location_key = proposal.get("location", "").lower().strip()
            company_hint = proposal.get("company_schema")  # O(1) lookup from validator
            template_path = await self.template_service.download_to_temp(
                location_key, company_hint=company_hint
            )
            if not template_path:
                raise FileNotFoundError(f"Template not found for {location_key}")

            # Build financial data
            financial_data = {
                "location": proposal["location"],
                "durations": proposal["durations"],
                "net_rates": proposal.get("net_rates", []),
                "spots": proposal.get("spots", 1),
                "client_name": client_name,
                "payment_terms": payment_terms,
            }

            # Handle start_dates (array) vs start_date (single)
            if "start_dates" in proposal and proposal["start_dates"]:
                financial_data["start_dates"] = proposal["start_dates"]
            else:
                financial_data["start_date"] = proposal.get("start_date", "1st December 2025")

            # Add optional fields
            if "end_date" in proposal:
                financial_data["end_date"] = proposal["end_date"]
            if "production_fee" in proposal:
                financial_data["production_fee"] = proposal["production_fee"]

            # Render PPTX with financial slide
            pptx_path, vat_amounts, total_amounts = await loop.run_in_executor(
                None,
                self.renderer.create_proposal_with_template,
                str(template_path),
                financial_data,
                currency
            )

            # Clean up downloaded template
            try:
                os.unlink(template_path)
            except OSError:
                pass

            result = {
                "path": pptx_path,
                "location": proposal["location"].title(),
                "filename": f"{proposal['location'].title()}_Proposal.pptx",
                "totals": total_amounts,
                "idx": idx
            }

            # Convert to PDF
            if is_single:
                pdf_path = await loop.run_in_executor(None, convert_pptx_to_pdf, pptx_path)
                timestamp_code = self._generate_timestamp_code()
                client_prefix = client_name.replace(" ", "_") if client_name else "Client"
                result["pdf_path"] = pdf_path
                result["pdf_filename"] = f"{client_prefix}_{timestamp_code}.pdf"
            else:
                # Determine which slides to remove
                if intro_outro_info:
                    remove_first = True
                    remove_last = True
                else:
                    # Legacy behavior
                    remove_first = False
                    remove_last = False
                    if idx == 0:
                        remove_last = True
                    elif idx < len(validated_proposals) - 1:
                        remove_first = True
                        remove_last = True
                    else:
                        remove_first = True

                pdf_path = await remove_slides_and_convert_to_pdf(pptx_path, remove_first, remove_last)
                result["pdf_file"] = pdf_path

            return result

        # Process all in parallel
        tasks = [process_single(idx, p) for idx, p in enumerate(validated_proposals)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                return {"success": False, "error": f"Error processing proposal {idx + 1}: {str(result)}"}

        # Sort by original index
        sorted_results = sorted(results, key=lambda x: x["idx"])

        # Handle single proposal
        if is_single:
            result = sorted_results[0]
            total_str = result["totals"][0] if result["totals"] else "AED 0"

            db.log_proposal(
                submitted_by=submitted_by,
                client_name=client_name,
                package_type="separate",
                locations=result["location"],
                total_amount=total_str,
            )

            return {
                "success": True,
                "is_single": True,
                "pptx_path": result["path"],
                "pdf_path": result["pdf_path"],
                "location": result["location"],
                "pptx_filename": result["filename"],
                "pdf_filename": result["pdf_filename"],
            }

        # Handle multiple proposals
        individual_files = []
        pdf_files = []
        locations = []

        for result in sorted_results:
            individual_files.append({
                "path": result["path"],
                "location": result["location"],
                "filename": result["filename"],
                "totals": result["totals"],
            })
            pdf_files.append(result["pdf_file"])
            locations.append(result["location"])

        # Add intro/outro slides
        if intro_outro_info:
            intro_pdf, outro_pdf = await self._create_intro_outro_slides(intro_outro_info)
            pdf_files.insert(0, intro_pdf)
            pdf_files.append(outro_pdf)

        # Merge PDFs
        merged_pdf = await loop.run_in_executor(None, merge_pdfs, pdf_files)

        # Clean up temp PDFs
        for pdf_file in pdf_files:
            try:
                os.unlink(pdf_file)
            except Exception as e:
                self.logger.warning(f"Failed to clean up PDF: {pdf_file} - {e}")

        # Log to database
        first_totals = [f.get("totals", ["AED 0"])[0] for f in individual_files]
        summary_total = ", ".join(first_totals)

        db.log_proposal(
            submitted_by=submitted_by,
            client_name=client_name,
            package_type="separate",
            locations=", ".join(locations),
            total_amount=summary_total,
        )

        timestamp_code = self._generate_timestamp_code()
        client_prefix = client_name.replace(" ", "_") if client_name else "Client"

        return {
            "success": True,
            "is_single": False,
            "individual_files": individual_files,
            "merged_pdf_path": merged_pdf,
            "locations": ", ".join(locations),
            "merged_pdf_filename": f"{client_prefix}_{timestamp_code}.pdf",
        }

    async def process_combined(
        self,
        proposals_data: list[dict[str, Any]],
        combined_net_rate: str,
        submitted_by: str = "",
        client_name: str = "",
        payment_terms: str = "100% upfront",
        currency: str = None
    ) -> dict[str, Any]:
        """
        Process combined package (one PDF with all locations).

        Args:
            proposals_data: List of proposal dicts
            combined_net_rate: Combined rate for package
            submitted_by: User who submitted
            client_name: Client name
            payment_terms: Payment terms text
            currency: Currency code

        Returns:
            Dict with success status and file paths:
            {success, is_combined, pdf_path, locations, pdf_filename}

        Example:
            >>> result = await processor.process_combined(
            ...     proposals_data,
            ...     "50000",
            ...     submitted_by="user@example.com",
            ...     client_name="ABC Corp",
            ...     payment_terms="100% upfront",
            ...     currency="AED"
            ... )
        """
        self.logger.info("[PROCESSOR] Starting process_combined")
        self.logger.info(f"[PROCESSOR] Proposals: {len(proposals_data)}")
        self.logger.info(f"[PROCESSOR] Combined rate: {combined_net_rate}")
        self.logger.info(f"[PROCESSOR] Client: {client_name}, Submitted by: {submitted_by}")
        self.logger.info(f"[PROCESSOR] Payment terms: {payment_terms}")
        self.logger.info(f"[PROCESSOR] Currency: {currency or 'AED'}")

        # Validate proposals (async)
        validated_proposals, errors = await self.validator.validate_combined_package(
            proposals_data,
            combined_net_rate
        )
        if errors:
            return {"success": False, "errors": errors}

        loop = asyncio.get_event_loop()

        # Get intro/outro info
        intro_outro_info = self.intro_outro_handler.get_intro_outro_location(validated_proposals)

        # Deduplicate deck slides (same location can have multiple durations)
        seen_locations = set()
        unique_proposals_for_deck = []

        for proposal in validated_proposals:
            location_key = proposal["location"]
            if location_key not in seen_locations:
                seen_locations.add(location_key)
                unique_proposals_for_deck.append(proposal)
                self.logger.info(f"[PROCESSOR] Including deck for '{location_key}' (first occurrence)")
            else:
                self.logger.info(f"[PROCESSOR] Skipping duplicate deck for '{location_key}'")

        # Process each unique location (in parallel)
        total_proposals = len(unique_proposals_for_deck)

        async def process_combined_single(idx: int, proposal: dict) -> dict:
            """Process a single proposal for combined package."""
            # Download template from storage
            location_key = proposal.get("location", "").lower().strip()
            company_hint = proposal.get("company_schema")  # O(1) lookup from validator
            template_path = await self.template_service.download_to_temp(
                location_key, company_hint=company_hint
            )
            if not template_path:
                raise FileNotFoundError(f"Template not found for {location_key}")

            total_combined_result = None

            # Last location gets the combined financial slide
            if idx == total_proposals - 1:
                pptx_path, total_combined_result = await loop.run_in_executor(
                    None,
                    self.renderer.create_combined_proposal_with_template,
                    str(template_path),
                    validated_proposals,  # Use ALL proposals (with duplicates for investment sheet)
                    combined_net_rate,
                    client_name,
                    payment_terms,
                    currency,
                )
                # Clean up downloaded template
                try:
                    os.unlink(template_path)
                except OSError:
                    pass
            else:
                pptx_path = str(template_path)
                # Note: template_path will be cleaned up after PDF conversion

            # Determine which slides to remove
            if intro_outro_info:
                remove_first = True
                remove_last = True
            else:
                # Legacy behavior
                remove_first = False
                remove_last = False
                if idx == 0:
                    remove_last = True
                elif idx < total_proposals - 1:
                    remove_first = True
                    remove_last = True
                else:
                    remove_first = True

            pdf_path = await remove_slides_and_convert_to_pdf(pptx_path, remove_first, remove_last)

            # Clean up temp PPTX/template
            try:
                os.unlink(pptx_path)
            except OSError as e:
                self.logger.warning(f"[PROCESSOR] Failed to cleanup temp file: {e}")

            return {"pdf_path": pdf_path, "total_combined": total_combined_result, "idx": idx}

        # Process all in parallel
        tasks = [process_combined_single(idx, p) for idx, p in enumerate(unique_proposals_for_deck)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for errors
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                return {"success": False, "error": f"Error processing proposal {idx + 1}: {str(result)}"}

        # Sort by original index and extract PDFs
        sorted_results = sorted(results, key=lambda x: x["idx"])
        pdf_files = [r["pdf_path"] for r in sorted_results]

        # Get total_combined from the last proposal's result
        total_combined = sorted_results[-1]["total_combined"] if sorted_results else None

        # Add intro/outro slides
        if intro_outro_info:
            intro_pdf, outro_pdf = await self._create_intro_outro_slides(intro_outro_info)
            pdf_files.insert(0, intro_pdf)
            pdf_files.append(outro_pdf)

        # Merge PDFs
        merged_pdf = await loop.run_in_executor(None, merge_pdfs, pdf_files)

        # Clean up temp PDFs
        for pdf_file in pdf_files:
            try:
                os.unlink(pdf_file)
            except Exception as e:
                self.logger.warning(f"Failed to clean up PDF: {pdf_file} - {e}")

        # Calculate total if not provided
        if total_combined is None:
            municipality_fee = 520
            total_upload_fees = sum(
                config.UPLOAD_FEES_MAPPING.get(p["location"].lower(), 3000)
                for p in validated_proposals
            )
            net_rate_numeric = float(combined_net_rate.replace("AED", "").replace(",", "").strip())
            subtotal = net_rate_numeric + total_upload_fees + municipality_fee
            vat = subtotal * 0.05
            total_combined = f"AED {subtotal + vat:,.0f}"

        # Log to database
        locations_str = ", ".join([p["location"].title() for p in validated_proposals])

        db.log_proposal(
            submitted_by=submitted_by,
            client_name=client_name,
            package_type="combined",
            locations=locations_str,
            total_amount=total_combined,
        )

        timestamp_code = self._generate_timestamp_code()
        client_prefix = client_name.replace(" ", "_") if client_name else "Client"

        return {
            "success": True,
            "is_combined": True,
            "pptx_path": None,
            "pdf_path": merged_pdf,
            "locations": locations_str,
            "pdf_filename": f"{client_prefix}_{timestamp_code}.pdf",
        }
