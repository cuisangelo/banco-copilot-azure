#!/bin/sh
# Deploys Banco Copilot end to end from a laptop: infra, images, search index, ingest function,
# web app, DNS and custom domain. Run from the repo root after `az login` and `vercel login`.
#
#   ARM_SUBSCRIPTION_ID=<subscription> TF_STATE_PATH=<durable path>/terraform.tfstate \
#   DNS_ZONE=cuisangelo.com scripts/deploy.sh
#
# The web hostname comes from web_custom_domain in infra/terraform.tfvars and must sit in DNS_ZONE,
# which is managed in Vercel. Re-running is safe: every step converges to the same state.
set -eu

: "${ARM_SUBSCRIPTION_ID:?ARM_SUBSCRIPTION_ID is required}"
: "${TF_STATE_PATH:?TF_STATE_PATH is required (keep it outside the repo: it holds secrets)}"
: "${DNS_ZONE:?DNS_ZONE is required}"
export ARM_SUBSCRIPTION_ID

tf() { terraform -chdir=infra "$@"; }
out() { tf output -raw "$1"; }
step() { printf '\n== %s\n' "$1"; }

step "1/9 infra (Event Grid trigger and custom domain come later)"
tf init -input=false -reconfigure -backend-config="path=$TF_STATE_PATH"
tf apply -input=false -auto-approve

rg=$(out resource_group_name)
acr=$(out acr_login_server)
domain=$(tf console <<'EOF' | tr -d '"'
var.web_custom_domain
EOF
)

step "2/9 container images (linux/amd64) and rollout"
az acr login --name "${acr%%.*}"
tag=$(git rev-parse --short HEAD)
for svc in products-api customers-api mcp-bank copilot-api; do
  image="$acr/$svc:$tag"
  docker buildx build --platform linux/amd64 -f "services/$svc/Dockerfile" -t "$image" --push .
  az containerapp update --resource-group "$rg" --name "bcopilot-$svc" --image "$image" --output none
done

step "3/9 search index and documents"
AZURE_OPENAI_ENDPOINT=$(out openai_endpoint) \
AZURE_OPENAI_API_VERSION=2024-10-21 \
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-3-small \
SEARCH_ENDPOINT=$(out search_endpoint) \
SEARCH_INDEX=bank-docs \
PYTHONPATH=functions/ingest \
  uv run --all-packages python scripts/ingest_local.py

step "4/9 ingest function (dependencies vendored: bank-contracts is a workspace package)"
pkg=$(mktemp -d)
cp functions/ingest/*.py functions/ingest/host.json "$pkg/"
uv export --package bank-ingest --no-hashes --no-editable --no-emit-project --frozen > "$pkg/requirements.txt"
uv pip install --target "$pkg/.python_packages/lib/site-packages" --python-version 3.12 \
  --python-platform x86_64-manylinux_2_28 -r "$pkg/requirements.txt"
(cd "$pkg" && zip -qr "$pkg.zip" .)
az functionapp deployment source config-zip --resource-group "$rg" --name "$(out ingest_function_name)" \
  --src "$pkg.zip" --build-remote false --output none

step "5/9 Event Grid trigger (needs the function code deployed)"
tf apply -input=false -auto-approve -var ingest_trigger_enabled=true

step "6/9 web app build and upload"
NEXT_PUBLIC_API_BASE_URL=$(out copilot_api_url) pnpm -C web build
pnpm dlx @azure/static-web-apps-cli@2.0.10 deploy web/out --env production \
  --deployment-token "$(out static_web_app_deployment_token)"

step "7/9 DNS: CNAME ${domain} -> Static Web App"
swa_host=$(out web_url | sed 's|https://||')
sub=${domain%."$DNS_ZONE"}
if ! vercel dns ls "$DNS_ZONE" | grep -Eq "[[:space:]]$sub[[:space:]]+CNAME[[:space:]]"; then
  vercel dns add "$DNS_ZONE" "$sub" CNAME "$swa_host"
fi
until dig +short CNAME "$domain" | grep -q "$swa_host"; do sleep 10; done

step "8/9 custom domain on the Static Web App"
tf apply -input=false -auto-approve -var ingest_trigger_enabled=true -var web_custom_domain_enabled=true

step "9/9 smoke test"
scripts/smoke.sh "$(out copilot_api_url)"
printf '\nLive at https://%s\n' "$domain"
