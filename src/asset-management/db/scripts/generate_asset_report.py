#!/usr/bin/env python3
"""
Generate Asset Hierarchy Report from Supabase Database.

Usage:
    python db/scripts/generate_asset_report.py          # DEV
    python db/scripts/generate_asset_report.py --prod   # PROD
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()
load_dotenv(Path(__file__).parent.parent.parent.parent.parent / ".env")

from supabase import Client, create_client


def get_supabase(prod: bool = False) -> Client:
    """Get Supabase client for DEV or PROD."""
    if prod:
        url = os.getenv("ASSETMGMT_PROD_SUPABASE_URL")
        key = os.getenv("ASSETMGMT_PROD_SUPABASE_SERVICE_ROLE_KEY")
    else:
        url = os.getenv("ASSETMGMT_DEV_SUPABASE_URL")
        key = os.getenv("ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        raise ValueError("Missing Supabase credentials")

    return create_client(url, key)


def generate_report(client: Client, env: str) -> str:
    """Generate the asset hierarchy report."""
    lines = []

    # Header
    lines.append("# Asset Management - Asset Hierarchy Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Environment:** {env}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Get networks from both schemas
    schemas = ["backlite_dubai", "backlite_abudhabi"]
    all_networks = {}
    all_packages = {}
    all_asset_types = {}

    for schema in schemas:
        # Networks
        networks = client.schema(schema).table("networks").select("*").order("network_key").execute()
        all_networks[schema] = networks.data

        # Packages with items
        packages = client.schema(schema).table("packages").select("*").order("package_key").execute()
        for pkg in packages.data:
            items = client.schema(schema).table("package_items").select("network_id").eq("package_id", pkg["id"]).execute()
            pkg["network_count"] = len(items.data)
            # Get network keys
            network_keys = []
            for item in items.data:
                net = client.schema(schema).table("networks").select("network_key").eq("id", item["network_id"]).execute()
                if net.data:
                    network_keys.append(net.data[0]["network_key"])
            pkg["network_keys"] = network_keys
        all_packages[schema] = packages.data

        # Asset types
        asset_types = client.schema(schema).table("asset_types").select("*, networks(network_key)").order("type_key").execute()
        all_asset_types[schema] = asset_types.data

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Schema | Networks | Packages | Asset Types |")
    lines.append("|--------|----------|----------|-------------|")
    total_networks = 0
    total_packages = 0
    total_types = 0
    for schema in schemas:
        n = len(all_networks[schema])
        p = len(all_packages[schema])
        t = len(all_asset_types[schema])
        total_networks += n
        total_packages += p
        total_types += t
        lines.append(f"| {schema} | {n} | {p} | {t} |")
    lines.append(f"| **Total** | **{total_networks}** | **{total_packages}** | **{total_types}** |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Dubai Networks
    lines.append("## Dubai Networks (backlite_dubai)")
    lines.append("")

    # Digital networks
    digital = [n for n in all_networks["backlite_dubai"] if n.get("display_type") == "digital"]
    if digital:
        lines.append("### Digital Networks")
        lines.append("")
        lines.append("| Network Key | Name | Standalone | Upload Fee |")
        lines.append("|-------------|------|------------|------------|")
        for n in sorted(digital, key=lambda x: x["network_key"]):
            standalone = "Yes" if n.get("standalone") else "No"
            fee = f"{int(n.get('upload_fee') or 0):,}" if n.get("upload_fee") else "N/A"
            lines.append(f"| {n['network_key']} | {n['name']} | {standalone} | {fee} |")
        lines.append("")

    # Static networks
    static = [n for n in all_networks["backlite_dubai"] if n.get("display_type") == "static"]
    if static:
        lines.append("### Static Networks")
        lines.append("")
        lines.append("| Network Key | Name | Standalone | Upload Fee |")
        lines.append("|-------------|------|------------|------------|")
        for n in sorted(static, key=lambda x: x["network_key"]):
            standalone = "Yes" if n.get("standalone") else "No"
            fee = f"{int(n.get('upload_fee') or 0):,}" if n.get("upload_fee") else "N/A"
            lines.append(f"| {n['network_key']} | {n['name']} | {standalone} | {fee} |")
        lines.append("")

    # Dubai packages
    if all_packages["backlite_dubai"]:
        lines.append("### Dubai Packages")
        lines.append("")
        lines.append("| Package Key | Name | Networks | Upload Fee |")
        lines.append("|-------------|------|----------|------------|")
        for p in all_packages["backlite_dubai"]:
            fee = f"{int(p.get('upload_fee') or 0):,}" if p.get("upload_fee") else "N/A"
            networks = ", ".join(p.get("network_keys", []))
            lines.append(f"| {p['package_key']} | {p['name']} | {networks} | {fee} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Abu Dhabi Networks
    lines.append("## Abu Dhabi Networks (backlite_abudhabi)")
    lines.append("")

    # Traditional networks (with asset types)
    traditional = [n for n in all_networks["backlite_abudhabi"] if not n.get("standalone")]
    if traditional:
        lines.append("### Traditional Networks (with Asset Types)")
        lines.append("")
        lines.append("| Network Key | Name | Asset Types | Upload Fee |")
        lines.append("|-------------|------|-------------|------------|")
        for n in sorted(traditional, key=lambda x: x["network_key"]):
            type_count = len([t for t in all_asset_types["backlite_abudhabi"] if t.get("networks", {}).get("network_key") == n["network_key"]])
            fee = f"{int(n.get('upload_fee') or 0):,}" if n.get("upload_fee") else "N/A"
            lines.append(f"| {n['network_key']} | {n['name']} | {type_count} | {fee} |")
        lines.append("")

    # Standalone networks
    standalone_nets = [n for n in all_networks["backlite_abudhabi"] if n.get("standalone")]
    if standalone_nets:
        lines.append("### Standalone Networks")
        lines.append("")
        lines.append("| Network Key | Name | Type | Upload Fee |")
        lines.append("|-------------|------|------|------------|")
        for n in sorted(standalone_nets, key=lambda x: x["network_key"]):
            fee = f"{int(n.get('upload_fee') or 0):,}" if n.get("upload_fee") else "N/A"
            lines.append(f"| {n['network_key']} | {n['name']} | {n.get('display_type', 'N/A')} | {fee} |")
        lines.append("")

    # Abu Dhabi packages
    if all_packages["backlite_abudhabi"]:
        lines.append("### Abu Dhabi Packages")
        lines.append("")
        lines.append("| Package Key | Name | Networks | Upload Fee |")
        lines.append("|-------------|------|----------|------------|")
        for p in all_packages["backlite_abudhabi"]:
            fee = f"{int(p.get('upload_fee') or 0):,}" if p.get("upload_fee") else "N/A"
            networks = ", ".join(p.get("network_keys", []))
            lines.append(f"| {p['package_key']} | {p['name']} | {networks} | {fee} |")
        lines.append("")

    lines.append("---")
    lines.append("")

    # Asset Types Detail
    lines.append("## Asset Types Detail")
    lines.append("")

    # Group by network
    types_by_network = {}
    for schema in schemas:
        for t in all_asset_types[schema]:
            net_key = t.get("networks", {}).get("network_key", "unknown")
            if net_key not in types_by_network:
                types_by_network[net_key] = []
            types_by_network[net_key].append(t["type_key"])

    for net_key in sorted(types_by_network.keys()):
        types = types_by_network[net_key]
        lines.append(f"### {net_key} ({len(types)} types)")
        lines.append("")
        for t in sorted(types):
            lines.append(f"- {t}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate Asset Hierarchy Report")
    parser.add_argument("--prod", action="store_true", help="Use PROD environment")
    parser.add_argument("--output", "-o", type=str, help="Output file path")
    args = parser.parse_args()

    env = "PROD" if args.prod else "DEV"
    print(f"Generating report from {env} Supabase...")

    client = get_supabase(prod=args.prod)
    report = generate_report(client, env)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report)
        print(f"Report saved to: {output_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
