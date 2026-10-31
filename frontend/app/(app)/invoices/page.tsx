"use client";

import Link from "next/link";
import { useState } from "react";
import { DownloadButton } from "@/components/ArtifactLinks";
import { PageHeader } from "@/components/AppShell";
import { Pager } from "@/components/Pager";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { StatusBadge } from "@/components/StatusBadge";
import { Card } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { formatDate, formatMoney } from "@/lib/utils";
import type { Invoice, Page } from "@/types/api";

const LIMIT = 20;

export default function InvoicesPage() {
  const [offset, setOffset] = useState(0);
  const { data, error, loading, reload } = useApi<Page<Invoice>>(`/invoices?limit=${LIMIT}&offset=${offset}`);
  return (
    <>
      <PageHeader title="Invoices" description="Drafts stay drafts until an approved workflow issues them." />
      <Card>
        {loading && <LoadingState />}
        {error && !data && (
          <div className="p-4">
            <ErrorState error={error} onRetry={reload} />
          </div>
        )}
        {data && data.items.length === 0 && <EmptyState title="No invoices yet">They appear here when a workflow creates one.</EmptyState>}
        {data && data.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Number</Th>
                  <Th>Customer</Th>
                  <Th className="text-right">Subtotal</Th>
                  <Th className="text-right">Tax</Th>
                  <Th className="text-right">Total</Th>
                  <Th>Status</Th>
                  <Th>Due</Th>
                  <Th>PDF</Th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((invoice) => (
                  <tr key={invoice.id}>
                    <Td className="whitespace-nowrap">
                      <Link href={`/workflows/${invoice.workflow_id}`} className="text-primary underline-offset-2 hover:underline">
                        {invoice.invoice_number}
                      </Link>
                    </Td>
                    <Td className="whitespace-nowrap">{invoice.customer_name}</Td>
                    <Td className="text-right whitespace-nowrap tabular-nums">{formatMoney(invoice.currency, invoice.subtotal)}</Td>
                    <Td className="text-right whitespace-nowrap tabular-nums">{formatMoney(invoice.currency, invoice.tax)}</Td>
                    <Td className="text-right font-medium whitespace-nowrap tabular-nums">{formatMoney(invoice.currency, invoice.total)}</Td>
                    <Td>
                      <StatusBadge status={invoice.status} />
                    </Td>
                    <Td className="whitespace-nowrap">{formatDate(invoice.due_date)}</Td>
                    <Td>
                      {invoice.artifact_id && (
                        <DownloadButton artifactId={invoice.artifact_id} filename={`${invoice.invoice_number}.pdf`} label="Download" />
                      )}
                    </Td>
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
