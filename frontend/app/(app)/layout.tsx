"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { ErrorState, LoadingState } from "@/components/states";
import { SessionProvider } from "@/hooks/useSession";
import { ApiError, apiGet, getToken } from "@/lib/api";
import type { Me } from "@/types/api";

export default function AppLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    apiGet<Me>("/auth/me").then(setMe, (e) => {
      if (e instanceof ApiError && e.status !== 401) setError(e);
    });
  }, [router]);

  if (error) {
    return (
      <main className="mx-auto max-w-xl p-6">
        <ErrorState error={error} onRetry={() => window.location.reload()} />
      </main>
    );
  }
  if (!me) return <LoadingState label="Signing you in" />;
  return (
    <SessionProvider me={me}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
