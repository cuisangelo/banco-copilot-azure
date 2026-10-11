"use client";

import { useEffect, useState } from "react";
import { ApiError, listFeedback } from "@/lib/api";
import { formatTime } from "@/lib/format";
import { STATUS_LABEL } from "@/lib/labels";
import { useSession } from "@/lib/session";
import { PERSONAS, type Feedback, type PersonaKey } from "@/lib/types";
import { LockIcon } from "./icons";

const percent = new Intl.NumberFormat("es-CL", { style: "percent", maximumFractionDigits: 0 });
const actorName = (actor: string) => (actor === "anonymous" ? "Anónimo" : (PERSONAS[actor as PersonaKey]?.name ?? actor));

export function FeedbackPanel() {
  const { session, expire } = useSession();
  const [feedback, setFeedback] = useState<Feedback[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const token = session?.role === "Supervisor" ? session.token : null;

  useEffect(() => {
    if (!token) return;
    let current = true;
    listFeedback(token).then(
      (list) => current && setFeedback(list),
      (err) => {
        if (!current) return;
        if (err instanceof ApiError && err.status === 401) return expire();
        setError(`No se pudo cargar el feedback (${(err as Error).message}).`);
      },
    );
    return () => {
      current = false;
    };
  }, [token, expire]);

  if (!token) {
    return (
      <div className="mx-auto max-w-xl px-4 pt-16 text-center sm:px-6">
        <LockIcon className="mx-auto size-10 text-brand" />
        <h1 className="mt-4 font-display text-2xl font-extrabold text-navy">Feedback de los asesores</h1>
        <p className="mt-2 text-muted">
          Elige a Sofía, con rol Supervisor, en la barra superior para ver cómo califican los asesores las respuestas del copiloto.
        </p>
      </div>
    );
  }

  const ups = feedback?.filter((f) => f.rating === "up").length ?? 0;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight text-navy">Feedback de los asesores</h1>
      <p className="mt-1 text-muted">Evaluación humana de las últimas 50 respuestas calificadas.</p>

      {error && (
        <p role="alert" className="mt-4 text-sm font-semibold text-reject">
          {error}
        </p>
      )}

      {feedback && feedback.length === 0 && (
        <p className="mt-6 rounded-2xl border border-dashed border-line px-5 py-8 text-center text-muted">
          Aún no hay calificaciones. Aparecen cuando un asesor marca 👍 o 👎 en una respuesta.
        </p>
      )}

      {feedback && feedback.length > 0 && (
        <>
          <p className="mt-6 inline-flex items-baseline gap-2 rounded-2xl bg-white px-5 py-3 shadow-soft ring-1 ring-line">
            <span className="font-display text-3xl font-extrabold text-ok-ink">{percent.format(ups / feedback.length)}</span>
            <span className="text-sm text-muted">
              de respuestas útiles 👍 · {ups} de {feedback.length}
            </span>
          </p>
          <div className="mt-4 overflow-x-auto rounded-2xl bg-white shadow-soft ring-1 ring-line">
            <table aria-label="Calificaciones del copiloto" className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-canvas text-xs text-muted">
                <tr>
                  <th className="px-4 py-2.5 font-semibold">Fecha</th>
                  <th className="px-4 py-2.5 font-semibold">Asesor</th>
                  <th className="px-4 py-2.5 font-semibold">Estado de la respuesta</th>
                  <th className="px-4 py-2.5 font-semibold">Calificación</th>
                  <th className="px-4 py-2.5 font-semibold">Comentario</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {feedback.map((f) => (
                  <tr key={f.id}>
                    <td className="px-4 py-3 whitespace-nowrap text-muted">{formatTime(f.created_at)}</td>
                    <td className="px-4 py-3 font-semibold text-navy">{actorName(f.actor)}</td>
                    <td className="px-4 py-3">{STATUS_LABEL[f.answer_status]}</td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span aria-hidden>{f.rating === "up" ? "👍" : "👎"}</span> {f.rating === "up" ? "Útil" : "No útil"}
                    </td>
                    <td className="px-4 py-3 text-ink">{f.comment ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
