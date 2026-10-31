"use client";

import { Check, CircleDashed, Hand, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { DownloadButton } from "@/components/ArtifactLinks";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { LazyWorkflowScene } from "@/components/three/lazy";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { useCan, useSession } from "@/hooks/useSession";
import { ApiError, apiPost } from "@/lib/api";
import { formatBytes, formatDateTime, formatMoney, humanize } from "@/lib/utils";
import type { Plan, WorkflowDetail } from "@/types/api";

const ACTIVE = ["queued", "running"];

function PlanView({ plan, source }: { plan: Plan; source: string | null }) {
  return (
    <div className="grid gap-3 text-sm">
      <p className="flex flex-wrap gap-2">
        {plan.actions.map((action) => (
          <span key={action} className="rounded-full bg-surface-muted px-2.5 py-0.5 text-xs">
            {humanize(action)}
          </span>
        ))}
      </p>
      {plan.customer_reference && (
        <p>
          <span className="text-muted">Customer: </span>
          {plan.customer_reference}
        </p>
      )}
      {plan.line_items.map((item, index) => (
        <p key={index}>
          <span className="text-muted">Line item: </span>
          {item.quantity} × {formatMoney(plan.currency, item.unit_price)} — {item.description}
        </p>
      ))}
      {plan.report && (
        <p>
          <span className="text-muted">Report: </span>
          {humanize(plan.report.type)} ({humanize(plan.report.period)})
        </p>
      )}
      <p className="text-xs text-muted">Planned by: {humanize(source ?? "unknown")}. Totals, recipients and permissions never come from the planner.</p>
    </div>
  );
}

function StepIcon({ status }: { status: string }) {
  if (status === "succeeded") return <Check className="size-4 text-success" aria-hidden />;
  if (status === "failed") return <X className="size-4 text-danger" aria-hidden />;
  return <CircleDashed className="size-4 text-muted" aria-hidden />;
}

export default function WorkflowDetailPage() {
  const { id } = useParams<{ id: string }>();
  const can = useCan();
  const me = useSession();
  const [actionError, setActionError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const { data: workflow, error, loading, reload } = useApi<WorkflowDetail>(`/workflows/${id}`, {
    pollMs: (w) => (w && !["succeeded", "rejected", "cancelled", "failed"].includes(w.status) ? 1500 : 0),
  });

  const act = async (path: string) => {
    setBusy(true);
    setActionError(null);
    try {
      await apiPost(path);
      await reload();
    } catch (e) {
      setActionError(e instanceof ApiError ? e : new ApiError(0, "unknown", "That did not work."));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Loading workflow" />;
  if (error && !workflow) return <ErrorState error={error} onRetry={reload} />;
  if (!workflow) return null;

  const pending = workflow.approvals.find((a) => a.status === "pending");
  const mayControl = can("retry_any") || (can("retry_own") && workflow.creator_email === me.email);
  const invoiceArtifacts = workflow.artifacts;

  return (
    <>
      <PageHeader
        title="Workflow"
        description={`Submitted by ${workflow.creator_email} · ${formatDateTime(workflow.created_at)}`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={workflow.status} className="text-sm" />
            {workflow.can_retry && mayControl && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => act(`/workflows/${id}/retry`)}>
                <RefreshCw aria-hidden />
                Retry
              </Button>
            )}
            {workflow.can_cancel && mayControl && (
              <Button size="sm" variant="secondary" disabled={busy} onClick={() => act(`/workflows/${id}/cancel`)}>
                Cancel
              </Button>
            )}
          </div>
        }
      />
      <div className="grid grid-cols-1 gap-6">
        {actionError && <ErrorState error={actionError} />}

        {ACTIVE.includes(workflow.status) && (
          <p role="status" className="rounded-md bg-info-soft p-3 text-sm text-info">
            Working on this now. This page updates by itself.
          </p>
        )}

        {pending && (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-gate/50 bg-gate-soft p-4 text-sm">
            <p className="min-w-0 text-gate">
              <Hand className="mr-2 inline size-4" aria-hidden />
              <strong>Nothing external happens until someone approves.</strong> {pending.summary}
            </p>
            <Button asChild size="sm">
              <Link href={`/approvals/${pending.id}`}>{can("approve") ? "Review and decide" : "View request"}</Link>
            </Button>
          </div>
        )}

        {workflow.error_message && (
          <div
            role="alert"
            className={
              workflow.status === "failed"
                ? "rounded-lg border border-danger/40 bg-danger-soft p-4 text-sm text-danger"
                : "rounded-lg border border-border bg-surface-muted p-4 text-sm"
            }
          >
            <p className="font-medium">
              {workflow.needs_clarification ? "More information needed" : workflow.status === "failed" ? "This workflow stopped" : "Decision"}
            </p>
            <p className="mt-1">{workflow.error_message}</p>
            {workflow.needs_clarification && (
              <Link className="mt-2 inline-block underline" href="/workflows/new">
                Submit a corrected request
              </Link>
            )}
          </div>
        )}

        <LazyWorkflowScene workflow={workflow} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Request" />
            <CardBody className="text-sm break-words whitespace-pre-wrap">{workflow.request_text}</CardBody>
          </Card>
          <Card>
            <CardHeader title="Interpreted plan" />
            <CardBody>
              {workflow.plan ? <PlanView plan={workflow.plan} source={workflow.planner_source} /> : <p className="text-sm text-muted">Not planned yet.</p>}
            </CardBody>
          </Card>
        </div>

        <Card>
          <CardHeader title="Step timeline" />
          {workflow.steps.length === 0 ? (
            <CardBody className="text-sm text-muted">No steps have started yet.</CardBody>
          ) : (
            <ol className="divide-y divide-border" data-testid="timeline">
              {workflow.steps.map((step) => (
                <li key={step.step_key} className="flex gap-3 px-4 py-3 text-sm">
                  <StepIcon status={step.status} />
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {humanize(step.step_key)}
                      <StatusBadge status={step.status} />
                      {step.runs > 1 && <span className="text-xs font-normal text-muted">ran {step.runs} times</span>}
                    </p>
                    {step.output_summary && <p className="mt-0.5 break-words text-muted">{step.output_summary}</p>}
                    {step.error && <p className="mt-0.5 break-words text-danger">{step.error}</p>}
                    <p className="mt-0.5 text-xs text-muted">{formatDateTime(step.started_at)}</p>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Artifacts" />
            {invoiceArtifacts.length === 0 ? (
              <CardBody className="text-sm text-muted">Nothing generated yet.</CardBody>
            ) : (
              <ul className="divide-y divide-border">
                {invoiceArtifacts.map((artifact) => (
                  <li key={artifact.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                    <span className="min-w-0">
                      <span className="block break-all">{artifact.filename}</span>
                      <span className="text-xs text-muted">
                        {humanize(artifact.kind)} · {formatBytes(artifact.size_bytes)}
                      </span>
                    </span>
                    <DownloadButton artifactId={artifact.id} filename={artifact.filename} label="Download" />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card>
            <CardHeader title="Approvals" />
            {workflow.approvals.length === 0 ? (
              <CardBody className="text-sm text-muted">No approval requested.</CardBody>
            ) : (
              <ul className="divide-y divide-border">
                {workflow.approvals.map((approval) => (
                  <li key={approval.id} className="px-4 py-3 text-sm">
                    <p className="flex flex-wrap items-center justify-between gap-2">
                      <Link href={`/approvals/${approval.id}`} className="text-primary underline">
                        {formatDateTime(approval.created_at)}
                      </Link>
                      <StatusBadge status={approval.status} />
                    </p>
                    <p className="mt-1 break-words text-muted">{approval.summary}</p>
                    {approval.reason && <p className="mt-1">Reason: {approval.reason}</p>}
                    {approval.invalidation_reason && <p className="mt-1 text-gate">Replaced because {approval.invalidation_reason}.</p>}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        {workflow.email_draft && (
          <Card>
            <CardHeader title="Email" action={<StatusBadge status={workflow.email_draft.status} />} />
            <CardBody className="grid gap-1 text-sm">
              <p>
                <span className="text-muted">To: </span>
                {workflow.email_draft.recipient}
              </p>
              <p>
                <span className="text-muted">Subject: </span>
                {workflow.email_draft.subject}
              </p>
              <p className="mt-2 rounded-md bg-surface-muted p-3 whitespace-pre-wrap">{workflow.email_draft.body}</p>
              {workflow.email_draft.provider_message_id && (
                <p className="mt-1 font-mono text-xs break-all text-muted">Provider message ID: {workflow.email_draft.provider_message_id}</p>
              )}
            </CardBody>
          </Card>
        )}

        <Card>
          <CardHeader title="Integration attempts and retries" />
          {workflow.operations.length === 0 ? (
            <CardBody className="text-sm text-muted">No external calls yet.</CardBody>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Operation</Th>
                  <Th>Provider</Th>
                  <Th>Status</Th>
                  <Th>Attempts</Th>
                  <Th>Last problem</Th>
                </tr>
              </thead>
              <tbody>
                {workflow.operations.map((operation) => (
                  <tr key={`${operation.provider}-${operation.operation}`}>
                    <Td>{humanize(operation.operation)}</Td>
                    <Td>{humanize(operation.provider)}</Td>
                    <Td>
                      <StatusBadge status={operation.status} />
                    </Td>
                    <Td className="tabular-nums">{operation.attempt_count}</Td>
                    <Td className="text-muted">{operation.last_error ?? "—"}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>

        <Card>
          <CardHeader title="Tracing" />
          <CardBody className="grid gap-1 text-sm">
            <p>
              <span className="text-muted">Trace ID: </span>
              <code className="font-mono text-xs break-all">{workflow.trace_id ?? "—"}</code>
            </p>
            <p>
              <span className="text-muted">Correlation ID: </span>
              <code className="font-mono text-xs break-all">{workflow.correlation_id ?? "—"}</code>
            </p>
            <p>
              <span className="text-muted">Workflow ID: </span>
              <code className="font-mono text-xs break-all">{workflow.id}</code>
            </p>
            <Link className="mt-1 text-primary underline" href={`/audit?workflow_id=${workflow.id}`}>
              See the full audit trail
            </Link>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
