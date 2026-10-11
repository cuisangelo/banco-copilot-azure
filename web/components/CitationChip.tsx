"use client";

import { useId, useState } from "react";
import type { Citation } from "@/lib/types";
import { CardIcon, DocumentIcon, PersonIcon } from "./icons";

const KIND = {
  doc: { Icon: DocumentIcon, label: "Documento" },
  product: { Icon: CardIcon, label: "Sistema de productos" },
  customer: { Icon: PersonIcon, label: "Ficha del cliente" },
};

export function CitationChip({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const { Icon, label } = KIND[citation.kind];

  return (
    <span className="relative inline-block max-w-full min-w-0 align-middle">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
        title={citation.ref}
        className={`inline-flex max-w-full items-center sm:max-w-[20rem] gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors ${
          open ? "border-brand bg-brand text-white" : "border-brand/25 bg-sky text-brand hover:border-brand/60"
        }`}
      >
        <Icon className="size-3.5 shrink-0" />
        <span className="truncate">{citation.ref}</span>
      </button>
      {open && (
        <span
          id={id}
          role="note"
          className="absolute top-full left-0 z-20 mt-1.5 block w-72 max-w-[calc(100vw-3rem)] rounded-xl bg-white p-3 text-sm shadow-lift ring-1 ring-line"
        >
          <span className="mb-1 flex items-center gap-1.5 text-xs font-semibold text-muted">
            <Icon className="size-3.5" />
            {label}
          </span>
          <span className="block text-ink">{citation.snippet}</span>
        </span>
      )}
    </span>
  );
}
