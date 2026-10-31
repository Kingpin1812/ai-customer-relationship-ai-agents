"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { useCan, useSession } from "@/hooks/useSession";
import { ApiError, apiPost } from "@/lib/api";
import { formatDateTime, humanize } from "@/lib/utils";
import type { Integration, Page } from "@/types/api";

export default function IntegrationsPage() {
  const can = useCan();
  const me = useSession();
  const { data, error, loading, reload } = useApi<Page<Integration>>("/integrations");
  const [problem, setProblem] = useState<ApiError | null>(null);

  const change = async (provider: string, action: "connect" | "disconnect") => {
    setProblem(null);
    try {
      await apiPost(`/integrations/${provider}/${action}`);
      await reload();
    } catch (e) {
      setProblem(e instanceof ApiError ? e : new ApiError(0, "unknown", "That did not work."));
    }
  };

  return (
    <>
      <PageHeader title="Integrations" description="Connections to outside systems. These demo providers are mocks; nothing leaves this machine." />
      {problem && (
        <div className="mb-4">
          <ErrorState error={problem} />
        </div>
      )}
      <Card>
        {loading && <LoadingState />}
        {error && !data && (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        )}
        {data && data.items.length === 0 && <EmptyState title="No integrations configured" />}
        {data && data.items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th>Provider</Th>
                <Th>Status</Th>
                <Th>Organization</Th>
                <Th>Scopes</Th>
                <Th>Last success</Th>
                {can("integration_configure") && <Th>Action</Th>}
              </tr>
            </thead>
            <tbody>
              {data.items.map((integration) => (
                <tr key={integration.id}>
                  <Td className="whitespace-nowrap">{humanize(integration.provider)}</Td>
                  <Td>
                    <StatusBadge status={integration.status} />
                  </Td>
                  <Td className="whitespace-nowrap">{me.organization_name}</Td>
                  <Td className="font-mono text-xs">{integration.scopes.join(", ")}</Td>
                  <Td className="whitespace-nowrap">{formatDateTime(integration.last_success_at)}</Td>
                  {can("integration_configure") && (
                    <Td>
                      {integration.status === "connected" ? (
                        <Button size="sm" variant="secondary" onClick={() => change(integration.provider, "disconnect")}>
                          Disconnect
                        </Button>
                      ) : (
                        <Button size="sm" onClick={() => change(integration.provider, "connect")}>
                          Reconnect
                        </Button>
                      )}
                    </Td>
                  )}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
