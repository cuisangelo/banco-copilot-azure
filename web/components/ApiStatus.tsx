"use client";

import { useEffect, useState } from "react";
import { formatInt } from "@/lib/format";

// Guaranteed at build time by next.config.ts.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;
const COLD_START_AFTER_MS = 5000;

type Probe =
  | { state: "checking" }
  | { state: "cold" }
  | { state: "online"; ms: number }
  | { state: "down"; reason: string };

const TONE: Record<Probe["state"], string> = {
  checking: "bg-muted",
  cold: "bg-contradiction",
  online: "bg-ok",
  down: "bg-reject",
};

function label(probe: Probe): string {
  switch (probe.state) {
    case "checking":
      return "Comprobando la API…";
    case "cold":
      return "API iniciando (escala a cero)";
    case "online":
      return `API en línea · ${formatInt(probe.ms)} ms`;
    case "down":
      return `API no disponible (${probe.reason})`;
  }
}

export function ApiStatus() {
  const [probe, setProbe] = useState<Probe>({ state: "checking" });

  useEffect(() => {
    const controller = new AbortController();
    const started = performance.now();
    const coldTimer = setTimeout(() => setProbe({ state: "cold" }), COLD_START_AFTER_MS);
    fetch(`${API_BASE}/.well-known/jwks.json`, { signal: controller.signal, cache: "no-store" })
      .then((response) =>
        setProbe(
          response.ok
            ? { state: "online", ms: Math.round(performance.now() - started) }
            : { state: "down", reason: `HTTP ${response.status}` },
        ),
      )
      .catch(() => {
        if (!controller.signal.aborted) setProbe({ state: "down", reason: "sin respuesta" });
      })
      .finally(() => clearTimeout(coldTimer));
    return () => {
      clearTimeout(coldTimer);
      controller.abort();
    };
  }, []);

  return (
    <p role="status" className="flex items-center gap-2.5 font-display text-lg font-bold text-navy">
      <span className={`size-3 shrink-0 rounded-full ${TONE[probe.state]}`} aria-hidden />
      {label(probe)}
    </p>
  );
}
