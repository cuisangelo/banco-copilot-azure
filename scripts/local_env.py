"""Writes .env.local and web/.env.local so scripts/local.sh runs copilot-api, mcp-bank and the web here.

Run with `uv run python scripts/local_env.py <resource-group>` after `az login` and `terraform apply`. The
settings are read from the deployed container apps and their secrets from Key Vault, so a local run uses
exactly what production uses; only the addresses between the local processes change. Both files are
gitignored: they hold the APIM subscription key and the persona signing key.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = {
    "MCP_BANK_URL": "http://localhost:8001/mcp",
    "MCP_ALLOWED_HOSTS": "localhost:8001",
    "CORS_ORIGIN": "http://localhost:3000",
}


def az(*args: str) -> str:
    return subprocess.run(["az", *args, "--output", "json"], check=True, capture_output=True, text=True).stdout


def deployed_env(resource_group: str, app: str, vault: str) -> dict[str, str]:
    container = json.loads(az("containerapp", "show", "-g", resource_group, "-n", f"bcopilot-{app}"))
    env = {}
    for entry in container["properties"]["template"]["containers"][0]["env"]:
        # The managed identity's client id would make DefaultAzureCredential skip the developer's az login.
        if entry["name"] == "AZURE_CLIENT_ID":
            continue
        if entry.get("secretRef"):
            env[entry["name"]] = json.loads(az("keyvault", "secret", "show", "--vault-name", vault, "-n", entry["secretRef"]))["value"]
        else:
            env[entry["name"]] = entry["value"]
    return env


def dotenv(values: dict[str, str]) -> str:
    quoted = (value.replace("\\", "\\\\").replace('"', '\\"') for value in values.values())
    return "".join(f'{name}="{value}"\n' for name, value in zip(values, quoted, strict=True))


def main() -> None:
    (resource_group,) = sys.argv[1:]
    (vault,) = json.loads(az("keyvault", "list", "-g", resource_group, "--query", "[].name"))
    env = deployed_env(resource_group, "mcp-bank", vault) | deployed_env(resource_group, "copilot-api", vault) | LOCAL
    (ROOT / ".env.local").write_text(dotenv(dict(sorted(env.items()))))
    # uvicorn listens on IPv4 only: "localhost" may resolve to ::1, where another local service can own :8000.
    (ROOT / "web" / ".env.local").write_text(dotenv({"NEXT_PUBLIC_API_BASE_URL": "http://127.0.0.1:8000"}))
    print(f"wrote .env.local ({len(env)} settings) and web/.env.local")


if __name__ == "__main__":
    main()
