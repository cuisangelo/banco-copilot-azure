#!/bin/sh
# Keeps one replica of every service running for a live demo, then lets them scale back to zero.
#
#   scripts/demo.sh up   <resource-group>   # before showing it: no ~25 s cold starts
#   scripts/demo.sh down <resource-group>   # afterwards: back to zero, no idle cost
#
# Terraform declares min_replicas = 0, so a later `terraform apply` also returns everything to zero.
set -eu

action="${1:?usage: scripts/demo.sh up|down <resource-group>}"
rg="${2:?usage: scripts/demo.sh up|down <resource-group>}"

case "$action" in
  up) replicas=1 ;;
  down) replicas=0 ;;
  *) echo "usage: scripts/demo.sh up|down <resource-group>" >&2; exit 2 ;;
esac

for svc in copilot-api mcp-bank products-api customers-api; do
  az containerapp update --resource-group "$rg" --name "bcopilot-$svc" --min-replicas "$replicas" --output none
  echo "bcopilot-$svc: min replicas $replicas"
done
