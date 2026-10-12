"use client";

import { LockIcon } from "@/components/icons";
import { portalUrl, resourceByKey, type Layout } from "./azure";
import { LOGIN_URL, usePortal } from "./portal";

export function ResourceList({ layout }: { layout: Layout }) {
  const deployment = usePortal();
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        {deployment ? (
          <a
            href={`${deployment.resourceGroupUrl}/overview`}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand"
          >
            Grupo de recursos {deployment.resourceGroup}
          </a>
        ) : (
          <a
            href={LOGIN_URL}
            className="rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand"
          >
            Iniciar sesión para abrir en Azure
          </a>
        )}
        <p className="flex items-center gap-1.5 text-sm text-muted">
          <LockIcon className="size-4 shrink-0" />
          Los nombres y enlaces al portal solo se muestran al autor, con sesión iniciada.
        </p>
      </div>
      <ul
        aria-label="Recursos desplegados"
        className="divide-y divide-line overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-line"
      >
        {layout.resources.map((r) => {
          const named = deployment && resourceByKey(deployment, r.key);
          return (
            <li
              key={r.key}
              className="grid gap-x-6 gap-y-2 px-5 py-4 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)_auto] lg:items-center"
            >
              <div className="min-w-0">
                <h3 className="font-mono text-[0.95rem] font-semibold break-all text-navy">{named?.name ?? r.key}</h3>
                <p className="mt-0.5 text-sm text-muted">
                  {r.service}, {r.regionLabel}
                </p>
              </div>
              <p className="text-[0.95rem] leading-relaxed text-ink">{r.role}</p>
              {deployment && named && (
                <a
                  href={portalUrl(deployment, named)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="justify-self-start rounded-full px-4 py-2 text-sm font-semibold whitespace-nowrap text-brand ring-1 ring-brand/30 transition-colors hover:bg-sky"
                >
                  Ver en Azure<span className="sr-only">: {named.name}</span>
                </a>
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}
