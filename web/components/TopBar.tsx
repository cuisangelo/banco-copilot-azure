"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { PersonaPicker } from "./PersonaPicker";

// Southern Cross: four stars, the brand mark of a bank called "Austral".
function Wordmark() {
  return (
    <span className="flex items-center gap-2.5">
      <svg viewBox="0 0 28 28" className="size-7" aria-hidden>
        <circle cx="14" cy="3.5" r="2.6" fill="var(--color-cyan)" />
        <circle cx="14" cy="24" r="3" fill="var(--color-cyan)" />
        <circle cx="5" cy="13" r="2.2" fill="white" />
        <circle cx="22.5" cy="11" r="1.9" fill="white" />
        <circle cx="18" cy="17.5" r="1.1" fill="white" opacity=".7" />
      </svg>
      <span className="font-display text-lg leading-none font-extrabold tracking-tight text-white">
        Banco <span className="font-semibold">Austral</span>
      </span>
    </span>
  );
}

const LINKS = [
  { href: "/", label: "Atención" },
  { href: "/supervisor", label: "Aprobaciones" },
];

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-30 bg-navy text-white">
      <div className="mx-auto flex h-16 max-w-[1440px] items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="shrink-0">
          <Wordmark />
        </Link>
        <span className="hidden h-6 w-px bg-white/20 md:block" aria-hidden />
        <span className="hidden text-sm text-white/75 md:block">Copiloto de atención</span>
        <nav aria-label="Secciones" className="ml-auto flex items-center gap-1 sm:ml-6">
          {LINKS.map(({ href, label }) => {
            const active = pathname === href || pathname === `${href}/`;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative rounded-lg px-2.5 py-2 text-sm font-semibold transition-colors sm:px-3 ${
                  active ? "text-white" : "text-white/70 hover:text-white"
                }`}
              >
                {label}
                {active && <span className="absolute inset-x-2.5 -bottom-[13px] h-[3px] rounded-full bg-cyan sm:inset-x-3" />}
              </Link>
            );
          })}
        </nav>
        <div className="sm:ml-auto">
          <PersonaPicker />
        </div>
      </div>
    </header>
  );
}
