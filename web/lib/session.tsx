"use client";

import { createContext, useContext, useState } from "react";
import { createDemoSession } from "./api";
import type { PersonaKey, Role } from "./types";

export interface PersonaSession {
  persona: PersonaKey;
  token: string;
  name: string;
  role: Role;
}

interface SessionState {
  session: PersonaSession | null;
  notice: string | null;
  pickerOpen: boolean;
  setPickerOpen: (open: boolean) => void;
  signIn: (persona: PersonaKey) => Promise<void>;
  signOut: () => void;
  expire: () => void;
}

const SessionContext = createContext<SessionState | null>(null);

// The persona token lives only in memory: a reload drops it on purpose.
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<PersonaSession | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  async function signIn(persona: PersonaKey) {
    setNotice(null);
    try {
      const { token, name, role } = await createDemoSession(persona);
      setSession({ persona, token, name, role });
    } catch (error) {
      setSession(null);
      setNotice(`No se pudo iniciar la sesión de demo (${(error as Error).message}). Intenta de nuevo.`);
      setPickerOpen(true);
    }
  }

  function signOut() {
    setNotice(null);
    setSession(null);
  }

  function expire() {
    setSession(null);
    setNotice("Tu sesión de demo venció. Elige una persona para continuar.");
    setPickerOpen(true);
  }

  return (
    <SessionContext.Provider value={{ session, notice, pickerOpen, setPickerOpen, signIn, signOut, expire }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  const state = useContext(SessionContext);
  if (!state) throw new Error("useSession must be used inside SessionProvider");
  return state;
}
