"use client";

import { useEffect, useRef, useState } from "react";
import { ApiError, getAccessRequest } from "@/lib/api";
import { FIELD_LABEL, REQUEST_STATUS_LABEL } from "@/lib/labels";
import { GRANT_MINUTES, type AccessRequest } from "@/lib/types";
import { LockIcon } from "./icons";

export const POLL_MS = 3000;

interface Props {
  request: AccessRequest;
  token: string;
  onDecided: (request: AccessRequest) => void;
  onUnauthorized: () => void;
}

export function AccessRequestCard({ request: initial, token, onDecided, onUnauthorized }: Props) {
  const [request, setRequest] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const callbacks = useRef({ onDecided, onUnauthorized });
  const pending = request.status === "pending";

  useEffect(() => {
    callbacks.current = { onDecided, onUnauthorized };
  });

  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(async () => {
      try {
        const latest = await getAccessRequest(request.id, token);
        setError(null);
        setRequest(latest);
        if (latest.status !== "pending") {
          clearInterval(timer);
          callbacks.current.onDecided(latest);
        }
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          clearInterval(timer);
          return callbacks.current.onUnauthorized();
        }
        setError(`No se pudo consultar el estado de la solicitud (${(err as Error).message}). Reintentando.`);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [pending, request.id, token]);

  const decided = !pending;

  return (
    <section className="rounded-xl border border-access/30 bg-access/[0.04] p-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-display text-sm font-bold text-access">
          <LockIcon className="size-4" />
          Solicitud de acceso para <span className="text-ink">{request.customer_id}</span>
        </h3>
        <span
          className={`inline-flex items-center gap-2 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
            pending ? "bg-white text-access ring-1 ring-access/30" : "bg-access text-white"
          }`}
        >
          {pending && <span className="size-1.5 animate-pulse rounded-full bg-access" aria-hidden />}
          {REQUEST_STATUS_LABEL[request.status]}
        </span>
      </header>

      <p className="mt-2 text-sm text-muted">{request.purpose}</p>

      <ul className="mt-3 flex flex-wrap gap-2" aria-label="Campos solicitados">
        {request.fields.map((field) => {
          const approved = request.approved_fields.includes(field);
          return (
            <li
              key={field}
              className={`rounded-lg px-2.5 py-1 text-sm ${
                !decided ? "bg-white ring-1 ring-line" : approved ? "bg-ok/10 text-ok" : "bg-reject/10 text-reject"
              }`}
            >
              <span className="font-semibold">{FIELD_LABEL[field]}</span>
              {decided && <span className="ml-1.5 text-xs">{approved ? "Autorizado" : "No autorizado"}</span>}
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-xs text-muted">
        {pending
          ? `Un Supervisor debe aprobarla. El permiso dura ${GRANT_MINUTES} minutos y solo cubre estos campos.`
          : request.approved_fields.length
            ? `Decidida por un Supervisor. El permiso vence en ${GRANT_MINUTES} minutos.`
            : "Decidida por un Supervisor. El copiloto responderá sin estos datos."}
      </p>
      {error && (
        <p role="alert" className="mt-2 text-xs text-reject">
          {error}
        </p>
      )}
    </section>
  );
}
