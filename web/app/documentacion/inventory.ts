import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { resolveDeployment, type Deployment } from "./azure";

// Read at build time by the server component; `next build` runs from web/.
export const INVENTORY_PATH = join(process.cwd(), "app/documentacion/inventory.generated.json");

export function loadDeployment(): Deployment {
  if (!existsSync(INVENTORY_PATH)) {
    throw new Error("falta inventory.generated.json: correr scripts/web_inventory.sh <grupo-de-recursos>");
  }
  return resolveDeployment(JSON.parse(readFileSync(INVENTORY_PATH, "utf8")));
}
