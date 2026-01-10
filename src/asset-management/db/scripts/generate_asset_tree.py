#!/usr/bin/env python3
"""
Asset Hierarchy Visualization Generator

Generates a visual tree structure of all assets in the Backlite Media
Asset Management system, suitable for sharing with management.

Features:
- Queries Supabase for networks, asset_types, packages, package_items
- Lists storage bucket contents (mockups, templates)
- Generates formatted ASCII tree with icons
- Outputs to markdown, plain text, or JSON
- Includes summary statistics

Usage:
    # Generate full report (markdown)
    python db/scripts/generate_asset_tree.py

    # Generate for specific company
    python db/scripts/generate_asset_tree.py --company backlite_dubai

    # Output formats
    python db/scripts/generate_asset_tree.py --format md
    python db/scripts/generate_asset_tree.py --format txt
    python db/scripts/generate_asset_tree.py --format json

    # Save to specific file
    python db/scripts/generate_asset_tree.py --output report.md
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()
load_dotenv(Path(__file__).parent.parent.parent.parent.parent / ".env")

from supabase import Client, create_client

# =============================================================================
# CONFIGURATION
# =============================================================================

VALID_SCHEMAS = ["backlite_dubai", "backlite_abudhabi", "backlite_uk", "viola"]
DEFAULT_SCHEMAS = ["backlite_dubai", "backlite_abudhabi"]

# Icons for tree visualization
ICONS = {
    "folder": "📁",
    "network": "📍",
    "asset_type": "🔹",
    "package": "📦",
    "template": "📋",
    "mockup": "📸",
    "frame": "🖼️",
    "link": "🔗",
    "traditional": "🏢",
    "standalone": "🏗️",
    "warning": "⚠️",
    "digital": "[DIGITAL]",
    "static": "[STATIC]",
}


def get_supabase(prod: bool = False) -> Client:
    """Get Supabase client for DEV or PROD."""
    if prod:
        url = os.getenv("ASSETMGMT_PROD_SUPABASE_URL")
        key = os.getenv("ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY")
        env_name = "PROD"
    else:
        url = os.getenv("ASSETMGMT_DEV_SUPABASE_URL")
        key = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY")
        env_name = "DEV"

    if not url or not key:
        raise ValueError(
            f"Missing Supabase credentials for {env_name}.\n"
            f"Set ASSETMGMT_{env_name}_SUPABASE_URL and ASSETMGMT_{env_name}_SUPABASE_SERVICE_ROLE_KEY"
        )

    return create_client(url, key)


# =============================================================================
# DATA FETCHING
# =============================================================================


def fetch_networks(client: Client, schema: str) -> list[dict]:
    """Fetch all networks from a schema."""
    try:
        result = client.schema(schema).table("networks").select("*").order("network_key").execute()
        return result.data or []
    except Exception as e:
        print(f"Warning: Could not fetch networks from {schema}: {e}")
        return []


def fetch_asset_types(client: Client, schema: str) -> list[dict]:
    """Fetch all asset types from a schema."""
    try:
        result = client.schema(schema).table("asset_types").select("*").order("type_key").execute()
        return result.data or []
    except Exception as e:
        print(f"Warning: Could not fetch asset_types from {schema}: {e}")
        return []


def fetch_packages(client: Client, schema: str) -> list[dict]:
    """Fetch all packages from a schema."""
    try:
        result = client.schema(schema).table("packages").select("*").order("package_key").execute()
        return result.data or []
    except Exception as e:
        print(f"Warning: Could not fetch packages from {schema}: {e}")
        return []


def fetch_package_items(client: Client, schema: str) -> list[dict]:
    """Fetch all package items from a schema."""
    try:
        result = client.schema(schema).table("package_items").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"Warning: Could not fetch package_items from {schema}: {e}")
        return []


def fetch_mockup_frames(client: Client, schema: str) -> list[dict]:
    """Fetch all mockup frames from a schema."""
    try:
        result = client.schema(schema).table("mockup_frames").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"Warning: Could not fetch mockup_frames from {schema}: {e}")
        return []


def fetch_storage_files(client: Client, bucket: str, prefix: str = "") -> list[dict]:
    """Fetch files from a storage bucket."""
    try:
        result = client.storage.from_(bucket).list(prefix)
        return result or []
    except Exception as e:
        print(f"Warning: Could not list {bucket}/{prefix}: {e}")
        return []


def get_storage_tree(client: Client, bucket: str, company: str) -> dict:
    """Build a tree structure of storage contents for a company."""
    tree = defaultdict(lambda: defaultdict(list))

    try:
        # List top-level folders under company
        folders = fetch_storage_files(client, bucket, company)

        for folder in folders:
            if folder.get("name"):
                folder_name = folder["name"]
                # List contents of each folder
                contents = fetch_storage_files(client, bucket, f"{company}/{folder_name}")
                tree[folder_name] = {
                    "files": [c.get("name") for c in contents if c.get("name")],
                    "count": len(contents),
                }
    except Exception as e:
        print(f"Warning: Could not build storage tree for {bucket}/{company}: {e}")

    return dict(tree)


# =============================================================================
# DATA ORGANIZATION
# =============================================================================


def organize_data(client: Client, schemas: list[str]) -> dict:
    """Fetch and organize all data from specified schemas."""
    data = {}

    for schema in schemas:
        print(f"Fetching data from {schema}...")

        networks = fetch_networks(client, schema)
        asset_types = fetch_asset_types(client, schema)
        packages = fetch_packages(client, schema)
        package_items = fetch_package_items(client, schema)
        mockup_frames = fetch_mockup_frames(client, schema)

        # Index asset types by network_id
        types_by_network = defaultdict(list)
        for at in asset_types:
            types_by_network[at.get("network_id")].append(at)

        # Index package items by package_id
        items_by_package = defaultdict(list)
        for pi in package_items:
            items_by_package[pi.get("package_id")].append(pi)

        # Index mockup frames by location_key
        frames_by_location = defaultdict(list)
        for mf in mockup_frames:
            frames_by_location[mf.get("location_key")].append(mf)

        # Create network lookup
        network_by_id = {n["id"]: n for n in networks}

        # Separate traditional and standalone networks
        traditional_networks = [n for n in networks if not n.get("standalone", True)]
        standalone_networks = [n for n in networks if n.get("standalone", True)]

        # Get storage info
        mockups_storage = get_storage_tree(client, "mockups", schema)
        templates_storage = get_storage_tree(client, "templates", schema)

        data[schema] = {
            "networks": networks,
            "traditional_networks": traditional_networks,
            "standalone_networks": standalone_networks,
            "asset_types": asset_types,
            "types_by_network": dict(types_by_network),
            "packages": packages,
            "package_items": package_items,
            "items_by_package": dict(items_by_package),
            "mockup_frames": mockup_frames,
            "frames_by_location": dict(frames_by_location),
            "network_by_id": network_by_id,
            "mockups_storage": mockups_storage,
            "templates_storage": templates_storage,
        }

    return data


# =============================================================================
# TREE GENERATION
# =============================================================================


def generate_tree_lines(data: dict) -> list[str]:
    """Generate ASCII tree lines from organized data."""
    lines = []

    lines.append("```")
    lines.append("BACKLITE MEDIA ASSET MANAGEMENT")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    schemas = list(data.keys())

    for i, schema in enumerate(schemas):
        schema_data = data[schema]
        is_last_schema = (i == len(schemas) - 1)
        prefix = "└── " if is_last_schema else "├── "
        child_prefix = "    " if is_last_schema else "│   "

        lines.append(f"{prefix}{ICONS['folder']} {schema}/")

        # Traditional Networks
        traditional = schema_data["traditional_networks"]
        standalone = schema_data["standalone_networks"]
        packages = schema_data["packages"]

        has_packages = len(packages) > 0
        has_standalone = len(standalone) > 0

        if traditional:
            trad_prefix = "├── " if (has_standalone or has_packages) else "└── "
            lines.append(f"{child_prefix}│")
            lines.append(f"{child_prefix}{trad_prefix}{ICONS['traditional']} TRADITIONAL NETWORKS (standalone=false)")

            for j, network in enumerate(traditional):
                is_last_trad = (j == len(traditional) - 1) and not has_standalone and not has_packages
                net_prefix = "│   └── " if (j == len(traditional) - 1) else "│   ├── "
                net_child = "│       " if (j < len(traditional) - 1) else "        "

                display_type = ICONS['digital'] if network.get('display_type') == 'digital' else ICONS['static']
                lines.append(f"{child_prefix}{net_prefix}{ICONS['network']} {network['network_key']}/ {display_type}")

                # Template
                lines.append(f"{child_prefix}{net_child}├── {ICONS['template']} template: templates/{schema}/{network['network_key']}/{network['network_key']}.pptx")

                # Asset types
                network_types = schema_data["types_by_network"].get(network["id"], [])
                for k, at in enumerate(network_types):
                    is_last_type = (k == len(network_types) - 1)
                    type_prefix = "└── " if is_last_type else "├── "
                    lines.append(f"{child_prefix}{net_child}{type_prefix}{ICONS['asset_type']} asset_type: {at['type_key']}")

                    # Mockup path
                    type_child = "    " if is_last_type else "│   "
                    lines.append(f"{child_prefix}{net_child}{type_child}├── {ICONS['mockup']} mockups/{schema}/{network['network_key']}/{at['type_key']}/outdoor/...")

                    # Frame count
                    frames = [f for f in schema_data["frames_by_location"].get(network['network_key'], [])
                              if f.get("type_key") == at['type_key']]
                    frame_count = len(frames)
                    lines.append(f"{child_prefix}{net_child}{type_child}└── {ICONS['frame']} mockup_frames: {frame_count} frames")

        # Standalone Networks
        if standalone:
            stand_prefix = "├── " if has_packages else "└── "
            lines.append(f"{child_prefix}│")
            lines.append(f"{child_prefix}{stand_prefix}{ICONS['standalone']} STANDALONE NETWORKS (standalone=true)")

            for j, network in enumerate(standalone):
                is_last_stand = (j == len(standalone) - 1)
                net_prefix = "│   └── " if is_last_stand else "│   ├── "
                net_child = "│       " if not is_last_stand else "        "

                display_type = ICONS['digital'] if network.get('display_type') == 'digital' else ICONS['static']
                lines.append(f"{child_prefix}{net_prefix}{ICONS['network']} {network['network_key']}/ {display_type}")

                # Template
                lines.append(f"{child_prefix}{net_child}├── {ICONS['template']} template: templates/{schema}/{network['network_key']}/{network['network_key']}.pptx")

                # Mockup
                lines.append(f"{child_prefix}{net_child}├── {ICONS['mockup']} mockups/{schema}/{network['network_key']}/outdoor/...")

                # Frame count
                frames = schema_data["frames_by_location"].get(network['network_key'], [])
                frame_count = len(frames)
                lines.append(f"{child_prefix}{net_child}└── {ICONS['frame']} mockup_frames: {frame_count} frames")

        # Packages
        if packages:
            lines.append(f"{child_prefix}│")
            lines.append(f"{child_prefix}└── {ICONS['package']} PACKAGES (bundles of networks)")

            for j, package in enumerate(packages):
                is_last_pkg = (j == len(packages) - 1)
                pkg_prefix = "    └── " if is_last_pkg else "    ├── "
                pkg_child = "        " if is_last_pkg else "    │   "

                lines.append(f"{child_prefix}{pkg_prefix}{ICONS['package']} {package['package_key']}/")

                # Package items
                items = schema_data["items_by_package"].get(package["id"], [])
                for k, item in enumerate(items):
                    is_last_item = (k == len(items) - 1)
                    item_prefix = "└── " if is_last_item else "├── "

                    network_id = item.get("network_id")
                    network = schema_data["network_by_id"].get(network_id, {})
                    network_key = network.get("network_key", f"network_id={network_id}")

                    lines.append(f"{child_prefix}{pkg_child}{item_prefix}{ICONS['link']} includes: {network_key}")

        lines.append("")

    lines.append("```")
    return lines


def generate_summary(data: dict) -> list[str]:
    """Generate summary statistics."""
    lines = []

    lines.append("")
    lines.append("## Summary Statistics")
    lines.append("")
    lines.append("```")
    lines.append("┌─────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│                         ASSET INVENTORY SUMMARY                             │")
    lines.append("└─────────────────────────────────────────────────────────────────────────────┘")
    lines.append("")

    total_networks = 0
    total_types = 0
    total_packages = 0
    total_frames = 0

    for schema, schema_data in data.items():
        trad_count = len(schema_data["traditional_networks"])
        stand_count = len(schema_data["standalone_networks"])
        type_count = len(schema_data["asset_types"])
        pkg_count = len(schema_data["packages"])
        frame_count = len(schema_data["mockup_frames"])

        total_networks += trad_count + stand_count
        total_types += type_count
        total_packages += pkg_count
        total_frames += frame_count

        lines.append(f"  {schema.upper()}")
        lines.append(f"  ├── Networks:        {trad_count + stand_count} total")
        lines.append(f"  │   ├── Traditional: {trad_count}")
        lines.append(f"  │   └── Standalone:  {stand_count}")
        lines.append(f"  ├── Asset Types:     {type_count}")
        lines.append(f"  ├── Packages:        {pkg_count}")
        lines.append(f"  └── Mockup Frames:   {frame_count}")
        lines.append("")

    lines.append("  ─────────────────────────────")
    lines.append(f"  TOTAL NETWORKS:      {total_networks}")
    lines.append(f"  TOTAL ASSET TYPES:   {total_types}")
    lines.append(f"  TOTAL PACKAGES:      {total_packages}")
    lines.append(f"  TOTAL MOCKUP FRAMES: {total_frames}")
    lines.append("")
    lines.append("┌─────────────────────────────────────────────────────────────────────────────┐")
    lines.append("│  Legend:                                                                    │")
    lines.append("│  📁 = Folder/Schema    📍 = Network    🔹 = Asset Type    📦 = Package      │")
    lines.append("│  📋 = Template         📸 = Mockup Photos    🖼️ = Mockup Frame DB Record   │")
    lines.append("│  🔗 = Package Link     🏢 = Traditional    🏗️ = Standalone                 │")
    lines.append("│  [DIGITAL] = Digital Display    [STATIC] = Static Billboard                │")
    lines.append("└─────────────────────────────────────────────────────────────────────────────┘")
    lines.append("```")

    return lines


def generate_markdown_report(data: dict) -> str:
    """Generate full markdown report."""
    lines = []

    lines.append("# Backlite Media Asset Management")
    lines.append("")
    lines.append("## Asset Hierarchy")
    lines.append("")
    lines.extend(generate_tree_lines(data))
    lines.extend(generate_summary(data))
    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated on {datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}*")

    return "\n".join(lines)


def generate_json_report(data: dict) -> str:
    """Generate JSON report."""
    report = {
        "generated_at": datetime.now().isoformat(),
        "schemas": {}
    }

    for schema, schema_data in data.items():
        report["schemas"][schema] = {
            "networks": {
                "traditional": [
                    {
                        "network_key": n["network_key"],
                        "name": n.get("name"),
                        "display_type": n.get("display_type"),
                        "asset_types": [
                            at["type_key"] for at in schema_data["types_by_network"].get(n["id"], [])
                        ],
                        "mockup_frames_count": len(schema_data["frames_by_location"].get(n["network_key"], []))
                    }
                    for n in schema_data["traditional_networks"]
                ],
                "standalone": [
                    {
                        "network_key": n["network_key"],
                        "name": n.get("name"),
                        "display_type": n.get("display_type"),
                        "mockup_frames_count": len(schema_data["frames_by_location"].get(n["network_key"], []))
                    }
                    for n in schema_data["standalone_networks"]
                ]
            },
            "packages": [
                {
                    "package_key": p["package_key"],
                    "name": p.get("name"),
                    "networks": [
                        schema_data["network_by_id"].get(item.get("network_id"), {}).get("network_key")
                        for item in schema_data["items_by_package"].get(p["id"], [])
                    ]
                }
                for p in schema_data["packages"]
            ],
            "summary": {
                "total_networks": len(schema_data["networks"]),
                "traditional_networks": len(schema_data["traditional_networks"]),
                "standalone_networks": len(schema_data["standalone_networks"]),
                "asset_types": len(schema_data["asset_types"]),
                "packages": len(schema_data["packages"]),
                "mockup_frames": len(schema_data["mockup_frames"])
            }
        }

    return json.dumps(report, indent=2)


# =============================================================================
# MAIN
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generate asset hierarchy visualization report"
    )
    parser.add_argument(
        "--company",
        type=str,
        help=f"Filter to specific company schema: {', '.join(VALID_SCHEMAS)}",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["md", "txt", "json"],
        default="md",
        help="Output format (default: md)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: asset_hierarchy_report.{format})",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Use PROD database (default: DEV)",
    )
    parser.add_argument(
        "--print",
        action="store_true",
        dest="print_output",
        help="Print to stdout instead of file",
    )

    args = parser.parse_args()

    # Determine schemas to query
    if args.company:
        if args.company not in VALID_SCHEMAS:
            print(f"Error: Invalid company '{args.company}'. Valid options: {', '.join(VALID_SCHEMAS)}")
            sys.exit(1)
        schemas = [args.company]
    else:
        schemas = DEFAULT_SCHEMAS

    # Connect to Supabase
    print(f"Connecting to {'PROD' if args.prod else 'DEV'} Supabase...")
    client = get_supabase(prod=args.prod)

    # Fetch and organize data
    data = organize_data(client, schemas)

    # Generate report
    if args.format == "json":
        report = generate_json_report(data)
        ext = "json"
    else:
        report = generate_markdown_report(data)
        ext = "md" if args.format == "md" else "txt"

    # Output
    if args.print_output:
        print(report)
    else:
        output_path = args.output or f"asset_hierarchy_report.{ext}"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n✅ Report saved to: {output_path}")
        print(f"   Total size: {len(report):,} characters")


if __name__ == "__main__":
    main()
