"use client";

import { PageHeader } from "@/components/AppShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardBody } from "@/components/ui/card";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";
import type { Page, SandboxEmail } from "@/types/api";

export default function OutboxPage() {
  const { data, error, loading, reload } = useApi<Page<SandboxEmail>>("/sandbox/emails?limit=50", {
    pollMs: () => 4000,
  });
  return (
    <>
      <PageHeader
        title="Sandbox outbox"
        description={
          data
            ? `The mock mail provider has received ${data.total} ${data.total === 1 ? "message" : "messages"}. No real email is ever sent.`
            : "What the mock mail provider received. No real email is ever sent."
        }
      />
      {loading && <LoadingState />}
      {error && !data && <ErrorState error={error} onRetry={reload} />}
      {data && data.items.length === 0 && (
        <Card>
          <EmptyState title="Nothing sent yet">Messages appear here only after someone approves them.</EmptyState>
        </Card>
      )}
      <ul className="grid gap-4" data-testid="outbox">
        {data?.items.map((email) => (
          <li key={email.provider_message_id}>
            <Card>
              <CardBody className="grid gap-1 text-sm">
                <p>
                  <span className="text-muted">To: </span>
                  <strong>{email.recipient}</strong>
                </p>
                <p>
                  <span className="text-muted">Subject: </span>
                  {email.subject}
                </p>
                <p className="text-xs text-muted">{formatDateTime(email.sent_at)}</p>
                <p className="mt-2 rounded-md bg-surface-muted p-3 whitespace-pre-wrap">{email.body}</p>
                <p className="text-xs text-muted">Attachments: {email.attachments.map((a) => a.filename).join(", ") || "None"}</p>
              </CardBody>
            </Card>
          </li>
        ))}
      </ul>
    </>
  );
}
