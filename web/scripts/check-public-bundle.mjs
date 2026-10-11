// Static Web Apps only guards /documentacion*. Every other file in out/ is public, so none may carry the
// deployed inventory: that happens as soon as a client component imports it.
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { RESOURCES, SUBSCRIPTION_ID } from "../app/documentacion/azure.ts";

const OUT = new URL("../out/", import.meta.url).pathname;
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
if (!apiBase) throw new Error("NEXT_PUBLIC_API_BASE_URL is required");

// The copilot-api hostname embeds its resource name and is public by design: every page calls it.
const secrets = [SUBSCRIPTION_ID, ...RESOURCES.map((r) => r.name).filter((name) => !apiBase.includes(name))];

const leaks = [];
for (const entry of readdirSync(OUT, { recursive: true, withFileTypes: true })) {
  if (!entry.isFile()) continue;
  const path = relative(OUT, join(entry.parentPath, entry.name));
  if (path.startsWith("documentacion")) continue;
  const content = readFileSync(join(OUT, path), "latin1");
  for (const secret of secrets) if (content.includes(secret)) leaks.push(`${path}: ${secret}`);
}

if (leaks.length) {
  console.error(`Deployed inventory leaked outside /documentacion:\n${leaks.join("\n")}`);
  process.exit(1);
}
console.log(`check-public-bundle: ${secrets.length} names absent from public files in out/`);
