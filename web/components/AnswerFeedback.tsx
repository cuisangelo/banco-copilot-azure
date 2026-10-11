"use client";

import { useState } from "react";
import { ApiError, sendFeedback } from "@/lib/api";
import type { ChatStatus, FeedbackCreate } from "@/lib/types";

type Rating = FeedbackCreate["rating"];

interface Props {
  sessionId: string;
  turnIndex: number;
  answerStatus: ChatStatus;
  token: string | null;
  onUnauthorized: () => void;
}

const RATINGS: { rating: Rating; emoji: string; label: string }[] = [
  { rating: "up", emoji: "👍", label: "Respuesta útil" },
  { rating: "down", emoji: "👎", label: "Respuesta no útil" },
];

export function AnswerFeedback({ sessionId, turnIndex, answerStatus, token, onUnauthorized }: Props) {
  const [chosen, setChosen] = useState<Rating | null>(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function send(rating: Rating) {
    setBusy(true);
    setError(null);
    try {
      await sendFeedback(
        { session_id: sessionId, turn_index: turnIndex, rating, comment: comment.trim() || null, answer_status: answerStatus },
        token,
      );
      setDone("Gracias por calificar esta respuesta.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return onUnauthorized();
      if (err instanceof ApiError && err.status === 409) setDone("Ya calificaste esta respuesta.");
      else if (err instanceof ApiError && err.status === 429) setError("Demasiadas acciones seguidas. Espera un minuto.");
      else setError(`No se pudo registrar la calificación (${(err as Error).message}).`);
    } finally {
      setBusy(false);
    }
  }

  function choose(rating: Rating) {
    setChosen(rating);
    if (rating === "up") send(rating);
  }

  const locked = busy || done !== null;

  return (
    <section aria-label="Calificar respuesta" className="border-t border-line pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-muted">¿Te sirvió esta respuesta?</span>
        {RATINGS.map(({ rating, emoji, label }) => (
          <button
            key={rating}
            type="button"
            aria-label={label}
            aria-pressed={chosen === rating}
            disabled={locked}
            onClick={() => choose(rating)}
            className="grid size-9 place-items-center rounded-full text-lg ring-1 ring-line transition-colors hover:bg-sky aria-pressed:bg-sky aria-pressed:ring-brand/50 disabled:opacity-60"
          >
            <span aria-hidden>{emoji}</span>
          </button>
        ))}
      </div>

      {chosen === "down" && done === null && (
        <div className="mt-3 space-y-2">
          <label htmlFor={`feedback-${turnIndex}`} className="block text-sm font-semibold text-navy">
            ¿Qué faltó o estuvo mal? <span className="font-normal text-muted">(opcional)</span>
          </label>
          <textarea
            id={`feedback-${turnIndex}`}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            maxLength={500}
            rows={2}
            disabled={busy}
            className="w-full resize-none rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-brand"
          />
          <button
            type="button"
            disabled={busy}
            onClick={() => send("down")}
            className="rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand-hover disabled:bg-line disabled:text-muted"
          >
            Enviar calificación
          </button>
        </div>
      )}

      {done && (
        <p role="status" className="mt-2 text-sm font-semibold text-navy">
          {done}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-sm font-semibold text-reject">
          {error}
        </p>
      )}
    </section>
  );
}
