"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, resumeSession, streamChat, type ChatEvent } from "@/lib/api";
import { nodeLabel } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { CUSTOMER_ID_PATTERN, type AccessRequest, type ChatAnswer, type TraceEvent } from "@/lib/types";
import { AccessRequestCard } from "./AccessRequestCard";
import { AnswerCard } from "./AnswerCard";
import { EscalationCard } from "./EscalationCard";
import { PanelIcon, SendIcon } from "./icons";
import { Inspector } from "./Inspector";

interface Turn {
  id: string;
  title: string;
  question: string | null;
  customerId: string | null;
  traces: TraceEvent[];
  answer: ChatAnswer | null;
  error: string | null;
  streaming: boolean;
}

const SUGGESTIONS: { text: string; customerId?: string }[] = [
  { text: "Cliente dependiente quiere abrir cuenta sueldo, ¿qué le pido?" },
  { text: "¿Diferencia entre Oro y Platinum?" },
  { text: "Cliente quiere un crédito de consumo" },
  { text: "¿Antigüedad laboral mínima para el hipotecario?" },
  { text: "¿C-1042 cumple para el hipotecario?", customerId: "C-1042" },
];

function describeFailure(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return "No hay nada que reanudar: esta consulta ya no espera una decisión.";
    if (err.status === 429) return "Demasiadas consultas seguidas. Espera un minuto e intenta de nuevo.";
    return `copilot-api rechazó la consulta (código ${err.status}).`;
  }
  console.error(err);
  return `No se pudo completar la consulta: ${(err as Error).message}`;
}

export function Chat() {
  const { session, expire } = useSession();
  const [sessionId] = useState(() => crypto.randomUUID());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [message, setMessage] = useState("");
  const [customerId, setCustomerId] = useState("");
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const log = useRef<HTMLDivElement>(null);

  const customerInvalid = customerId !== "" && !CUSTOMER_ID_PATTERN.test(customerId);
  const busy = turns.some((t) => t.streaming);
  const canSend = message.trim() !== "" && !customerInvalid && !busy;

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  async function run(turn: Pick<Turn, "title" | "question" | "customerId">, stream: AsyncGenerator<ChatEvent>) {
    const id = crypto.randomUUID();
    const update = (patch: (t: Turn) => Partial<Turn>) =>
      setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));
    setTurns((all) => [...all, { ...turn, id, traces: [], answer: null, error: null, streaming: true }]);
    try {
      for await (const event of stream) {
        if (event.type === "trace") update((t) => ({ traces: [...t.traces, event.payload] }));
        else if (event.type === "answer") update(() => ({ answer: event.payload }));
        else update(() => ({ error: event.payload.message }));
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        expire();
        update(() => ({ error: "La sesión venció. Elige una persona y vuelve a preguntar." }));
      } else {
        update(() => ({ error: describeFailure(err) }));
      }
    } finally {
      update(() => ({ streaming: false }));
    }
  }

  function send(event: React.FormEvent) {
    event.preventDefault();
    if (!canSend) return;
    const question = message.trim();
    const customer = customerId || null;
    setMessage("");
    run(
      { title: question, question, customerId: customer },
      streamChat({ session_id: sessionId, message: question, customer_id: customer }, session?.token ?? null),
    );
  }

  function resume(request: AccessRequest) {
    if (!session) return;
    run(
      { title: `Reanudación tras la decisión sobre ${request.customer_id}`, question: null, customerId: request.customer_id },
      resumeSession(sessionId, session.token),
    );
  }

  const traceCount = turns.reduce((n, t) => n + t.traces.length, 0);

  return (
    <div className="relative flex min-h-0 flex-1">
      <section className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-line bg-white">
          <div className="mx-auto flex max-w-3xl flex-wrap items-end gap-x-4 gap-y-2 px-4 py-3 sm:px-6">
            <div>
              <label htmlFor="customer" className="block text-xs font-semibold text-muted">
                Cliente en atención
              </label>
              <input
                id="customer"
                value={customerId}
                onChange={(e) => setCustomerId(e.target.value.toUpperCase().trim())}
                placeholder="C-1042"
                autoComplete="off"
                aria-invalid={customerInvalid}
                aria-describedby="customer-hint"
                className={`mt-1 w-32 rounded-xl border bg-canvas px-3 py-1.5 font-semibold tracking-wide text-navy outline-none placeholder:font-normal placeholder:text-muted/60 focus:border-brand ${
                  customerInvalid ? "border-reject" : "border-line"
                }`}
              />
            </div>
            <p id="customer-hint" className={`pb-2 text-xs ${customerInvalid ? "font-semibold text-reject" : "text-muted"}`}>
              {customerInvalid
                ? "Usa el formato C-1234"
                : session?.role === "Asesor"
                  ? "Opcional. Con un cliente, la respuesta usa solo los datos que tu acceso permite."
                  : session
                    ? "El rol Supervisor no consulta datos de clientes."
                    : "Sin persona solo se consultan documentos y productos."}
            </p>
            <button
              type="button"
              onClick={() => setInspectorOpen(!inspectorOpen)}
              aria-expanded={inspectorOpen}
              aria-controls="inspector"
              className="mb-0.5 ml-auto flex items-center gap-2 rounded-full px-3 py-1.5 text-sm font-semibold text-brand ring-1 ring-brand/30 transition-colors hover:bg-sky aria-expanded:bg-sky"
            >
              <PanelIcon className="size-4" />
              Inspector
              {traceCount > 0 && (
                <span className="rounded-full bg-brand px-1.5 text-xs text-white tabular-nums">{traceCount}</span>
              )}
            </button>
          </div>
        </div>

        <div ref={log} role="log" aria-live="polite" aria-label="Conversación" className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-6">
            {turns.length === 0 && (
              <div className="pt-4 sm:pt-10">
                <h1 className="font-display text-3xl leading-tight font-extrabold tracking-tight text-navy sm:text-4xl">
                  ¿Qué necesita tu cliente?
                </h1>
                <p className="mt-3 max-w-xl text-lg text-muted">
                  Cuéntalo como se lo contarías a un compañero. Cada requisito y cada paso llega con su fuente.
                </p>
                <ul className="mt-8 grid gap-2 sm:grid-cols-2">
                  {SUGGESTIONS.map((s) => (
                    <li key={s.text}>
                      <button
                        type="button"
                        onClick={() => {
                          setMessage(s.text);
                          if (s.customerId) setCustomerId(s.customerId);
                        }}
                        className="h-full w-full rounded-2xl bg-white px-4 py-3 text-left text-[0.95rem] text-ink shadow-soft ring-1 ring-line transition-colors hover:ring-brand/50"
                      >
                        {s.text}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {turns.map((turn) => (
              <div key={turn.id} className="space-y-3">
                <div className="flex flex-col items-end gap-1">
                  {turn.customerId && (
                    <span className="rounded-full bg-sky px-2 py-0.5 text-xs font-semibold text-brand">{turn.customerId}</span>
                  )}
                  <p
                    className={`max-w-[85%] rounded-2xl rounded-br-md px-4 py-2.5 ${
                      turn.question ? "bg-navy text-white" : "bg-access/10 text-sm text-access"
                    }`}
                  >
                    {turn.question ?? turn.title}
                  </p>
                </div>

                {turn.streaming && !turn.answer && (
                  <p className="flex items-center gap-2.5 text-sm text-muted">
                    <span className="size-2 animate-pulse rounded-full bg-cyan" aria-hidden />
                    {turn.traces.length
                      ? `${nodeLabel(turn.traces[turn.traces.length - 1].node)}…`
                      : "Leyendo la consulta…"}
                  </p>
                )}

                {turn.error && (
                  <p role="alert" className="rounded-2xl border-l-4 border-reject bg-white px-4 py-3 text-sm text-ink shadow-soft">
                    {turn.error}
                  </p>
                )}

                {turn.answer && (
                  <AnswerCard answer={turn.answer}>
                    {turn.answer.access_request && session && (
                      <AccessRequestCard
                        request={turn.answer.access_request}
                        token={session.token}
                        onDecided={resume}
                        onUnauthorized={expire}
                      />
                    )}
                    {turn.answer.escalation && (
                      <EscalationCard draft={turn.answer.escalation} token={session?.token ?? null} onUnauthorized={expire} />
                    )}
                  </AnswerCard>
                )}
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={send} className="border-t border-line bg-white">
          <div className="mx-auto flex max-w-3xl items-end gap-3 px-4 py-3 sm:px-6">
            <label htmlFor="message" className="sr-only">
              Consulta
            </label>
            <textarea
              id="message"
              rows={1}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) send(e);
              }}
              maxLength={2000}
              placeholder="Describe la situación del cliente"
              className="max-h-40 min-h-12 flex-1 resize-none rounded-2xl border border-line bg-canvas px-4 py-3 outline-none [field-sizing:content] placeholder:text-muted/70 focus:border-brand"
            />
            <button
              type="submit"
              disabled={!canSend}
              className="flex h-12 items-center gap-2 rounded-full bg-brand px-5 font-semibold text-white transition-colors hover:bg-brand-hover disabled:bg-line disabled:text-muted"
            >
              Consultar
              <SendIcon className="size-4" />
            </button>
          </div>
        </form>
      </section>

      <aside
        id="inspector"
        aria-label="Inspector"
        hidden={!inspectorOpen}
        className="absolute inset-0 z-20 bg-canvas lg:static lg:w-[380px] lg:shrink-0 lg:border-l lg:border-line"
      >
        <Inspector
          turns={turns.filter((t) => t.traces.length > 0)}
          onClose={() => setInspectorOpen(false)}
        />
      </aside>
    </div>
  );
}
