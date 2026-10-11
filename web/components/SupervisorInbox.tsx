"use client";

import { useEffect, useState } from "react";
import { ApiError, decideAccessRequest, listAccessRequests } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { FIELD_LABEL, REQUEST_STATUS_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { GRANT_MINUTES, PERSONAS, type AccessRequest, type Level2Field, type PersonaKey } from "@/lib/types";
import { LockIcon, RefreshIcon } from "./icons";

const personName = (sub: string | null) => (sub ? (PERSONAS[sub as PersonaKey]?.name ?? sub) : "—");

function PendingCard({
  request,
  token,
  onDecided,
  onUnauthorized,
}: {
  request: AccessRequest;
  token: string;
  onDecided: (r: AccessRequest) => void;
  onUnauthorized: () => void;
}) {
  const [selected, setSelected] = useState<Level2Field[]>(request.fields);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stale, setStale] = useState(false);

  async function decide(approved_fields: Level2Field[]) {
    setBusy(true);
    setError(null);
    try {
      onDecided(await decideAccessRequest(request.id, { approved_fields }, token));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      if (err instanceof ApiError && err.status === 409) {
        setStale(true);
        setError("Ya decidida en otra pestaña o por otro Supervisor. Actualiza la bandeja para ver el resultado.");
      } else if (err instanceof ApiError && err.status === 403) {
        setError("No puedes decidir esta solicitud: un Supervisor no aprueba solicitudes propias.");
      } else {
        setError(`No se pudo registrar la decisión (${(err as Error).message}).`);
      }
    } finally {
      setBusy(false);
    }
  }

  const toggle = (field: Level2Field) =>
    setSelected((s) => (s.includes(field) ? s.filter((f) => f !== field) : request.fields.filter((f) => f === field || s.includes(f))));

  return (
    <article className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-line">
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-display text-lg font-bold text-navy">Cliente {request.customer_id}</h3>
          <p className="text-sm text-muted">
            Pedido por <span className="font-semibold text-ink">{personName(request.requested_by)}</span> el{" "}
            {formatTime(request.created_at)}
          </p>
        </div>
        <span className="flex items-center gap-1.5 rounded-full bg-access/10 px-2.5 py-1 text-xs font-semibold text-access">
          <LockIcon className="size-3.5" />
          Nivel 2
        </span>
      </header>

      <p className="mt-3 rounded-xl bg-canvas px-3 py-2 text-[0.95rem] text-ink">{request.purpose}</p>

      <fieldset className="mt-4" disabled={busy || stale}>
        <legend className="mb-2 text-sm font-semibold text-navy">Campos que autorizas</legend>
        <div className="flex flex-wrap gap-2">
          {request.fields.map((field) => (
            <label
              key={field}
              className="flex cursor-pointer items-center gap-2 rounded-xl px-3 py-2 text-sm ring-1 ring-line has-[:checked]:bg-sky has-[:checked]:ring-brand/40"
            >
              <input
                type="checkbox"
                checked={selected.includes(field)}
                onChange={() => toggle(field)}
                className="size-4 accent-brand"
              />
              {FIELD_LABEL[field]}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy || stale || selected.length === 0}
          onClick={() => decide(selected)}
          className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:bg-line disabled:text-muted"
        >
          Aprobar selección
        </button>
        <button
          type="button"
          disabled={busy || stale}
          onClick={() => decide([])}
          className="rounded-full px-4 py-2 text-sm font-semibold text-reject ring-1 ring-reject/40 transition-colors hover:bg-reject/5 disabled:opacity-50"
        >
          Rechazar
        </button>
        <span className="text-xs text-muted">El permiso dura {GRANT_MINUTES} minutos.</span>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm font-semibold text-reject">
          {error}
        </p>
      )}
    </article>
  );
}

export function SupervisorInbox() {
  const { session, expire } = useSession();
  const [requests, setRequests] = useState<AccessRequest[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const token = session?.role === "Supervisor" ? session.token : null;

  useEffect(() => {
    if (!token) return;
    let current = true;
    listAccessRequests(token).then(
      (list) => {
        if (!current) return;
        setRequests(list);
        setError(null);
      },
      (err) => {
        if (!current) return;
        if (err instanceof ApiError && err.status === 401) return expire();
        setError(`No se pudo cargar la bandeja (${(err as Error).message}).`);
      },
    );
    return () => {
      current = false;
    };
  }, [token, reloads, expire]);

  if (!token) {
    return (
      <div className="mx-auto max-w-xl px-4 pt-16 text-center sm:px-6">
        <LockIcon className="mx-auto size-10 text-brand" />
        <h1 className="mt-4 font-display text-2xl font-extrabold text-navy">Bandeja del Supervisor</h1>
        <p className="mt-2 text-muted">
          Elige a Sofía, con rol Supervisor, en la barra superior para revisar las solicitudes de acceso a datos de clientes.
        </p>
      </div>
    );
  }

  const pending = requests?.filter((r) => r.status === "pending") ?? [];
  const decided = requests?.filter((r) => r.status !== "pending") ?? [];

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold tracking-tight text-navy">Solicitudes de acceso</h1>
          <p className="mt-1 text-muted">Autoriza por campo solo lo que la consulta necesita.</p>
        </div>
        <button
          type="button"
          onClick={() => setReloads((n) => n + 1)}
          className="flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold text-brand ring-1 ring-brand/30 hover:bg-sky"
        >
          <RefreshIcon className="size-4" />
          Actualizar
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 text-sm font-semibold text-reject">
          {error}
        </p>
      )}

      <section className="mt-6" aria-label="Pendientes">
        {requests && pending.length === 0 && (
          <p className="rounded-2xl border border-dashed border-line px-5 py-8 text-center text-muted">
            No hay solicitudes pendientes. Las nuevas aparecen al actualizar.
          </p>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {pending.map((request) => (
            <PendingCard
              key={request.id}
              request={request}
              token={token}
              onUnauthorized={expire}
              onDecided={(updated) => setRequests((all) => all!.map((r) => (r.id === updated.id ? updated : r)))}
            />
          ))}
        </div>
      </section>

      {decided.length > 0 && (
        <section className="mt-10">
          <h2 className="font-display text-lg font-bold text-navy">Historial de decisiones</h2>
          <div className="mt-3 overflow-x-auto rounded-2xl bg-white shadow-soft ring-1 ring-line">
            <table aria-label="Historial de decisiones" className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-canvas text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Cliente</th>
                  <th className="px-4 py-2.5 font-semibold">Asesor</th>
                  <th className="px-4 py-2.5 font-semibold">Campos autorizados</th>
                  <th className="px-4 py-2.5 font-semibold">Estado</th>
                  <th className="px-4 py-2.5 font-semibold">Decidió</th>
                  <th className="px-4 py-2.5 font-semibold">Cuándo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {decided.map((r) => (
                  <tr key={r.id}>
                    <td className="px-4 py-3 font-semibold text-navy">{r.customer_id}</td>
                    <td className="px-4 py-3">{personName(r.requested_by)}</td>
                    <td className="px-4 py-3">
                      {r.approved_fields.length ? r.approved_fields.map((f) => FIELD_LABEL[f]).join(", ") : "Ninguno"}
                    </td>
                    <td className="px-4 py-3">{REQUEST_STATUS_LABEL[r.status]}</td>
                    <td className="px-4 py-3">{personName(r.decided_by)}</td>
                    <td className="px-4 py-3 text-muted">{r.decided_at && formatTime(r.decided_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
