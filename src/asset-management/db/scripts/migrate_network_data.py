#!/usr/bin/env python3
"""
Network Data Migration Script - Excel to Supabase (Unified Schema)

Migrates network data from master_network_data_for_upload_v1.xlsx to Supabase.
Uses the unified networks architecture where ALL sellable entities are networks.

Also migrates:
- Mockup photos from data_backup_prod/data/mockups/ to Supabase Storage
- Templates from data_backup_prod/data/templates/ to Supabase Storage

Data Routing:
- Dubai networks → backlite_dubai schema
- Abu Dhabi networks → backlite_abudhabi schema

Usage:
    # Dry run (preview changes):
    python db/scripts/migrate_network_data.py --dry-run

    # Execute against DEV (default):
    python db/scripts/migrate_network_data.py

    # Execute against PROD:
    python db/scripts/migrate_network_data.py --prod

    # Clear existing data first (REPLACE ALL):
    python db/scripts/migrate_network_data.py --clear

    # Skip storage migration (database only):
    python db/scripts/migrate_network_data.py --skip-storage

Prerequisites:
    - Schema must be applied: asset-management/db/migrations/01_schema.sql
    - Environment variables: ASSETMGMT_DEV_SUPABASE_URL, ASSETMGMT_DEV_SUPABASE_SERVICE_ROLE_KEY
    - Excel file: master_network_data_for_upload_v1.xlsx in asset-management root
    - Backup data: sales-module/data_backup_prod/data/mockups/ and templates/
"""

import argparse
import mimetypes
import os
import sys
from pathlib import Path

import pandas as pd

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

PROJECT_ROOT = Path(__file__).parent.parent.parent  # asset-management/
EXCEL_FILE = PROJECT_ROOT / "master_network_data_for_upload_v1.xlsx"

# City to schema mapping
CITY_SCHEMA_MAP = {
    "Dubai": "backlite_dubai",
    "Abu Dhabi": "backlite_abudhabi",
}
DEFAULT_SCHEMA = "backlite_dubai"

# Valid company schemas
VALID_SCHEMAS = ["backlite_dubai", "backlite_uk", "backlite_abudhabi", "viola"]

# =============================================================================
# SPECIAL NETWORK OVERRIDES
# Traditional networks with asset_types (Galleria only now)
# =============================================================================

SPECIAL_TRADITIONAL_NETWORKS = {
    # Galleria networks remain as traditional (standalone=false with asset_types)
    # These are defined in Excel, no overrides needed here
}

# =============================================================================
# HELIX PACKAGE CONFIGURATION
# The Helix is a PACKAGE containing 4 standalone DNA networks
# =============================================================================

HELIX_PACKAGE = {
    "package_key": "the_helix",
    "name": "The Helix",
    "upload_fee": 3000,
    "city": "Dubai",
    "networks": [
        {"network_key": "dna01", "name": "DNA01", "upload_fee": 3000},
        {"network_key": "dna02", "name": "DNA02", "upload_fee": 3000},  # formerly bl108
        {"network_key": "dna03", "name": "DNA03", "upload_fee": 3000},
        {"network_key": "dna04", "name": "DNA04", "upload_fee": 3000},  # formerly bl308
    ],
}

# Legacy networks to add that might not be in Excel
LEGACY_NETWORKS = [
    {"network_key": "uae12", "network_name": "UAE12", "type": "static", "city": "Dubai", "standalone": 1.0},
    {"network_key": "uae36", "network_name": "UAE36", "type": "static", "city": "Dubai", "standalone": 1.0},
    {"network_key": "uae36a", "network_name": "UAE36a", "type": "static", "city": "Dubai", "standalone": 1.0},
    {"network_key": "uae37", "network_name": "UAE37", "type": "static", "city": "Dubai", "standalone": 1.0},
    {"network_key": "uae38", "network_name": "UAE38", "type": "static", "city": "Dubai", "standalone": 1.0},
]

# =============================================================================
# UPLOAD FEE CONFIGURATION
# These are the known upload fees from the existing database.
# Digital networks: use existing values
# Static networks: default to 3000 if missing
# =============================================================================

DEFAULT_UPLOAD_FEE = 3000  # Default for networks without upload_fee
DEFAULT_COUNTRY = "UAE"  # Default country for all networks

# Known upload fees from existing database (digital networks)
KNOWN_UPLOAD_FEES = {
    # DNA networks (Dubai) - part of The Helix package
    "dna01": 3000,
    "dna02": 3000,  # formerly bl108
    "dna03": 3000,
    "dna04": 3000,  # formerly bl308
    # Other digital networks - Dubai
    "dubai_gateway": 2000,
    "dubai_jawhara": 1000,
    "oryx": 1500,
    "triple_crown_dubai": 3000,
    # Digital networks - Abu Dhabi
    "alqana": 3000,
    "triple_crown_abu_dhabi": 3000,
    # Galleria networks (Abu Dhabi) - traditional networks
    "galleria_extension_indoor": 3000,
    "galleria_extension_outdoor": 3000,
    "galleria_luxury_indoor": 3000,
    "galleria_luxury_outdoor": 3000,
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

    print(f"Connecting to {env_name} Supabase: {url}")
    return create_client(url, key)


def fetch_existing_upload_fees(client: Client) -> dict[str, float]:
    """
    Fetch existing upload_fee values from the database.
    Returns: {network_key: upload_fee}
    """
    print("\n  Fetching existing upload fees from database...")
    fees = {}

    for schema in VALID_SCHEMAS:
        try:
            result = client.schema(schema).table("networks").select("network_key, upload_fee").execute()
            for row in result.data:
                if row.get("upload_fee") is not None:
                    fees[row["network_key"]] = float(row["upload_fee"])
        except Exception as e:
            print(f"    Warning: Could not fetch from {schema}: {e}")

    print(f"    Found {len(fees)} networks with upload fees")
    return fees


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def safe_int(value) -> int | None:
    """Convert value to int, handling NaN and strings."""
    if pd.isna(value):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def safe_float(value) -> float | None:
    """Convert value to float, handling NaN."""
    if pd.isna(value):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def safe_str(value) -> str | None:
    """Convert value to string, handling NaN."""
    if pd.isna(value):
        return None
    s = str(value).strip()
    return s if s else None


def get_schema_for_city(city: str) -> str:
    """Get company schema based on city."""
    if pd.isna(city) or not city:
        return DEFAULT_SCHEMA
    return CITY_SCHEMA_MAP.get(city, DEFAULT_SCHEMA)


def parse_asset_types(asset_types_str: str) -> list[dict]:
    """Parse comma-separated asset types into list of dicts."""
    if pd.isna(asset_types_str) or not asset_types_str:
        return []

    types = []
    for name in str(asset_types_str).split(","):
        name = name.strip()
        if not name:
            continue

        # Generate type_key from name (lowercase, underscores, no special chars)
        type_key = name.lower()
        type_key = type_key.replace(" ", "_")
        type_key = type_key.replace("(", "").replace(")", "")
        type_key = type_key.replace("-", "_")
        type_key = type_key.replace(".", "")

        types.append({
            "name": name,
            "type_key": type_key,
        })

    return types


# =============================================================================
# DATA LOADING
# =============================================================================

def normalize_key(key: str) -> str:
    """Normalize a key by replacing spaces with underscores and lowercasing."""
    if not key:
        return key
    return key.strip().lower().replace(" ", "_").replace("-", "_")


def load_excel_data(excel_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load and parse Excel data into networks and packages DataFrames."""
    print(f"Loading data from: {excel_path}")

    df = pd.read_excel(excel_path)

    # Find where packages section starts (row with "package_name" in network_key column)
    package_header_idx = df[df["network_key"] == "package_name"].index

    if len(package_header_idx) > 0:
        split_idx = package_header_idx[0]
        networks_df = df.iloc[:split_idx].copy()
        packages_df = df.iloc[split_idx + 1:].copy()

        # Rename package columns
        packages_df = packages_df.rename(columns={
            "network_key": "package_key",
            "network_name": "network_keys_combined",
        })
        packages_df = packages_df[packages_df["package_key"].notna()]

        # Normalize package keys (fix spaces like "galleria_outdoor domination" -> "galleria_outdoor_domination")
        packages_df["package_key"] = packages_df["package_key"].apply(normalize_key)
        print(f"  Normalized package keys")
    else:
        networks_df = df.copy()
        packages_df = pd.DataFrame()

    # Filter valid networks (must have network_key and type)
    networks_df = networks_df[networks_df["network_key"].notna()]
    networks_df = networks_df[networks_df["type"].notna()]

    # Networks to SKIP (they're now packages or don't exist)
    # - the_helix: Now a package, not a network
    # - bl108, bl308: Don't exist anymore (they're dna02, dna04)
    # - digital_icons: Doesn't exist anymore
    # - helix_network_dna*: Duplicates - DNA networks are created by HELIX_PACKAGE
    skip_networks = {
        "the_helix", "bl108", "bl308", "digital_icons",
        "helix_network_dna01", "helix_network_dna02", "helix_network_dna03", "helix_network_dna04",
    }

    # Fix known typos in Excel
    typo_fixes = {
        "ua43": "uae43",
        "the_oryx": "oryx",  # Normalize: remove "the_" prefix
    }

    # Apply typo fixes
    for old_key, new_key in typo_fixes.items():
        mask = networks_df["network_key"] == old_key
        if mask.any():
            networks_df.loc[mask, "network_key"] = new_key
            print(f"  Fixed typo: {old_key} -> {new_key}")
    before_count = len(networks_df)
    networks_df = networks_df[~networks_df["network_key"].isin(skip_networks)]
    skipped = before_count - len(networks_df)
    if skipped > 0:
        print(f"  Skipped {skipped} networks (now packages or deprecated): {skip_networks}")

    # Apply special overrides for traditional networks (Galleria only now)
    print("  Applying special network overrides...")
    for network_key, overrides in SPECIAL_TRADITIONAL_NETWORKS.items():
        mask = networks_df["network_key"] == network_key
        if mask.any():
            # Update existing row
            for col, val in overrides.items():
                if col == "standalone":
                    networks_df.loc[mask, col] = 0.0 if not val else 1.0
                elif col == "display_type":
                    networks_df.loc[mask, "type"] = val
                else:
                    networks_df.loc[mask, col] = val
            print(f"    Updated: {network_key} -> traditional with asset_types")
        else:
            # Add new row for this network
            new_row = {
                "network_key": network_key,
                "network_name": network_key.replace("_", " ").title(),
                "type": overrides.get("display_type", "digital"),
                "city": overrides.get("city", "Dubai"),
                "standalone": 0.0 if not overrides.get("standalone", False) else 1.0,
                "asset_types": overrides.get("asset_types", ""),
            }
            networks_df = pd.concat([networks_df, pd.DataFrame([new_row])], ignore_index=True)
            print(f"    Added: {network_key} -> traditional with asset_types")

    # Add legacy networks if not present
    existing_keys = set(networks_df["network_key"].tolist())
    legacy_added = 0
    for legacy in LEGACY_NETWORKS:
        if legacy["network_key"] not in existing_keys:
            networks_df = pd.concat([networks_df, pd.DataFrame([legacy])], ignore_index=True)
            legacy_added += 1
    if legacy_added:
        print(f"    Added {legacy_added} legacy networks")

    print(f"  Total: {len(networks_df)} networks and {len(packages_df)} packages")
    return networks_df, packages_df


# =============================================================================
# MIGRATION STEPS
# =============================================================================

def clear_existing_data(client: Client, schema: str, dry_run: bool = False) -> None:
    """Clear existing data from a schema (respecting FK constraints)."""
    print(f"\n  Clearing existing data in {schema}...")

    tables = ["package_items", "packages", "asset_types", "networks"]

    for table in tables:
        if dry_run:
            print(f"    [DRY RUN] Would delete from {schema}.{table}")
        else:
            try:
                # Delete all rows (neq id 0 is a trick to delete all)
                client.schema(schema).table(table).delete().neq("id", 0).execute()
                print(f"    Cleared: {schema}.{table}")
            except Exception as e:
                print(f"    Warning clearing {table}: {e}")


def migrate_networks(
    client: Client,
    networks_df: pd.DataFrame,
    existing_fees: dict[str, float] | None = None,
    dry_run: bool = False,
) -> dict[str, dict]:
    """
    Migrate networks to Supabase.

    Args:
        existing_fees: Optional dict of {network_key: upload_fee} from DB fetch

    Returns: {network_key: {"id": int, "schema": str, "standalone": bool}}
    """
    print("\n" + "=" * 60)
    print("STEP 1: MIGRATE NETWORKS")
    print("=" * 60)

    # Merge known fees with fetched fees (fetched takes precedence)
    all_known_fees = {**KNOWN_UPLOAD_FEES}
    if existing_fees:
        all_known_fees.update(existing_fees)

    network_map = {}

    # Group networks by schema (based on city)
    networks_by_schema: dict[str, list] = {}
    for _, row in networks_df.iterrows():
        schema = get_schema_for_city(row.get("city"))
        if schema not in networks_by_schema:
            networks_by_schema[schema] = []
        networks_by_schema[schema].append(row)

    for schema, networks in networks_by_schema.items():
        print(f"\n  Schema: {schema} ({len(networks)} networks)")

        for row in networks:
            network_key = row["network_key"]
            standalone = safe_float(row.get("standalone", 1)) == 1.0

            # Determine upload_fee:
            # 1. Use value from Excel if present
            # 2. Else use known/fetched value from database
            # 3. Else use default (3000)
            upload_fee = safe_float(row.get("upload_fee"))
            if upload_fee is None:
                upload_fee = all_known_fees.get(network_key, DEFAULT_UPLOAD_FEE)

            # Determine city (required for schema routing)
            city = safe_str(row.get("city"))
            if not city:
                # Default to Dubai for backlite_dubai schema
                city = "Dubai"

            # Determine country
            country = safe_str(row.get("country"))
            if not country:
                country = DEFAULT_COUNTRY

            network_data = {
                "network_key": network_key,
                "name": row["network_name"],
                "standalone": standalone,
                "display_type": safe_str(row.get("type")),
                "city": city,
                "country": country,
                "sov_percent": safe_float(row.get("sov_percent")),
                "upload_fee": upload_fee,
                "loop_duration": safe_int(row.get("loop_seconds")),
                "spot_duration": safe_int(row.get("spots_in_loop")),
                "width": safe_str(row.get("width")),
                "height": safe_str(row.get("height")),
                "number_of_faces": safe_int(row.get("number_of_faces")),
                "is_active": True,
                "created_by": "excel_migration",
            }

            # Remove None values
            network_data = {k: v for k, v in network_data.items() if v is not None}

            if dry_run:
                print(f"    [DRY RUN] {network_key} (standalone={standalone})")
                network_map[network_key] = {"id": None, "schema": schema, "standalone": standalone}
            else:
                try:
                    result = client.schema(schema).table("networks").insert(network_data).execute()
                    network_id = result.data[0]["id"]
                    print(f"    Inserted: {network_key} (id={network_id})")
                    network_map[network_key] = {"id": network_id, "schema": schema, "standalone": standalone}
                except Exception as e:
                    print(f"    ERROR: {network_key} - {e}")

    print(f"\n  Total networks migrated: {len(network_map)}")
    return network_map


def migrate_asset_types(
    client: Client,
    networks_df: pd.DataFrame,
    network_map: dict[str, dict],
    dry_run: bool = False,
) -> dict[str, list[dict]]:
    """
    Migrate asset types for traditional networks.

    Returns: {network_key: [{"type_key": str, "id": int}, ...]}
    """
    print("\n" + "=" * 60)
    print("STEP 2: MIGRATE ASSET TYPES (Traditional Networks)")
    print("=" * 60)

    asset_type_map = {}
    total_types = 0

    for _, row in networks_df.iterrows():
        network_key = row["network_key"]
        asset_types_str = row.get("asset_types")

        # Skip if no asset types
        if pd.isna(asset_types_str) or not asset_types_str:
            continue

        network_info = network_map.get(network_key)
        if not network_info:
            print(f"  WARNING: Network not found: {network_key}")
            continue

        schema = network_info["schema"]
        network_id = network_info["id"]
        asset_types = parse_asset_types(asset_types_str)

        if not asset_types:
            continue

        print(f"\n  {network_key}: {len(asset_types)} asset types")
        asset_type_map[network_key] = []

        for at in asset_types:
            type_data = {
                "type_key": at["type_key"],
                "name": at["name"],
                "network_id": network_id,
                "display_type": safe_str(row.get("type")) or "digital",
                "is_active": True,
                "created_by": "excel_migration",
            }

            if dry_run:
                print(f"    [DRY RUN] {at['type_key']}")
                asset_type_map[network_key].append({"type_key": at["type_key"], "id": None})
                total_types += 1
            else:
                try:
                    result = client.schema(schema).table("asset_types").insert(type_data).execute()
                    type_id = result.data[0]["id"]
                    print(f"    Inserted: {at['type_key']} (id={type_id})")
                    asset_type_map[network_key].append({"type_key": at["type_key"], "id": type_id})
                    total_types += 1
                except Exception as e:
                    print(f"    ERROR: {at['type_key']} - {e}")

    print(f"\n  Total asset types migrated: {total_types}")
    return asset_type_map


def migrate_helix_package(
    client: Client,
    network_map: dict[str, dict],
    dry_run: bool = False,
) -> dict[str, dict]:
    """
    Migrate The Helix package with its 4 DNA standalone networks.

    Returns updated network_map with the new DNA networks.
    """
    print("\n" + "=" * 60)
    print("STEP 2b: MIGRATE HELIX PACKAGE (Dubai)")
    print("=" * 60)

    schema = "backlite_dubai"
    helix = HELIX_PACKAGE

    print(f"\n  Creating {helix['package_key']} package with {len(helix['networks'])} networks")

    # First, create the DNA networks as standalone
    for net in helix["networks"]:
        network_data = {
            "network_key": net["network_key"],
            "name": net["name"],
            "standalone": True,
            "display_type": "digital",
            "city": helix["city"],
            "country": DEFAULT_COUNTRY,
            "upload_fee": net["upload_fee"],
            "is_active": True,
            "created_by": "excel_migration",
        }

        if dry_run:
            print(f"    [DRY RUN] Would create network: {net['network_key']}")
            network_map[net["network_key"]] = {"id": None, "schema": schema, "standalone": True}
        else:
            try:
                result = client.schema(schema).table("networks").insert(network_data).execute()
                network_id = result.data[0]["id"]
                print(f"    Created network: {net['network_key']} (id={network_id})")
                network_map[net["network_key"]] = {"id": network_id, "schema": schema, "standalone": True}
            except Exception as e:
                print(f"    ERROR creating network {net['network_key']}: {e}")

    # Now create The Helix package
    if dry_run:
        print(f"    [DRY RUN] Would create package: {helix['package_key']} with upload_fee={helix['upload_fee']}")
    else:
        try:
            package_result = client.schema(schema).table("packages").insert({
                "package_key": helix["package_key"],
                "name": helix["name"],
                "upload_fee": helix["upload_fee"],
                "is_active": True,
                "created_by": "excel_migration",
            }).execute()

            package_id = package_result.data[0]["id"]
            print(f"    Created package: {helix['package_key']} (id={package_id}, upload_fee={helix['upload_fee']})")

            # Add DNA networks to the package
            for net in helix["networks"]:
                network_info = network_map.get(net["network_key"])
                if network_info and network_info.get("id"):
                    client.schema(schema).table("package_items").insert({
                        "package_id": package_id,
                        "item_type": "network",
                        "network_id": network_info["id"],
                    }).execute()
                    print(f"      Added to package: {net['network_key']}")
        except Exception as e:
            print(f"    ERROR creating package: {e}")

    return network_map


def migrate_packages(
    client: Client,
    packages_df: pd.DataFrame,
    network_map: dict[str, dict],
    dry_run: bool = False,
) -> int:
    """Migrate packages and package items from Excel."""
    print("\n" + "=" * 60)
    print("STEP 4: MIGRATE PACKAGES (from Excel)")
    print("=" * 60)

    if packages_df.empty:
        print("  No packages to migrate from Excel")
        return 0

    total_packages = 0

    for _, row in packages_df.iterrows():
        package_key = row.get("package_key")
        network_keys_str = row.get("network_keys_combined")

        if pd.isna(package_key) or pd.isna(network_keys_str):
            continue

        # Parse network keys
        network_keys = [k.strip() for k in str(network_keys_str).split(",") if k.strip()]

        if not network_keys:
            continue

        # Determine schema from first network
        first_network = network_map.get(network_keys[0])
        if not first_network:
            print(f"  WARNING: No networks found for package: {package_key}")
            continue

        schema = first_network["schema"]

        # Format package name
        package_name = package_key.replace("_", " ").title()

        # Get upload_fee from row if available, else default to 3000
        upload_fee = safe_float(row.get("upload_fee")) or DEFAULT_UPLOAD_FEE

        print(f"\n  {package_key} ({len(network_keys)} networks, upload_fee={upload_fee}) -> {schema}")

        if dry_run:
            print(f"    [DRY RUN] Would create package with networks: {network_keys}")
            total_packages += 1
            continue

        try:
            # Insert package with upload_fee
            package_result = client.schema(schema).table("packages").insert({
                "package_key": package_key,
                "name": package_name,
                "upload_fee": upload_fee,
                "is_active": True,
                "created_by": "excel_migration",
            }).execute()

            package_id = package_result.data[0]["id"]
            print(f"    Created package: {package_key} (id={package_id})")

            # Insert package items
            for nk in network_keys:
                network_info = network_map.get(nk)
                if not network_info or not network_info.get("id"):
                    print(f"      WARNING: Network not found: {nk}")
                    continue

                client.schema(schema).table("package_items").insert({
                    "package_id": package_id,
                    "item_type": "network",
                    "network_id": network_info["id"],
                }).execute()
                print(f"      Added: {nk}")

            total_packages += 1

        except Exception as e:
            print(f"    ERROR: {package_key} - {e}")

    print(f"\n  Total packages migrated: {total_packages}")
    return total_packages


# =============================================================================
# STORAGE MIGRATION
# =============================================================================

# Storage path renames: old_path -> new_path
# Format: (old_company, old_network_key) -> (new_company, new_network_key)
STORAGE_RENAMES = {
    # Dubai renames (same company, different network_key)
    ("backlite_dubai", "the_oryx"): ("backlite_dubai", "oryx"),  # Remove "the_" prefix
    ("backlite_dubai", "triple_crown"): ("backlite_dubai", "triple_crown_dubai"),
    ("backlite_dubai", "bl108"): ("backlite_dubai", "dna02"),  # bl108 -> dna02
    # Abu Dhabi moves (different company + rename)
    ("backlite_dubai", "al_qana"): ("backlite_abudhabi", "alqana"),
    ("backlite_dubai", "the_triple_crown_abu_dhabi"): ("backlite_abudhabi", "triple_crown_abu_dhabi"),
}

# Paths to delete (deprecated networks/packages)
STORAGE_DELETES = [
    # Deprecated networks
    ("backlite_dubai", "bl308"),  # No longer exists (was dna04, but no mockups)
    ("backlite_dubai", "digital_icons"),  # No longer exists
    # Packages stored as networks (not needed)
    ("backlite_dubai", "the_galleria_full_dominance"),
    ("backlite_dubai", "the_galleria_indoor_dominance"),
    ("backlite_dubai", "the_galleria_outdoor_screens_dominance"),
]


def list_storage_files(client: Client, bucket: str, path: str) -> list[dict]:
    """List all files in a storage bucket path recursively."""
    all_files = []

    try:
        # List items at this path
        items = client.storage.from_(bucket).list(path)

        for item in items:
            item_path = f"{path}/{item['name']}" if path else item['name']

            if item.get("id") is None:
                # It's a folder, recurse
                sub_files = list_storage_files(client, bucket, item_path)
                all_files.extend(sub_files)
            else:
                # It's a file
                all_files.append({"path": item_path, "metadata": item})
    except Exception as e:
        # Path doesn't exist or error
        pass

    return all_files


def migrate_storage_paths(
    client: Client,
    buckets: list[str],
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Migrate storage paths based on STORAGE_RENAMES mapping.

    For each bucket (mockups, templates):
    1. List files under old paths
    2. Move/copy to new paths
    3. Optionally delete old paths

    Returns: {"moved": count, "deleted": count, "errors": count}
    """
    print("\n" + "=" * 60)
    print("STEP 5: MIGRATE STORAGE PATHS")
    print("=" * 60)

    stats = {"moved": 0, "deleted": 0, "errors": 0, "skipped": 0}

    for bucket in buckets:
        print(f"\n  Bucket: {bucket}")

        # Process renames
        for (old_company, old_key), (new_company, new_key) in STORAGE_RENAMES.items():
            old_path = f"{old_company}/{old_key}"
            new_path = f"{new_company}/{new_key}"

            print(f"\n    Checking: {old_path}")

            # List files at old path
            files = list_storage_files(client, bucket, old_path)

            if not files:
                print(f"      No files found at {old_path}")
                stats["skipped"] += 1
                continue

            print(f"      Found {len(files)} files to move")

            for file_info in files:
                old_file_path = file_info["path"]
                # Replace old path prefix with new path prefix
                new_file_path = old_file_path.replace(old_path, new_path, 1)

                if dry_run:
                    print(f"      [DRY RUN] Would move: {old_file_path} -> {new_file_path}")
                    stats["moved"] += 1
                else:
                    try:
                        # Supabase storage move (works within same bucket)
                        client.storage.from_(bucket).move(old_file_path, new_file_path)
                        print(f"      Moved: {old_file_path} -> {new_file_path}")
                        stats["moved"] += 1
                    except Exception as e:
                        print(f"      ERROR moving {old_file_path}: {e}")
                        stats["errors"] += 1

        # Process deletes
        for (company, key) in STORAGE_DELETES:
            delete_path = f"{company}/{key}"

            print(f"\n    Checking for deletion: {delete_path}")

            files = list_storage_files(client, bucket, delete_path)

            if not files:
                print(f"      No files found at {delete_path}")
                continue

            print(f"      Found {len(files)} files to delete")

            for file_info in files:
                file_path = file_info["path"]

                if dry_run:
                    print(f"      [DRY RUN] Would delete: {file_path}")
                    stats["deleted"] += 1
                else:
                    try:
                        client.storage.from_(bucket).remove([file_path])
                        print(f"      Deleted: {file_path}")
                        stats["deleted"] += 1
                    except Exception as e:
                        print(f"      ERROR deleting {file_path}: {e}")
                        stats["errors"] += 1

    print(f"\n  Storage migration complete:")
    print(f"    Moved: {stats['moved']}")
    print(f"    Deleted: {stats['deleted']}")
    print(f"    Skipped: {stats['skipped']}")
    print(f"    Errors: {stats['errors']}")

    return stats


def update_mockup_frames_location_keys(
    client: Client,
    dry_run: bool = False,
) -> int:
    """
    Update mockup_frames location_keys to match new network_keys.
    """
    print("\n" + "=" * 60)
    print("STEP 6: UPDATE MOCKUP_FRAMES LOCATION_KEYS")
    print("=" * 60)

    updates = [
        ("backlite_dubai", "the_oryx", "oryx"),  # Remove "the_" prefix
        ("backlite_dubai", "triple_crown", "triple_crown_dubai"),
        ("backlite_dubai", "bl108", "dna02"),  # bl108 -> dna02
    ]

    total_updated = 0

    for schema, old_key, new_key in updates:
        if dry_run:
            # Count how many would be updated
            result = client.schema(schema).table("mockup_frames").select("id").eq("location_key", old_key).execute()
            count = len(result.data)
            print(f"  [DRY RUN] Would update {count} rows: {old_key} -> {new_key} in {schema}")
            total_updated += count
        else:
            try:
                result = client.schema(schema).table("mockup_frames").update(
                    {"location_key": new_key}
                ).eq("location_key", old_key).execute()
                count = len(result.data)
                print(f"  Updated {count} rows: {old_key} -> {new_key} in {schema}")
                total_updated += count
            except Exception as e:
                print(f"  ERROR updating {old_key} in {schema}: {e}")

    print(f"\n  Total mockup_frames updated: {total_updated}")
    return total_updated


# =============================================================================
# MAIN
# =============================================================================

def run_migration(args: argparse.Namespace) -> None:
    """Run the full migration."""
    print("\n" + "=" * 60)
    print("ASSET MANAGEMENT - NETWORK DATA MIGRATION")
    print("=" * 60)
    print(f"Source: {EXCEL_FILE}")
    print(f"Target: {'PROD' if args.prod else 'DEV'} Supabase")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Clear existing: {args.clear}")
    print(f"Fetch fees from DB: {args.fetch_fees}")
    print(f"Migrate storage: {args.migrate_storage}")
    print("=" * 60)

    if not EXCEL_FILE.exists():
        print(f"\nERROR: Excel file not found: {EXCEL_FILE}")
        sys.exit(1)

    # Load data
    networks_df, packages_df = load_excel_data(EXCEL_FILE)

    # Connect to Supabase
    client = get_supabase(prod=args.prod)

    # Optionally fetch existing upload fees from database
    existing_fees = {}
    if args.fetch_fees:
        existing_fees = fetch_existing_upload_fees(client)
        print(f"  Fetched {len(existing_fees)} upload fees from existing database")

    # Clear existing data if requested
    if args.clear:
        schemas_to_clear = set()
        for _, row in networks_df.iterrows():
            schema = get_schema_for_city(row.get("city"))
            schemas_to_clear.add(schema)

        for schema in schemas_to_clear:
            clear_existing_data(client, schema, dry_run=args.dry_run)

    # Step 1: Migrate networks from Excel (pass existing fees)
    network_map = migrate_networks(client, networks_df, existing_fees=existing_fees, dry_run=args.dry_run)

    # Step 2b: Migrate The Helix package with DNA networks (Dubai only)
    network_map = migrate_helix_package(client, network_map, dry_run=args.dry_run)

    # Step 3: Migrate asset types for traditional networks (Galleria)
    migrate_asset_types(client, networks_df, network_map, dry_run=args.dry_run)

    # Step 4: Migrate packages from Excel (with upload_fee)
    migrate_packages(client, packages_df, network_map, dry_run=args.dry_run)

    # Step 5: Migrate storage paths (if requested)
    if args.migrate_storage:
        migrate_storage_paths(client, ["mockups", "templates"], dry_run=args.dry_run)

        # Step 6: Update mockup_frames location_keys
        update_mockup_frames_location_keys(client, dry_run=args.dry_run)

    # Summary
    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)

    dubai_count = sum(1 for n in network_map.values() if n["schema"] == "backlite_dubai")
    abudhabi_count = sum(1 for n in network_map.values() if n["schema"] == "backlite_abudhabi")

    print(f"  backlite_dubai: {dubai_count} networks")
    print(f"  backlite_abudhabi: {abudhabi_count} networks")
    print("=" * 60)

    if args.dry_run:
        print("\n⚠️  DRY RUN - No changes were made")
    else:
        print("\n✅ Migration complete!")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate network data from Excel to Supabase"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without making changes",
    )
    parser.add_argument(
        "--prod",
        action="store_true",
        help="Run against PROD (default: DEV)",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing data before migration (REPLACE ALL)",
    )
    parser.add_argument(
        "--fetch-fees",
        action="store_true",
        help="Fetch existing upload_fee values from DB before migration",
    )
    parser.add_argument(
        "--migrate-storage",
        action="store_true",
        help="Migrate storage paths (rename oryx->the_oryx, etc.) and update mockup_frames",
    )

    args = parser.parse_args()

    try:
        run_migration(args)
    except KeyboardInterrupt:
        print("\n\nMigration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
