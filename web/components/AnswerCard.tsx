"use client";

import { STATUS_LABEL } from "@/lib/labels";
import type { ChatAnswer, ChatStatus, Citation, Claim } from "@/lib/types";
import { CitationChip } from "./CitationChip";

export const STATUS_TONE: Record<ChatStatus, { bar: string; pill: string; dot: string }> = {
  ok: { bar: "border-t-ok", pill: "bg-ok/10 text-ok", dot: "bg-ok" },
  clarification: { bar: "border-t-pending", pill: "bg-sky text-brand", dot: "bg-brand" },
  insufficient: { bar: "border-t-insufficient", pill: "bg-insufficient/10 text-insufficient", dot: "bg-insufficient" },
  contradiction: { bar: "border-t-contradiction", pill: "bg-contradiction/10 text-contradiction", dot: "bg-contradiction" },
  rejected: { bar: "border-t-reject", pill: "bg-reject/10 text-reject", dot: "bg-reject" },
  access_required: { bar: "border-t-access", pill: "bg-access/10 text-access", dot: "bg-access" },
};

function Sources({ claim, citations }: { claim: Claim; citations: Map<string, Citation> }) {
  return (
    <span className="mt-1.5 flex flex-wrap gap-1.5">
      {claim.citation_ids.map((id) => {
        const citation = citations.get(id);
        return citation && <CitationChip key={id} citation={citation} />;
      })}
    </span>
  );
}

export function AnswerCard({ answer, children }: { answer: ChatAnswer; children?: React.ReactNode }) {
  const tone = STATUS_TONE[answer.status];
  const citations = new Map(answer.citations.map((c) => [c.id, c]));

  return (
    <article className={`rounded-2xl border-t-4 bg-white shadow-soft ${tone.bar}`}>
      <div className="space-y-5 p-5 sm:p-6">
        <header className="space-y-3">
          <span className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold ${tone.pill}`}>
            <span className={`size-2 rounded-full ${tone.dot}`} aria-hidden />
            {STATUS_LABEL[answer.status]}
          </span>
          <p className="text-[1.0625rem] leading-relaxed text-ink">{answer.message}</p>
        </header>

        {answer.requirements.length > 0 && (
          <section>
            <h3 className="mb-2 font-display text-sm font-bold text-navy">Requisitos</h3>
            <ul className="divide-y divide-line rounded-xl border border-line">
              {answer.requirements.map((claim) => (
                <li key={claim.text} className="group px-4 py-3 has-[:checked]:bg-sky/50">
                  <label className="flex cursor-pointer gap-3">
                    <input type="checkbox" className="mt-1 size-4 shrink-0 accent-brand" />
                    <span className="leading-snug group-has-[:checked]:text-muted group-has-[:checked]:line-through">
                      {claim.text}
                    </span>
                  </label>
                  <span className="block pl-7">
                    <Sources claim={claim} citations={citations} />
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {answer.steps.length > 0 && (
          <section>
            <h3 className="mb-2 font-display text-sm font-bold text-navy">
              Pasos
            </h3>
            <ol aria-label="Pasos" className="space-y-3">
              {answer.steps.map((claim, index) => (
                <li key={claim.text} className="flex gap-3">
                  <span
                    className="grid size-7 shrink-0 place-items-center rounded-full bg-navy font-display text-xs font-bold text-white"
                    aria-hidden
                  >
                    {index + 1}
                  </span>
                  <span className="pt-0.5">
                    <span className="block leading-snug">{claim.text}</span>
                    <Sources claim={claim} citations={citations} />
                  </span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {children}
      </div>
    </article>
  );
}
