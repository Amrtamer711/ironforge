#!/bin/bash
# =============================================================================
# Supabase Sync Wrapper Script
# =============================================================================
# Quick wrapper for the TypeScript sync script
#
# Usage:
#   ./scripts/sync-supabase.sh dev-to-prod --all
#   ./scripts/sync-supabase.sh prod-to-dev --db
#   ./scripts/sync-supabase.sh dev-to-prod --storage --project salesbot
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check if ts-node is available
if ! command -v npx &> /dev/null; then
    echo "Error: npx not found. Install Node.js first."
    exit 1
fi

# Run the TypeScript script
npx ts-node scripts/sync-supabase.ts --direction "$@"
