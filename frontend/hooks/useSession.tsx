"use client";

import { createContext, useContext, type ReactNode } from "react";
import type { Me } from "@/types/api";

const SessionContext = createContext<Me | null>(null);

export function SessionProvider({ me, children }: { me: Me; children: ReactNode }) {
  return <SessionContext.Provider value={me}>{children}</SessionContext.Provider>;
}

export function useSession(): Me {
  const me = useContext(SessionContext);
  if (!me) throw new Error("useSession must be used inside the signed-in layout");
  return me;
}

/** For hiding controls only. The server enforces every permission regardless. */
export function useCan() {
  const me = useSession();
  return (permission: string) => me.permissions.includes(permission);
}
