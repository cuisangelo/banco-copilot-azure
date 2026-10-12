import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { resolveDeployment, toLayout, type Layout } from "./azure";

// `next build` runs from web/; scripts/web_inventory.sh writes the file and Static Web Apps serves it to owners only.
const INVENTORY_PATH = join(process.cwd(), "public/privado/inventario.json");

/** The public half of the inventory, read at build time: everything but names and ids. */
export function loadLayout(): Layout {
  if (!existsSync(INVENTORY_PATH)) {
    throw new Error("falta public/privado/inventario.json: correr scripts/web_inventory.sh <grupo-de-recursos>");
  }
  return toLayout(resolveDeployment(JSON.parse(readFileSync(INVENTORY_PATH, "utf8"))));
}
