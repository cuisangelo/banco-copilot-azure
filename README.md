# Banco Copilot Azure

Copiloto cognitivo para asesores de un banco ficticio ("Banco Austral"), construido sobre Azure:
Microsoft Foundry, Agent Framework, MCP, Azure AI Search, Content Safety y acceso a datos de cliente
por niveles con aprobación de Supervisor.

- Diseño: [`docs/superpowers/specs/2026-10-11-banco-copilot-design.md`](docs/superpowers/specs/2026-10-11-banco-copilot-design.md)
- Plan: [`docs/superpowers/plans/2026-10-11-banco-copilot.md`](docs/superpowers/plans/2026-10-11-banco-copilot.md)

## Tests (sin Azure)

```sh
uv run --all-packages pytest      # backend, evaluaciones, función de ingesta y contratos
pnpm -C web test                  # web
terraform -chdir=infra test       # invariantes de infraestructura, con providers simulados
```

## Correr en local

`copilot-api`, `mcp-bank` y la web corren en tu máquina; el modelo, AI Search, Content Safety, Cosmos y
los backends detrás de APIM son los desplegados, y todo se autentica con tu `az login`.

Requisitos: `uv`, `pnpm`, `az login` en la suscripción y un `terraform apply` hecho con tu usuario
(te da los roles de datos que usa la corrida local).

```sh
uv run python scripts/local_env.py bcopilot-rg   # escribe .env.local y web/.env.local desde lo desplegado
scripts/web_inventory.sh bcopilot-rg             # inventario de /documentacion
scripts/local.sh                                 # mcp-bank :8001, copilot-api :8000, web http://localhost:3000
```

- `.env.local` trae la clave de suscripción de APIM y la clave que firma los tokens de las personas: está
  en `.gitignore` y no se comparte.
- La API local usa la **misma base de Cosmos** que producción (una segunda base saldría del free tier):
  comparte sesiones, auditoría y el tope diario de tokens.
- Si cambia la configuración desplegada (por ejemplo, al encender o apagar el modo agéntico), vuelve a
  correr `local_env.py`.
