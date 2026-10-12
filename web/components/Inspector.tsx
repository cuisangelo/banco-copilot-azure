import { formatInt, formatUsd } from "@/lib/format";
import { nodeLabel } from "@/lib/labels";
import type { TraceEvent } from "@/lib/types";
import { CloseIcon } from "./icons";

export interface InspectedTurn {
  id: string;
  title: string;
  traces: TraceEvent[];
}

function Totals({ traces }: { traces: TraceEvent[] }) {
  const sum = (pick: (t: TraceEvent) => number) => traces.reduce((acc, t) => acc + pick(t), 0);
  return (
    <dl aria-label="Totales del turno" className="mt-3 grid grid-cols-3 gap-2 rounded-xl bg-white p-3 text-center ring-1 ring-line">
      <div>
        <dt className="text-xs text-muted">Duración</dt>
        <dd className="font-display text-sm font-bold text-navy tabular-nums">{formatInt(sum((t) => t.duration_ms))} ms</dd>
      </div>
      <div>
        <dt className="text-xs text-muted">Consumo</dt>
        <dd className="font-display text-sm font-bold text-navy tabular-nums">
          {formatInt(sum((t) => t.tokens_in + t.tokens_out))} tokens
        </dd>
      </div>
      <div>
        <dt className="text-xs text-muted">Costo</dt>
        <dd className="font-display text-sm font-bold text-navy tabular-nums">{formatUsd(sum((t) => t.cost_usd))}</dd>
      </div>
    </dl>
  );
}

function TraceRow({ trace }: { trace: TraceEvent }) {
  const hasData = Object.keys(trace.data).length > 0;
  return (
    <li className="relative pb-4 pl-6 last:pb-0">
      <span className="absolute top-1.5 left-0 size-2.5 rounded-full border-2 border-brand bg-white" aria-hidden />
      <div className="flex items-baseline justify-between gap-3">
        <p className="leading-tight">
          <span className="font-semibold text-ink">{nodeLabel(trace.node)}</span>{" "}
          <span className="text-xs text-muted">{trace.node}</span>
        </p>
        <span className="shrink-0 text-xs text-muted tabular-nums">{formatInt(trace.duration_ms)} ms</span>
      </div>
      {(trace.tokens_in > 0 || trace.tokens_out > 0) && (
        <p className="mt-0.5 flex flex-wrap gap-x-3 text-xs text-muted tabular-nums">
          <span>{formatInt(trace.tokens_in)} entrada</span>
          <span>{formatInt(trace.tokens_out)} salida</span>
          <span>{formatUsd(trace.cost_usd)}</span>
        </p>
      )}
      {Array.isArray(trace.data.subqueries) && (
        <div className="mt-1 text-xs text-ink">
          <p className="font-semibold">Búsqueda agéntica · {trace.data.subqueries.length} subconsultas</p>
          <ul className="mt-0.5 list-disc pl-4">
            {(trace.data.subqueries as string[]).map((query) => (
              <li key={query}>{query}</li>
            ))}
          </ul>
        </div>
      )}
      {hasData && (
        <details className="mt-1 text-xs">
          <summary className="cursor-pointer text-brand">Detalle</summary>
          <pre className="mt-1 overflow-x-auto rounded-lg bg-white p-2 text-[11px] leading-relaxed text-ink ring-1 ring-line">
            {JSON.stringify(trace.data, null, 2)}
          </pre>
        </details>
      )}
    </li>
  );
}

export function Inspector({ turns, onClose }: { turns: InspectedTurn[]; onClose?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <h2 className="font-display text-base font-bold text-navy">Inspector</h2>
          <p className="text-xs text-muted">Qué hizo el copiloto en cada consulta</p>
        </div>
        {onClose && (
          <button type="button" onClick={onClose} aria-label="Cerrar inspector" className="rounded-full p-2 text-muted hover:bg-sky">
            <CloseIcon className="size-5" />
          </button>
        )}
      </header>
      {turns.length === 0 ? (
        <p className="p-5 text-sm text-muted">Haz una consulta y aquí verás cada paso: búsqueda, herramientas, guardrails, tokens y costo.</p>
      ) : (
        <ol aria-label="Turnos" className="flex-1 space-y-6 overflow-y-auto p-5">
          {[...turns].reverse().map((turn) => (
            <li key={turn.id}>
              <h3 className="mb-3 line-clamp-2 text-sm font-semibold text-navy">{turn.title}</h3>
              <ol className="border-l border-line pl-0 [&>li]:-ml-[5px]">
                {turn.traces.map((trace, index) => (
                  <TraceRow key={index} trace={trace} />
                ))}
              </ol>
              <Totals traces={turn.traces} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
