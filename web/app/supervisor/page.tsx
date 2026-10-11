"use client";

import { useState } from "react";
import { FeedbackPanel } from "@/components/FeedbackPanel";
import { SupervisorInbox } from "@/components/SupervisorInbox";

const TABS = [
  { id: "requests", label: "Solicitudes" },
  { id: "feedback", label: "Feedback" },
] as const;

export default function SupervisorPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("requests");

  return (
    <main className="min-h-0 flex-1 overflow-y-auto">
      <div className="border-b border-line bg-white">
        <div role="tablist" aria-label="Vista del Supervisor" className="mx-auto flex max-w-5xl gap-1 px-4 sm:px-6">
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              id={`tab-${id}`}
              type="button"
              role="tab"
              aria-selected={tab === id}
              aria-controls={`panel-${id}`}
              onClick={() => setTab(id)}
              className="border-b-2 border-transparent px-4 py-3 text-sm font-semibold text-muted transition-colors hover:text-navy aria-selected:border-brand aria-selected:text-brand"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "requests" ? <SupervisorInbox /> : <FeedbackPanel />}
      </div>
    </main>
  );
}
