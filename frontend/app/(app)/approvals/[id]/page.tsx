"use client";

import { Mail, NotebookPen, ReceiptText } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { DownloadButton } from "@/components/ArtifactLinks";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/form";
import { useApi } from "@/hooks/useApi";
import { useCan } from "@/hooks/useSession";
import { ApiError, apiPost, fetchArtifactBlob } from "@/lib/api";
import { formatDate, formatDateTime, formatMoney } from "@/lib/utils";
import type { Approval, ApprovalAction } from "@/types/api";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[8rem_1fr] sm:gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

function PdfPreview({ artifactId, title }: { artifactId: string; title: string }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let revoked = false;
    let objectUrl: string | null = null;
    fetchArtifactBlob(artifactId).then(
      (blob) => {
        if (revoked) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      },
      () => setFailed(true),
    );
    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [artifactId]);

  if (failed) return <p className="text-sm text-danger">The preview could not be loaded. Try downloading the file.</p>;
  if (!url) return <LoadingState label="Loading preview" />;
  return <iframe src={url} title={title} className="h-96 w-full rounded-md border border-border bg-white" />;
}

function ActionCard({ action }: { action: ApprovalAction }) {
  if (action.type === "issue_invoice") {
    return (
      <Card>
        <CardHeader title="Issue invoice" action={<ReceiptText className="size-4 text-muted" aria-hidden />} />
        <CardBody className="grid gap-4 text-sm">
          <dl className="grid gap-2">
            <Row label="Number">{action.invoice_number}</Row>
            <Row label="Subtotal">{formatMoney(action.currency, action.subtotal)}</Row>
            <Row label="Tax">{formatMoney(action.currency, action.tax)}</Row>
            <Row label="Total">
              <strong className="text-base">{formatMoney(action.currency, action.total)}</strong>
            </Row>
            <Row label="Due">{formatDate(action.due_date)}</Row>
          </dl>
          {action.artifact && (
            <>
              <PdfPreview artifactId={action.artifact.artifact_id} title={`Preview of ${action.artifact.filename}`} />
              <div>
                <DownloadButton artifactId={action.artifact.artifact_id} filename={action.artifact.filename} />
                <p className="mt-1 font-mono text-xs break-all text-muted">SHA-256 {action.artifact.checksum}</p>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    );
  }
  if (action.type === "update_crm_note") {
    return (
      <Card>
        <CardHeader title="Update CRM record" action={<NotebookPen className="size-4 text-muted" aria-hidden />} />
        <CardBody>
          <dl className="grid gap-2 text-sm">
            <Row label="Record">{action.provider_customer_id}</Row>
            <Row label="Note to add">{action.note}</Row>
          </dl>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader title="Send email" action={<Mail className="size-4 text-muted" aria-hidden />} />
      <CardBody>
        <dl className="grid gap-2 text-sm">
          <Row label="To">
            <strong>{action.to}</strong>
          </Row>
          <Row label="Subject">{action.subject}</Row>
          <Row label="Message">
            <p className="rounded-md bg-surface-muted p-3 whitespace-pre-wrap">{action.body}</p>
          </Row>
          <Row label="Attachments">{action.attachments.map((a) => a.filename).join(", ") || "None"}</Row>
        </dl>
      </CardBody>
    </Card>
  );
}

export default function ApprovalDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const can = useCan();
  const { data: approval, error, loading, reload } = useApi<Approval>(`/approvals/${id}`);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<ApiError | null>(null);
  const [replacement, setReplacement] = useState<string | null>(null);

  if (loading) return <LoadingState label="Loading approval" />;
  if (error && !approval) return <ErrorState error={error} onRetry={reload} />;
  if (!approval) return null;

  const decide = async (decision: "approve" | "reject" | "request_changes") => {
    setBusy(true);
    setProblem(null);
    try {
      await apiPost(`/approvals/${id}/decision`, { decision, reason: reason.trim() || undefined });
      router.push(`/workflows/${approval.workflow_id}`);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "unknown", "That did not work.");
      setProblem(err);
      const details = err.details as { new_approval_id?: string } | null;
      setReplacement(details?.new_approval_id ?? null);
      await reload();
      setBusy(false);
    }
  };

  const decidable = approval.status === "pending" && can("approve");

  return (
    <>
      <PageHeader
        title="Review this action"
        description={`Requested by ${approval.requested_by_email} · ${formatDateTime(approval.created_at)}`}
        action={<StatusBadge status={approval.status} className="text-sm" />}
      />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="grid min-w-0 grid-cols-1 content-start gap-6">
          <Card>
            <CardHeader title="What approving will do" />
            <CardBody className="grid gap-2 text-sm">
              <p className="text-base font-medium break-words">{approval.summary}</p>
              <p className="text-muted">
                Customer: {approval.payload.customer.name} ({approval.payload.customer.provider_customer_id}). Exactly what is shown below will run, nothing else. If anything changes first, this approval stops working and a new one is created.
              </p>
            </CardBody>
          </Card>
          {approval.payload.actions.map((action) => (
            <ActionCard key={action.type} action={action} />
          ))}
        </div>

        <aside className="grid grid-cols-1 content-start gap-6 lg:sticky lg:top-6">
          <Card>
            <CardHeader title="Decision" />
            <CardBody className="grid gap-3 text-sm">
              {problem && <ErrorState error={problem} />}
              {replacement && (
                <Button asChild variant="secondary">
                  <Link href={`/approvals/${replacement}`}>Review the new request</Link>
                </Button>
              )}
              {decidable ? (
                <>
                  <div>
                    <Label htmlFor="reason">Reason (required to reject or request changes)</Label>
                    <Textarea id="reason" maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
                  </div>
                  <Button disabled={busy} onClick={() => decide("approve")}>
                    Approve and run
                  </Button>
                  <Button variant="secondary" disabled={busy || !reason.trim()} onClick={() => decide("request_changes")}>
                    Request changes
                  </Button>
                  <Button variant="danger" disabled={busy || !reason.trim()} onClick={() => decide("reject")}>
                    Reject
                  </Button>
                  <p className="text-xs text-muted">Expires {formatDateTime(approval.expires_at)}</p>
                </>
              ) : approval.status === "pending" ? (
                <p data-testid="no-approve-permission" className="text-muted">
                  Waiting for a manager. Your role cannot approve this.
                </p>
              ) : (
                <div className="grid gap-1">
                  <p>
                    Decided by {approval.decided_by_email ?? "the system"}
                    {approval.decided_at ? ` on ${formatDateTime(approval.decided_at)}` : ""}.
                  </p>
                  {approval.reason && <p>Reason: {approval.reason}</p>}
                  {approval.invalidation_reason && <p className="text-gate">Stopped because {approval.invalidation_reason}.</p>}
                </div>
              )}
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Approval fingerprint" />
            <CardBody className="text-xs text-muted">
              <code className="font-mono break-all">{approval.payload_hash}</code>
              <p className="mt-2">This SHA-256 covers the exact action above. It is checked again immediately before anything runs.</p>
              <Link className="mt-2 inline-block text-primary underline" href={`/workflows/${approval.workflow_id}`}>
                Open the workflow
              </Link>
            </CardBody>
          </Card>
        </aside>
      </div>
    </>
  );
}
