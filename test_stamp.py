#!/usr/bin/env python3
"""
Quick test script to create a dated stamp and test placement on a PDF
"""
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
from pathlib import Path
import asyncio
import sys

async def create_dated_stamp():
    """Create stamp with today's date"""
    # Use stamp.png (original, don't overwrite)
    original_stamp_path = Path("stamp.png")
    if not original_stamp_path.exists():
        print(f"ERROR: stamp.png not found!")
        return None

    # Load original stamp
    logo = Image.open(original_stamp_path).convert("RGBA")
    width, height = logo.size

    # Get today's date
    today = datetime.now().strftime("%d-%m-%Y")

    # Create drawing context on the logo itself (don't extend canvas)
    draw = ImageDraw.Draw(logo)

    # Try to use a nice BOLD font, fallback to default
    try:
        # Use Helvetica Bold
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60, index=1)  # index=1 for bold
    except:
        try:
            font = ImageFont.truetype("/Library/Fonts/Arial Bold.ttf", 48)
        except:
            try:
                font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 48)
            except:
                font = ImageFont.load_default()

    # Position date lower on the stamp
    # Get text bounding box to center it
    bbox = draw.textbbox((0, 0), today, font=font)
    text_width = bbox[2] - bbox[0]
    text_x = (width - text_width) // 2 + 40  # Shifted right by 40 pixels
    text_y = int(height * 0.521)  # Place at 53% down from top

    # Draw date in black with white outline for visibility
    # Draw outline (white)
    for adj_x in [-2, -1, 0, 1, 2]:
        for adj_y in [-2, -1, 0, 1, 2]:
            if adj_x != 0 or adj_y != 0:
                draw.text((text_x + adj_x, text_y + adj_y), today, fill=(255, 255, 255, 255), font=font)
    # Draw main text (black)
    draw.text((text_x, text_y), today, fill=(0, 0, 0, 255), font=font)

    # Save as stamp_dated.png (don't overwrite original)
    output_path = Path("stamp_dated.png")
    logo.save(output_path)
    print(f"✓ Created dated stamp: {output_path}")
    print(f"  Size: {logo.size[0]}x{logo.size[1]} pixels")
    print(f"  Date: {today}")
    print(f"  Position: top 1/8 of stamp (y={text_y})")

    return output_path

async def test_stamp_on_pdf(pdf_path: str):
    """Test stamping on a provided PDF"""
    from booking_parser import BookingOrderParser

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        print(f"ERROR: PDF not found: {pdf_file}")
        return

    parser = BookingOrderParser(company="test")

    print(f"\n📄 Testing stamp placement on: {pdf_file}")
    print("=" * 60)

    # Apply stamp
    stamped_path = await parser._apply_stamp_to_pdf(pdf_file)

    if stamped_path != pdf_file:
        print(f"\n✓ Stamp applied successfully!")
        print(f"  Output: {stamped_path}")
    else:
        print(f"\n⚠ Stamp was not applied (no suitable placement found)")

async def main():
    print("=" * 60)
    print("STAMP PLACEMENT TEST SCRIPT")
    print("=" * 60)

    # Step 1: Create dated stamp
    print("\n1. Creating dated stamp from logo.png...")
    stamp_path = await create_dated_stamp()

    if not stamp_path:
        return

    # Step 2: Test on PDF if provided
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        await test_stamp_on_pdf(pdf_path)
    else:
        print("\n" + "=" * 60)
        print("To test stamp placement on a PDF, run:")
        print(f"  python test_stamp.py <path_to_pdf>")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
