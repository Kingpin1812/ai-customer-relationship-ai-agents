"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { LazySystemScene } from "@/components/three/lazy";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useApi } from "@/hooks/useApi";
import { useCan } from "@/hooks/useSession";
import { formatDateTime, humanize } from "@/lib/utils";
import type { DashboardSummary } from "@/types/api";

function Stat({ label, value, href }: { label: string; value: number; href: string }) {
  return (
    <Link href={href} className="rounded-lg border border-border bg-surface p-4 hover:border-primary">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </Link>
  );
}

export default function DashboardPage() {
  const can = useCan();
  const { data, error, loading, reload } = useApi<DashboardSummary>("/dashboard/summary", {
    pollMs: () => 5000,
  });

  const newButton = can("workflow_submit") && (
    <Button asChild>
      <Link href="/workflows/new">
        <Plus aria-hidden />
        New workflow
      </Link>
    </Button>
  );

  return (
    <>
      <PageHeader title="Overview" description="Everything running, and what is waiting for a person." action={newButton} />
      {loading && <LoadingState />}
      {error && !data && <ErrorState error={error} onRetry={reload} />}
      {data && (
        <div className="grid grid-cols-1 gap-6">
          <LazySystemScene summary={data} />
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            <Stat label="Total workflows" value={data.total} href="/workflows" />
            <Stat label="Running" value={data.by_status.running + data.by_status.queued} href="/workflows?status=running" />
            <Stat label="Succeeded" value={data.by_status.succeeded} href="/workflows?status=succeeded" />
            <Stat label="Failed" value={data.by_status.failed} href="/workflows?status=failed" />
            <Stat label="Pending approvals" value={data.pending_approvals} href="/approvals" />
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader title="Recent activity" />
              {data.recent_activity.length === 0 ? (
                <EmptyState title="No activity yet">Submit a workflow to see it here.</EmptyState>
              ) : (
                <ul className="divide-y divide-border">
                  {data.recent_activity.map((event, index) => (
                    <li key={`${event.created_at}-${index}`} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                      <span className="min-w-0">
                        <span className="font-medium">{humanize(event.action)}</span>
                        <span className="block truncate text-xs text-muted">
                          {event.actor_email ?? "System"} · {formatDateTime(event.created_at)}
                        </span>
                      </span>
                      {event.workflow_id && (
                        <Link className="text-xs text-primary underline" href={`/workflows/${event.workflow_id}`}>
                          Open workflow
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <div className="grid grid-cols-1 content-start gap-6">
              <Card>
                <CardHeader title="Integration health" />
                <ul className="divide-y divide-border">
                  {data.integrations.map((integration) => (
                    <li key={integration.provider} className="flex items-center justify-between gap-2 px-4 py-3 text-sm">
                      <span>
                        {humanize(integration.provider)}
                        <span className="block text-xs text-muted">
                          Last success: {formatDateTime(integration.last_success_at)}
                        </span>
                      </span>
                      <StatusBadge status={integration.status} />
                    </li>
                  ))}
                </ul>
              </Card>
              <Card>
                <CardHeader title="Last 7 days" />
                <CardBody className="p-0">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-muted">
                        <th scope="col" className="px-4 py-2 font-medium">Day</th>
                        <th scope="col" className="px-4 py-2 text-right font-medium">Succeeded</th>
                        <th scope="col" className="px-4 py-2 text-right font-medium">Failed</th>
                      </tr>
                    </thead>
                    <tbody className="tabular-nums">
                      {data.trend.map((day) => (
                        <tr key={day.day} className="border-t border-border">
                          <td className="px-4 py-1.5">{day.day.slice(5)}</td>
                          <td className="px-4 py-1.5 text-right">{day.succeeded}</td>
                          <td className="px-4 py-1.5 text-right">{day.failed}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardBody>
              </Card>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
