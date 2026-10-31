"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Pager } from "@/components/Pager";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { useCan } from "@/hooks/useSession";
import { formatDateTime, formatDuration, humanize } from "@/lib/utils";
import type { Page, WorkflowStatus, WorkflowSummary } from "@/types/api";

const STATUSES: WorkflowStatus[] = [
  "queued",
  "running",
  "waiting_for_approval",
  "succeeded",
  "failed",
  "rejected",
  "cancelled",
];
const LIMIT = 20;

function WorkflowList() {
  const can = useCan();
  const initial = useSearchParams().get("status") ?? "";
  const [status, setStatus] = useState(initial);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (status) params.set("status", status);
  if (search.trim()) params.set("q", search.trim());
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);

  const { data, error, loading, reload } = useApi<Page<WorkflowSummary>>(`/workflows?${params}`, {
    pollMs: () => 4000,
  });
  const change = <T,>(setter: (value: T) => void) => (value: T) => {
    setter(value);
    setOffset(0);
  };

  return (
    <>
      <PageHeader
        title="Workflows"
        description="Every request, who made it, and where it is now."
        action={
          can("workflow_submit") && (
            <Button asChild>
              <Link href="/workflows/new">
                <Plus aria-hidden />
                New workflow
              </Link>
            </Button>
          )
        }
      />
      <form className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4" role="search" onSubmit={(e) => e.preventDefault()}>
        <div>
          <Label htmlFor="q">Search requests</Label>
          <Input id="q" value={search} onChange={(e) => change(setSearch)(e.target.value)} placeholder="Acme, invoice…" />
        </div>
        <div>
          <Label htmlFor="status">Status</Label>
          <Select id="status" value={status} onChange={(e) => change(setStatus)(e.target.value)}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {humanize(s)}
              </option>
            ))}
          </Select>
        </div>
        <div>
          <Label htmlFor="from">From</Label>
          <Input id="from" type="date" value={dateFrom} onChange={(e) => change(setDateFrom)(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="to">To</Label>
          <Input id="to" type="date" value={dateTo} onChange={(e) => change(setDateTo)(e.target.value)} />
        </div>
      </form>
      <Card>
        {loading && <LoadingState />}
        {error && !data && (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        )}
        {data && data.items.length === 0 && (
          <EmptyState title="No workflows match">Try different filters, or submit a new request.</EmptyState>
        )}
        {data && data.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Request</Th>
                  <Th>Status</Th>
                  <Th>Creator</Th>
                  <Th>Created</Th>
                  <Th>Duration</Th>
                  <Th>ID</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((workflow) => (
                  <tr key={workflow.id}>
                    <Td className="min-w-64">
                      <Link href={`/workflows/${workflow.id}`} className="text-primary underline-offset-2 hover:underline">
                        {workflow.request_summary}
                      </Link>
                      {workflow.needs_clarification && <span className="mt-1 block text-xs text-gate">Needs clarification</span>}
                    </Td>
                    <Td>
                      <StatusBadge status={workflow.status} />
                    </Td>
                    <Td className="whitespace-nowrap">{workflow.creator_email}</Td>
                    <Td className="whitespace-nowrap">{formatDateTime(workflow.created_at)}</Td>
                    <Td>{formatDuration(workflow.duration_seconds)}</Td>
                    <Td className="font-mono text-xs">{workflow.id.slice(0, 8)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <Pager total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </Card>
    </>
  );
}

export default function WorkflowsPage() {
  return (
    <Suspense>
      <WorkflowList />
    </Suspense>
  );
}
