"use client";

import { useState } from "react";
import { ApiError, decideEscalation } from "@/lib/api";
import type { EscalationDraft } from "@/lib/types";
import { CitationChip } from "./CitationChip";
import { FlagIcon } from "./icons";

interface Props {
  draft: EscalationDraft;
  token: string | null;
  onUnauthorized: () => void;
}

export function EscalationCard({ draft, token, onUnauthorized }: Props) {
  const [outcome, setOutcome] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function decide(approve: boolean) {
    setBusy(true);
    setError(null);
    try {
      const result = await decideEscalation(draft.id, { approve }, token);
      setOutcome("ticket_id" in result ? `Ticket ${result.ticket_id} creado` : "Escalamiento descartado");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      setError(`No se pudo registrar la decisión (${(err as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-contradiction/30 bg-contradiction/[0.05] p-4">
      <h3 className="flex items-center gap-2 font-display text-sm font-bold text-contradiction">
        <FlagIcon className="size-4" />
        Borrador de escalamiento
      </h3>
      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-xs font-semibold text-muted">Área</dt>
          <dd className="font-semibold text-ink">{draft.area}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold text-muted">Resumen</dt>
          <dd className="text-ink">{draft.summary}</dd>
        </div>
      </dl>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {draft.evidence.map((citation) => (
          <CitationChip key={citation.id} citation={citation} />
        ))}
      </div>

      {outcome ? (
        <p role="status" className="mt-4 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-navy ring-1 ring-line">
          {outcome}
        </p>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(true)}
            className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:opacity-60"
          >
            Crear ticket
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => decide(false)}
            className="rounded-full px-4 py-2 text-sm font-semibold text-brand ring-1 ring-brand/40 transition-colors hover:bg-sky disabled:opacity-60"
          >
            Descartar
          </button>
          <span className="text-xs text-muted">Nada se envía sin tu aprobación.</span>
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-reject">
          {error}
        </p>
      )}
    </section>
  );
}
