"use client";

import { useEffect, useRef } from "react";
import { useSession } from "@/lib/session";
import { PERSONAS, type PersonaKey } from "@/lib/types";
import { ChevronIcon } from "./icons";

const AVATAR_TONE: Record<PersonaKey, string> = {
  ana: "bg-brand text-white",
  bruno: "bg-cyan text-navy",
  sofia: "bg-white text-navy ring-2 ring-cyan",
};

function Avatar({ persona }: { persona: PersonaKey | null }) {
  if (!persona) {
    return (
      <span className="grid size-8 place-items-center rounded-full border border-dashed border-current opacity-70" aria-hidden>
        <span className="size-2 rounded-full bg-current" />
      </span>
    );
  }
  return (
    <span className={`grid size-8 place-items-center rounded-full font-display text-sm font-bold ${AVATAR_TONE[persona]}`} aria-hidden>
      {PERSONAS[persona].name[0]}
    </span>
  );
}

const OPTIONS: (PersonaKey | null)[] = [null, "ana", "bruno", "sofia"];

export function PersonaPicker() {
  const { session, notice, pickerOpen, setPickerOpen, signIn, signOut } = useSession();
  const root = useRef<HTMLDivElement>(null);
  const label = session ? `${session.name}, ${session.role}` : "Sin persona";

  useEffect(() => {
    if (!pickerOpen) return;
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !root.current?.contains(event.target as Node)) {
        setPickerOpen(false);
      }
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [pickerOpen, setPickerOpen]);

  async function choose(persona: PersonaKey | null) {
    setPickerOpen(false);
    if (persona === null) signOut();
    else await signIn(persona);
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        aria-label={`Persona: ${label}`}
        aria-haspopup="listbox"
        aria-expanded={pickerOpen}
        onClick={() => setPickerOpen(!pickerOpen)}
        className="flex items-center gap-2.5 rounded-full py-1 pr-3 pl-1 text-white transition-colors hover:bg-white/10"
      >
        <Avatar persona={session?.persona ?? null} />
        <span className="hidden text-left leading-tight sm:block">
          <span className="block text-sm font-semibold">{session ? session.name : "Sin persona"}</span>
          <span className="block text-xs text-white/70">{session ? session.role : "Solo documentos"}</span>
        </span>
        <span className="sr-only sm:hidden">{session ? `${session.name} ${session.role}` : "Sin persona"}</span>
        <ChevronIcon className={`size-4 transition-transform ${pickerOpen ? "rotate-180" : ""}`} />
      </button>

      {pickerOpen && (
        <div className="absolute top-full right-0 z-40 mt-2 w-72 overflow-hidden rounded-2xl bg-white text-ink shadow-lift ring-1 ring-line">
          {notice && (
            <p role="alert" className="border-b border-line bg-reject/5 px-4 py-3 text-sm text-reject">
              {notice}
            </p>
          )}
        <ul role="listbox" aria-label="Elige una persona de demo" className="py-2">
          {OPTIONS.map((persona) => {
            const selected = (session?.persona ?? null) === persona;
            return (
              <li
                key={persona ?? "none"}
                role="option"
                aria-selected={selected}
                tabIndex={0}
                onClick={() => choose(persona)}
                onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && choose(persona)}
                className={`flex cursor-pointer items-center gap-3 px-4 py-2.5 hover:bg-sky focus-visible:bg-sky ${selected ? "bg-sky/60" : ""}`}
              >
                <span className={persona ? "" : "text-muted"}>
                  <Avatar persona={persona} />
                </span>
                <span className="leading-tight">
                  <span className="block font-semibold">{persona ? PERSONAS[persona].name : "Sin persona"}</span>
                  <span className="block text-xs text-muted">
                    {persona ? PERSONAS[persona].role : "Solo documentos y productos"}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
        </div>
      )}
    </div>
  );
}
