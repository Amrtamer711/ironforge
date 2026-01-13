#!/usr/bin/env python3
"""
Convert all PPTX templates to PDF using Microsoft PowerPoint and upload alongside originals.

This script:
1. Lists all PPTX templates from Supabase Storage
2. Downloads each PPTX
3. Converts to PDF using Microsoft PowerPoint (AppleScript on macOS)
4. Uploads the PDF back to the same folder

Usage:
    # Set environment variables first
    export ASSETMGMT_DEV_SUPABASE_URL="your-url"
    export ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY="your-key"

    # Run the script
    python convert_templates_to_pdf.py

    # Or dry-run first
    python convert_templates_to_pdf.py --dry-run
"""

import argparse
import os
import subprocess
import sys
import tempfile

from supabase import create_client


def get_supabase_client():
    """Get Supabase client from environment variables."""
    url = os.getenv("ASSETMGMT_DEV_SUPABASE_URL")
    key = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        print("ERROR: Missing environment variables")
        print("Set ASSETMGMT_DEV_SUPABASE_URL and ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY")
        sys.exit(1)

    return create_client(url, key)


def convert_pptx_to_pdf(pptx_path: str, pdf_path: str) -> bool:
    """Convert PPTX to PDF using Microsoft PowerPoint (AppleScript)."""
    powerpoint_script = f'''
    tell application "Microsoft PowerPoint"
        open POSIX file "{pptx_path}"
        save active presentation in POSIX file "{pdf_path}" as save as PDF
        close active presentation
    end tell
    '''

    result = subprocess.run(
        ['osascript', '-e', powerpoint_script],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        print(f"    PowerPoint error: {result.stderr}")
        return False

    return os.path.exists(pdf_path)


def list_all_templates(supabase) -> list[dict]:
    """List all PPTX templates from storage."""
    storage = supabase.storage
    bucket = storage.from_("templates")

    templates = []

    # List all companies (top-level folders)
    companies = bucket.list("")

    for company_item in companies:
        company = company_item.get("name")
        if not company or company.startswith("."):
            continue

        print(f"  Scanning company: {company}")

        # List location folders under company
        locations = bucket.list(company)

        for loc_item in locations:
            location = loc_item.get("name")
            if not location or location.startswith("."):
                continue

            # Skip intro_outro folder (already PDFs)
            if location == "intro_outro":
                continue

            # List files in location folder
            files = bucket.list(f"{company}/{location}")

            for file_item in files:
                filename = file_item.get("name", "")
                if filename.endswith((".pptx", ".ppt")):
                    storage_key = f"{company}/{location}/{filename}"
                    templates.append({
                        "company": company,
                        "location": location,
                        "filename": filename,
                        "storage_key": storage_key,
                    })

    return templates


def check_pdf_exists(supabase, storage_key: str) -> bool:
    """Check if PDF version already exists."""
    pdf_key = storage_key.replace('.pptx', '.pdf').replace('.ppt', '.pdf')

    try:
        bucket = supabase.storage.from_("templates")
        bucket.download(pdf_key)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Convert PPTX templates to PDF")
    parser.add_argument("--dry-run", action="store_true", help="List templates without converting")
    parser.add_argument("--force", action="store_true", help="Re-convert even if PDF exists")
    args = parser.parse_args()

    print("=" * 60)
    print("PPTX to PDF Template Converter (Microsoft PowerPoint)")
    print("=" * 60)

    # Get client
    supabase = get_supabase_client()

    # List all templates
    print("\nScanning templates bucket...")
    templates = list_all_templates(supabase)
    print(f"\nFound {len(templates)} PPTX templates")

    if args.dry_run:
        print("\n[DRY RUN] Would convert:")
        for t in templates:
            print(f"  - {t['storage_key']}")
        return

    # Process each template
    bucket = supabase.storage.from_("templates")
    converted = 0
    skipped = 0
    errors = []

    for i, template in enumerate(templates, 1):
        storage_key = template["storage_key"]
        pdf_key = storage_key.replace('.pptx', '.pdf').replace('.ppt', '.pdf')

        print(f"\n[{i}/{len(templates)}] {storage_key}")

        # Check if PDF already exists
        if not args.force and check_pdf_exists(supabase, storage_key):
            print("  -> PDF already exists, skipping")
            skipped += 1
            continue

        try:
            # Download PPTX
            print("  -> Downloading PPTX...")
            pptx_data = bucket.download(storage_key)

            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp:
                tmp.write(pptx_data)
                pptx_path = tmp.name

            # Create temp path for PDF
            pdf_path = pptx_path.replace('.pptx', '.pdf')

            # Convert to PDF using PowerPoint
            print("  -> Converting via PowerPoint...")
            if not convert_pptx_to_pdf(pptx_path, pdf_path):
                raise Exception("PowerPoint conversion failed")

            # Read PDF
            with open(pdf_path, "rb") as f:
                pdf_data = f.read()

            # Upload PDF
            print(f"  -> Uploading PDF ({len(pdf_data) / 1024 / 1024:.1f} MB)...")
            bucket.upload(
                pdf_key,
                pdf_data,
                {"content-type": "application/pdf", "upsert": "true"}
            )

            # Cleanup temp files
            os.unlink(pptx_path)
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)

            print("  -> Done!")
            converted += 1

        except Exception as e:
            print(f"  -> ERROR: {e}")
            errors.append((storage_key, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Converted: {converted}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for key, err in errors:
            print(f"  - {key}: {err}")


if __name__ == "__main__":
    main()
