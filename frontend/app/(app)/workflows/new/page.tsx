"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/form";
import { useCan, useSession } from "@/hooks/useSession";
import { ApiError, apiPost, apiUpload } from "@/lib/api";

const DEMO_REQUEST =
  "Prepare an invoice for Acme Ltd for 10 hours of approved consulting at ₹2,500 per hour, update the CRM note, generate this month's sales summary, and prepare an email.";

const SIMULATIONS = [
  { value: "", label: "None" },
  { value: "crm_timeout", label: "CRM times out twice, then recovers" },
  { value: "crm_down", label: "CRM stays down (retries run out)" },
  { value: "report_down", label: "Report store unavailable" },
  { value: "email_unknown_sent", label: "Mail provider goes silent after sending" },
  { value: "email_unknown_lost", label: "Mail provider goes silent, nothing sent" },
];

export default function NewWorkflowPage() {
  const can = useCan();
  const me = useSession();
  const router = useRouter();
  const [request, setRequest] = useState("");
  const [customer, setCustomer] = useState("");
  const [currency, setCurrency] = useState("");
  const [simulate, setSimulate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  // Kept across attempts, so a retry after a dropped connection cannot create a second workflow.
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null);

  if (!can("workflow_submit")) {
    return (
      <>
        <PageHeader title="New workflow" />
        <ErrorState error="Your role can view workflows but not submit them." />
      </>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const context: Record<string, string> = {};
    if (customer.trim()) context.customer_reference = customer.trim();
    if (currency) context.currency = currency;
    if (simulate) context.simulate = simulate;
    const fingerprint = JSON.stringify({ request, context });
    if (attempt.current?.fingerprint !== fingerprint) {
      attempt.current = { fingerprint, key: crypto.randomUUID() };
    }
    try {
      const created = await apiPost<{ workflow_id: string }>("/workflows", {
        request,
        context,
        idempotency_key: attempt.current.key,
      });
      if (file) await apiUpload(`/workflows/${created.workflow_id}/attachments`, file);
      router.push(`/workflows/${created.workflow_id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", "That could not be submitted."));
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="New workflow" description="Say what you need in plain language. Anything sensitive will wait for approval before it runs." />
      <Card className="max-w-3xl">
        <CardBody>
          <form onSubmit={submit} className="grid gap-4">
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label htmlFor="request">Request</Label>
                <Button type="button" size="sm" variant="ghost" onClick={() => setRequest(DEMO_REQUEST)}>
                  Use the demo request
                </Button>
              </div>
              <Textarea
                id="request"
                required
                minLength={3}
                maxLength={4000}
                rows={5}
                value={request}
                onChange={(e) => setRequest(e.target.value)}
                placeholder="Prepare an invoice for Acme Ltd for 10 hours of consulting at ₹2,500 per hour and prepare an email."
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="customer">Customer (optional)</Label>
                <Input id="customer" value={customer} onChange={(e) => setCustomer(e.target.value)} placeholder="acme-ltd" />
              </div>
              <div>
                <Label htmlFor="currency">Currency (optional)</Label>
                <Select id="currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                  <option value="">From the request</option>
                  <option value="INR">INR</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                </Select>
              </div>
            </div>
            <div>
              <Label htmlFor="file">Supporting file (optional)</Label>
              <Input
                id="file"
                type="file"
                className="py-2"
                accept=".pdf,.png,.jpg,.jpeg,.csv,.txt"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <p className="mt-1 text-xs text-muted">PDF, PNG, JPEG, CSV or TXT, up to 5 MB. Stored for reviewers; never read by the AI.</p>
            </div>
            {me.fault_injection_enabled && (
              <div>
                <Label htmlFor="simulate">Simulate a failure (demo only)</Label>
                <Select id="simulate" value={simulate} onChange={(e) => setSimulate(e.target.value)}>
                  {SIMULATIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </Select>
              </div>
            )}
            {error && <ErrorState error={error} />}
            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={busy || request.trim().length < 3}>
                {busy ? "Submitting…" : "Submit"}
              </Button>
              <Button asChild variant="secondary">
                <Link href="/workflows">Cancel</Link>
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </>
  );
}
