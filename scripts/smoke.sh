#!/bin/sh
# Post-deploy smoke test against the public copilot-api.
# Usage: scripts/smoke.sh https://<copilot-api-fqdn>
set -eu

base="${1:?usage: scripts/smoke.sh <copilot-api base url>}"

# Prints the JSON of the final `answer` event of an SSE stream read from stdin; fails on `error`.
final_answer() {
  python3 -I -c '
import json, sys
event = None
answer = None
for line in sys.stdin:
    line = line.rstrip("\n")
    if line.startswith("event:"):
        event = line[6:].strip()
    elif line.startswith("data:") and event in ("answer", "error"):
        if event == "error":
            sys.exit("error event: " + line[5:].strip())
        answer = line[5:].strip()
if answer is None:
    sys.exit("stream ended without an answer event")
print(answer)
'
}

echo "1/2 procedure question returns ok with citations"
answer=$(curl -sS -N --fail-with-body -X POST "$base/chat" \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"smoke-1","message":"¿Qué pasos sigo para bloquear una tarjeta extraviada?"}' | final_answer)
printf '%s' "$answer" | python3 -I -c '
import json, sys
a = json.load(sys.stdin)
s = a["status"]; assert s == "ok", f"status={s}"
assert len(a["citations"]) >= 1, "no citations"
n = len(a["citations"]); print(f"   ok: {n} citations")
'

echo "2/2 level-2 field without a grant is never disclosed"
token=$(curl -sS --fail-with-body -X POST "$base/demo/session" \
  -H 'Content-Type: application/json' -d '{"persona":"ana"}' |
  python3 -I -c 'import json, sys; print(json.load(sys.stdin)["token"])')
answer=$(curl -sS -N --fail-with-body -X POST "$base/chat" \
  -H 'Content-Type: application/json' -H "Authorization: Bearer $token" \
  -d '{"session_id":"smoke-2","customer_id":"C-1007","message":"¿Cuál es la renta mensual de este cliente?"}' | final_answer)
printf '%s' "$answer" | python3 -I -c '
import json, sys
a = json.load(sys.stdin)
s = a["status"]; assert s == "access_required", f"status={s}"
assert "monthly_income" in a["access_request"]["fields"], "request does not ask for monthly_income"
print("   ok: access_required for monthly_income")
'

echo "smoke passed"
