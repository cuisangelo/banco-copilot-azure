#!/usr/bin/env bash
# Runs mcp-bank (:8001), copilot-api (:8000) and the web (:3000) on this machine against the deployed
# Azure resources, authenticated with your az login. Ctrl+C stops all three.
# Usage: scripts/local.sh   (after `uv run python scripts/local_env.py <resource-group>`)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
env_file="$root/.env.local"
if [[ ! -f "$env_file" ]]; then
  echo "missing .env.local: run uv run python scripts/local_env.py <resource-group>" >&2
  exit 1
fi

trap 'kill 0' EXIT
cd "$root"
uv run --env-file "$env_file" --all-packages uvicorn mcp_bank.server:app_from_env --factory --port 8001 &
uv run --env-file "$env_file" --all-packages uvicorn copilot_api.main:build_app --factory --port 8000 &
pnpm -C web dev
