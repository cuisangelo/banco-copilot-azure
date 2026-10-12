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
  { href: "/documentacion", label: "Documentación" },
];

export function TopBar() {
  const pathname = usePathname();
  return (
    <header className="z-30 shrink-0 bg-navy text-white">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-4 px-4 sm:flex-nowrap sm:px-6">
        <Link href="/" className="flex h-14 shrink-0 items-center sm:h-16">
          <Wordmark />
        </Link>
        <span className="hidden h-6 w-px bg-white/20 md:block" aria-hidden />
        <span className="hidden text-sm text-white/75 md:block">Copiloto de atención</span>
        <div className="order-2 ml-auto sm:order-3">
          <PersonaPicker />
        </div>
        <nav
          aria-label="Secciones"
          className="order-3 -mx-4 flex w-[calc(100%+2rem)] border-t border-white/10 sm:order-2 sm:mx-0 sm:ml-6 sm:w-auto sm:border-0"
        >
          {LINKS.map(({ href, label }) => {
            const active = pathname === href || pathname === `${href}/`;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={`relative flex h-11 flex-1 items-center justify-center gap-1.5 px-3 text-sm font-semibold transition-colors sm:h-16 sm:flex-none ${
                  active ? "text-white" : "text-white/70 hover:text-white"
                }`}
              >
                {label}
                {active && <span className="absolute inset-x-3 bottom-0 h-[3px] rounded-full bg-cyan" />}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
