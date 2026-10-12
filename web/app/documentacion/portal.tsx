"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { resolveDeployment, type Deployment } from "./azure";

// Static Web Apps serves /privado/* to the owner role only (public/staticwebapp.config.json).
export const INVENTORY_URL = "/privado/inventario.json";
export const LOGIN_URL = "/.auth/login/aad?post_login_redirect_uri=/documentacion";

const PortalContext = createContext<Deployment | null>(null);

/** The deployment with names and portal links, for the signed-in owner; null for everyone else. */
export const usePortal = () => useContext(PortalContext);

async function ownerDeployment(): Promise<Deployment | null> {
  const me = await fetch("/.auth/me");
  if (!me.ok) return null;
  const { clientPrincipal } = await me.json();
  if (!clientPrincipal?.userRoles.includes("owner")) return null;
  const inventory = await fetch(INVENTORY_URL);
  if (!inventory.ok) throw new Error(`${INVENTORY_URL}: HTTP ${inventory.status}`);
  return resolveDeployment(await inventory.json());
}

/** Sign-out for the owner; for everyone else, sign-in, which only adds names and portal links. */
export function AccountLink({ className }: { className: string }) {
  return usePortal() ? (
    <a href="/.auth/logout?post_logout_redirect_uri=/documentacion" className={className}>
      Cerrar sesión
    </a>
  ) : (
    <a href={LOGIN_URL} className={className}>
      Iniciar sesión
    </a>
  );
}

export function PortalProvider({ children }: { children: React.ReactNode }) {
  const [deployment, setDeployment] = useState<Deployment | null>(null);
  useEffect(() => {
    // The page stays public when this fails; only the portal links depend on it.
    ownerDeployment().then(setDeployment, (error) => console.error(error));
  }, []);
  return <PortalContext.Provider value={deployment}>{children}</PortalContext.Provider>;
}
