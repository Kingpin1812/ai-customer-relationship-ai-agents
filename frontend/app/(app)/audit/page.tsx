"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Pager } from "@/components/Pager";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Card } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { formatDateTime } from "@/lib/utils";
import type { AuditEvent, Page } from "@/types/api";

const LIMIT = 50;
const UUID = /^[0-9a-f-]{36}$/i;

function AuditList() {
  const [workflowId, setWorkflowId] = useState(useSearchParams().get("workflow_id") ?? "");
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);

  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (UUID.test(workflowId.trim())) params.set("workflow_id", workflowId.trim());
  if (actor.trim()) params.set("actor_email", actor.trim());
  if (action.trim()) params.set("action", action.trim());
  if (dateFrom) params.set("date_from", dateFrom);
  if (dateTo) params.set("date_to", dateTo);

  const { data, error, loading, reload } = useApi<Page<AuditEvent>>(`/audit?${params}`);
  const change = (setter: (value: string) => void) => (event: { target: { value: string } }) => {
    setter(event.target.value);
    setOffset(0);
  };

  return (
    <>
      <PageHeader title="Audit log" description="Append-only. Nothing here can be edited or removed by the application." />
      <form className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5" role="search" onSubmit={(e) => e.preventDefault()}>
        <div>
          <Label htmlFor="actor">Actor email</Label>
          <Input id="actor" value={actor} onChange={change(setActor)} placeholder="manager@demo.test" />
        </div>
        <div>
          <Label htmlFor="action">Action</Label>
          <Input id="action" value={action} onChange={change(setAction)} placeholder="approval.approved" />
        </div>
        <div>
          <Label htmlFor="workflow">Workflow ID</Label>
          <Input id="workflow" value={workflowId} onChange={change(setWorkflowId)} />
        </div>
        <div>
          <Label htmlFor="from">From</Label>
          <Input id="from" type="date" value={dateFrom} onChange={change(setDateFrom)} />
        </div>
        <div>
          <Label htmlFor="to">To</Label>
          <Input id="to" type="date" value={dateTo} onChange={change(setDateTo)} />
        </div>
      </form>
      <Card>
        {loading && <LoadingState />}
        {error && !data && (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        )}
        {data && data.items.length === 0 && <EmptyState title="No events match" />}
        {data && data.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Time</Th>
                  <Th>Actor</Th>
                  <Th>Action</Th>
                  <Th>Target</Th>
                  <Th>Workflow</Th>
                  <Th>Result</Th>
                  <Th>Correlation ID</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((event) => (
                  <tr key={event.id}>
                    <Td className="whitespace-nowrap">{formatDateTime(event.created_at)}</Td>
                    <Td className="whitespace-nowrap">{event.actor_email ?? "System"}</Td>
                    <Td className="font-mono text-xs whitespace-nowrap">{event.action}</Td>
                    <Td className="max-w-56 font-mono text-xs break-all">{event.target}</Td>
                    <Td className="font-mono text-xs">
                      {event.workflow_id ? (
                        <Link href={`/workflows/${event.workflow_id}`} className="text-primary underline">
                          {event.workflow_id.slice(0, 8)}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </Td>
                    <Td>
                      <StatusBadge status={event.result} />
                    </Td>
                    <Td className="font-mono text-xs">{event.correlation_id?.slice(0, 12) ?? "—"}</Td>
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

export default function AuditPage() {
  return (
    <Suspense>
      <AuditList />
    </Suspense>
  );
}
