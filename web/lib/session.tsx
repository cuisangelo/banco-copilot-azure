"use client";

import { createContext, useCallback, useContext, useState } from "react";
import { ApiError, createDemoSession } from "./api";
import type { PersonaKey, Role } from "./types";

// copilot-api scales to zero; a cold start takes ~25 s and the first calls fail at the ingress
// (network error or 502/503/504) before reaching the app. ~40 s of backoff covers it.
const WAKE_RETRY_DELAYS_MS = [2000, 4000, 8000, 12000, 15000];

function isColdStart(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof ApiError && [502, 503, 504].includes(error.status));
}

export interface PersonaSession {
  persona: PersonaKey;
  token: string;
  name: string;
  role: Role;
}

interface SessionState {
  session: PersonaSession | null;
  notice: string | null;
  connecting: PersonaKey | null;
  waking: boolean;
  pickerOpen: boolean;
  setPickerOpen: (open: boolean) => void;
  signIn: (persona: PersonaKey) => Promise<void>;
  signOut: () => void;
  expire: () => void;
}

const SessionContext = createContext<SessionState | null>(null);

// The persona token lives only in memory: a reload drops it on purpose.
export function SessionProvider({
  children,
  retryDelaysMs = WAKE_RETRY_DELAYS_MS,
}: {
  children: React.ReactNode;
  retryDelaysMs?: number[];
}) {
  const [session, setSession] = useState<PersonaSession | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<PersonaKey | null>(null);
  const [waking, setWaking] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  async function signIn(persona: PersonaKey) {
    setNotice(null);
    setConnecting(persona);
    try {
      for (let attempt = 0; ; attempt++) {
        try {
          const { token, name, role } = await createDemoSession(persona);
          setSession({ persona, token, name, role });
          setPickerOpen(false);
          return;
        } catch (error) {
          if (!isColdStart(error) || attempt >= retryDelaysMs.length) throw error;
          setWaking(true);
          await new Promise((resolve) => setTimeout(resolve, retryDelaysMs[attempt]));
        }
      }
    } catch (error) {
      setSession(null);
      setNotice(`No se pudo iniciar la sesión de demo (${(error as Error).message}). Intenta de nuevo.`);
      setPickerOpen(true);
    } finally {
      setConnecting(null);
      setWaking(false);
    }
  }

  function signOut() {
    setNotice(null);
    setSession(null);
  }

  // Stable identity: consumers list it as an effect dependency.
  const expire = useCallback(() => {
    setSession(null);
    setNotice("Tu sesión de demo venció. Elige una persona para continuar.");
    setPickerOpen(true);
  }, []);

  return (
    <SessionContext.Provider value={{ session, notice, connecting, waking, pickerOpen, setPickerOpen, signIn, signOut, expire }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const state = useContext(SessionContext);
  if (!state) throw new Error("useSession must be used inside SessionProvider");
  return state;
}
