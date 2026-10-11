#!/usr/bin/env bash
# Writes web/app/documentacion/inventory.generated.json from the live resource group, for the /documentacion
# build. The file is gitignored: subscription, tenant and resource names never enter the public repo.
# Usage: scripts/web_inventory.sh <resource-group>   (after `az login`)
set -euo pipefail

rg="${1:?usage: scripts/web_inventory.sh <resource-group>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
out="$root/web/app/documentacion/inventory.generated.json"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

az account show --output json > "$tmp/account.json"
az resource list --resource-group "$rg" --output json > "$tmp/resources.json"
node "$root/web/scripts/inventory-from-az.mjs" "$rg" "$tmp/account.json" "$tmp/resources.json" > "$tmp/inventory.json"
mv "$tmp/inventory.json" "$out"
echo "wrote $out"
