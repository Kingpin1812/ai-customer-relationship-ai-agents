"use client";

import { ShieldCheck } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { ErrorState } from "@/components/states";
import { ApiError, apiPost, setToken } from "@/lib/api";

const ACCOUNTS = [
  { email: "manager@demo.test", name: "Maya Manager", role: "Manager", note: "Submits and approves" },
  { email: "operator@demo.test", name: "Omar Operator", role: "Operator", note: "Submits own work; cannot approve" },
  { email: "admin@demo.test", name: "Asha Admin", role: "Admin", note: "Users, integrations, everything" },
  { email: "viewer@demo.test", name: "Vik Viewer", role: "Viewer", note: "Read-only" },
];

function LoginForm() {
  const router = useRouter();
  const expired = useSearchParams().get("expired");
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const signIn = async (email: string) => {
    setBusy(email);
    setError(null);
    try {
      const { access_token } = await apiPost<{ access_token: string }>("/auth/dev-login", { email });
      setToken(access_token);
      router.replace("/dashboard");
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", "Sign-in failed."));
      setBusy(null);
    }
  };

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-lg flex-col justify-center px-4 py-10">
      <div className="mb-6 flex items-center gap-2 text-primary">
        <ShieldCheck className="size-6" aria-hidden />
        <span className="font-semibold">Workflow Control</span>
      </div>
      <h1 className="text-2xl font-semibold">Sign in to the demo</h1>
      <p className="mt-2 text-sm text-muted">
        Development sign-in with synthetic data. Production uses your identity provider, and this screen does not exist there.
      </p>
      {expired && (
        <p role="status" className="mt-4 rounded-md bg-gate-soft p-3 text-sm text-gate">
          Your session ended. Sign in again to continue.
        </p>
      )}
      {error && (
        <div className="mt-4">
          <ErrorState error={error} />
        </div>
      )}
      <ul className="mt-6 grid gap-3">
        {ACCOUNTS.map((account) => (
          <li key={account.email}>
            <button
              type="button"
              disabled={busy !== null}
              onClick={() => signIn(account.email)}
              className="flex w-full items-center justify-between gap-4 rounded-lg border border-border bg-surface p-4 text-left hover:border-primary disabled:opacity-60"
            >
              <span>
                <span className="block text-sm font-medium">{account.name}</span>
                <span className="block text-xs text-muted">{account.note}</span>
              </span>
              <span className="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs">{account.role}</span>
            </button>
          </li>
        ))}
      </ul>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
