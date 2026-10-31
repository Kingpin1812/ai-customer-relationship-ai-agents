"use client";

import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Pager } from "@/components/Pager";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Card } from "@/components/ui/card";
import { Label, Select } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, formatMoney, humanize } from "@/lib/utils";
import type { Approval, ApprovalStatus, Page } from "@/types/api";

const STATUSES: ApprovalStatus[] = ["pending", "approved", "rejected", "changes_requested", "expired"];
const LIMIT = 20;

export default function ApprovalsPage() {
  const [status, setStatus] = useState<string>("pending");
  const [offset, setOffset] = useState(0);
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (status) params.set("status", status);
  const { data, error, loading, reload } = useApi<Page<Approval>>(`/approvals?${params}`, {
    pollMs: () => 4000,
  });

  return (
    <>
      <PageHeader title="Approvals" description="Sensitive actions stay paused here until an authorized person decides." />
      <div className="mb-4 max-w-xs">
        <Label htmlFor="status">Status</Label>
        <Select
          id="status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
        >
          <option value="">All</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {humanize(s)}
            </option>
          ))}
        </Select>
      </div>
      <Card>
        {loading && <LoadingState />}
        {error && !data && (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        )}
        {data && data.items.length === 0 && <EmptyState title={status === "pending" ? "Nothing is waiting for approval" : "No approvals here"} />}
        {data && data.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Action</Th>
                  <Th>Amount</Th>
                  <Th>Recipient</Th>
                  <Th>Requested by</Th>
                  <Th>Status</Th>
                  <Th>Requested</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((approval) => (
                  <tr key={approval.id}>
                    <Td className="min-w-64">
                      <Link href={`/approvals/${approval.id}`} className="text-primary underline-offset-2 hover:underline">
                        {approval.summary}
                      </Link>
                    </Td>
                    <Td className="whitespace-nowrap tabular-nums">{formatMoney(approval.currency, approval.amount)}</Td>
                    <Td className="whitespace-nowrap">{approval.recipient ?? "—"}</Td>
                    <Td className="whitespace-nowrap">{approval.requested_by_email}</Td>
                    <Td>
                      <StatusBadge status={approval.status} />
                    </Td>
                    <Td className="whitespace-nowrap">{formatDateTime(approval.created_at)}</Td>
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
