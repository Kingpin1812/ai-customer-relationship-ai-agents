"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorState, LoadingState } from "@/components/states";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { useCan, useSession } from "@/hooks/useSession";
import { ApiError, apiPatch } from "@/lib/api";
import type { Member } from "@/types/api";

const ROLES: Member["role"][] = ["admin", "manager", "operator", "viewer"];

export default function SettingsPage() {
  const can = useCan();
  const me = useSession();
  const allowed = can("user_manage");
  const { data, error, loading, reload } = useApi<{ items: Member[] }>(allowed ? "/members" : null);
  const [problem, setProblem] = useState<ApiError | null>(null);

  if (!allowed) {
    return (
      <>
        <PageHeader title="Settings" />
        <ErrorState error="Only administrators can change organization settings." />
      </>
    );
  }

  const changeRole = async (userId: string, role: string) => {
    setProblem(null);
    try {
      await apiPatch(`/members/${userId}`, { role });
    } catch (e) {
      setProblem(e instanceof ApiError ? e : new ApiError(0, "unknown", "That did not work."));
    }
    await reload();
  };

  return (
    <>
      <PageHeader title="Settings" description={me.organization_name} />
      <div className="grid grid-cols-1 gap-6">
        {problem && <ErrorState error={problem} />}
        <Card>
          <CardHeader title="Users and roles" />
          {loading && <LoadingState />}
          {error && !data && (
            <div className="p-4">
              <ErrorState error={error} onRetry={reload} />
            </div>
          )}
          {data && (
            <Table>
              <thead>
                <tr>
                  <Th>Name</Th>
                  <Th>Email</Th>
                  <Th>Status</Th>
                  <Th>Role</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((member) => (
                  <tr key={member.user_id}>
                    <Td className="whitespace-nowrap">{member.display_name}</Td>
                    <Td className="whitespace-nowrap">{member.email}</Td>
                    <Td>{member.status}</Td>
                    <Td>
                      <Select
                        aria-label={`Role for ${member.display_name}`}
                        className="h-8 w-32"
                        value={member.role}
                        onChange={(e) => changeRole(member.user_id, e.target.value)}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </Select>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <Card>
          <CardHeader title="Workflow policy" />
          <CardBody className="grid gap-1 text-sm text-muted">
            <p>Sending email, issuing invoices and CRM updates always need approval.</p>
            <p>Approval expiry, tax rate and payment terms are set in server configuration (see run.md).</p>
            <p>Retention: no automatic deletion is configured in this demo.</p>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
