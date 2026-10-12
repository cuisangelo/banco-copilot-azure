// Two leaks this build must not ship, both checked against the real inventory so the check itself never
// contains what it looks for:
// 1. Static Web Apps only guards /privado/*; every other file in out/ is public, /documentacion included.
// 2. The repo is public; no tracked file may identify the deployment.
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";

const WEB = new URL("..", import.meta.url).pathname;
const OUT = join(WEB, "out");
const INVENTORY = join(WEB, "public/privado/inventario.json");

if (!existsSync(INVENTORY)) throw new Error("falta public/privado/inventario.json: correr scripts/web_inventory.sh <grupo-de-recursos>");
const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL;
if (!apiBase) throw new Error("NEXT_PUBLIC_API_BASE_URL is required");

const inventory = JSON.parse(readFileSync(INVENTORY, "utf8"));
const accountIds = [inventory.subscriptionId, inventory.tenantDomain];
const names = inventory.resources.map((r) => r.name);

// The copilot-api hostname embeds its resource name and is public by design: every page calls it.
const publicLeaks = [...accountIds, ...names.filter((name) => !apiBase.includes(name))];
const leaks = [];
for (const entry of readdirSync(OUT, { recursive: true, withFileTypes: true })) {
  if (!entry.isFile()) continue;
  const path = relative(OUT, join(entry.parentPath, entry.name));
  if (path.startsWith("privado/")) continue;
  const content = readFileSync(join(OUT, path), "latin1");
  for (const value of publicLeaks) if (content.includes(value)) leaks.push(`out/${path}`);
}

// Names Terraform derives from the public prefix alone (`<prefix>-<service>`, e.g. in test hostnames) say
// nothing about this deployment; the ones carrying its random suffix do.
const prefix = inventory.resourceGroup.replace(/-rg$/, "");
const repoLeaks = [...accountIds, ...inventory.resources.filter((r) => r.name !== `${prefix}-${r.key}`).map((r) => r.name)];
try {
  const files = execFileSync("git", ["grep", "--untracked", "-lF", ...repoLeaks.flatMap((v) => ["-e", v])], {
    cwd: join(WEB, ".."),
    encoding: "utf8",
  });
  leaks.push(...files.trim().split("\n"));
} catch (error) {
  // git grep exits 1 when nothing matches; anything else is a real failure.
  if (error.status !== 1) throw error;
}

if (leaks.length) {
  console.error(`Deployment identifiers found where they must not be:\n${[...new Set(leaks)].join("\n")}`);
  process.exit(1);
}
console.log(
  `check-public-bundle: ${publicLeaks.length} identifiers absent from public files in out/, ${repoLeaks.length} absent from the repo`,
);
