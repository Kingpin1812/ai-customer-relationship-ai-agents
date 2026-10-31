"use client";

import Link from "next/link";
import { DownloadButton } from "@/components/ArtifactLinks";
import { PageHeader } from "@/components/AppShell";
import { EmptyState, ErrorState, LoadingState } from "@/components/states";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Table, Td, Th } from "@/components/ui/table";
import { useApi } from "@/hooks/useApi";
import { formatDate, formatDateTime, formatMoney, humanize } from "@/lib/utils";
import type { Page, Report } from "@/types/api";

export default function ReportsPage() {
  const { data, error, loading, reload } = useApi<Page<Report>>("/reports?limit=50");
  return (
    <>
      <PageHeader title="Reports" description="Generated only from approved queries over your organization's records." />
      {loading && <LoadingState />}
      {error && !data && <ErrorState error={error} onRetry={reload} />}
      {data && data.items.length === 0 && (
        <Card>
          <EmptyState title="No reports yet">Ask for one in a workflow, for example: generate this month&apos;s sales summary.</EmptyState>
        </Card>
      )}
      <div className="grid grid-cols-1 gap-6">
        {data?.items.map((report) => (
          <Card key={report.id}>
            <CardHeader title={humanize(report.report_type)} />
            <CardBody className="grid gap-1 text-sm text-muted">
              <p>
                Period: {formatDate(report.period_start)} to {formatDate(report.period_end)}
              </p>
              <p>Generated: {formatDateTime(report.generated_at)}</p>
              <p>Source: {report.source.query}</p>
              <p>
                <Link href={`/workflows/${report.workflow_id}`} className="text-primary underline">
                  Open workflow
                </Link>
              </p>
            </CardBody>
            <Table>
              <thead>
                <tr>
                  <Th>Customer</Th>
                  <Th className="text-right">Sales</Th>
                  <Th className="text-right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {report.summary.rows.map((row) => (
                  <tr key={`${row.customer_name}-${row.currency}`}>
                    <Td>{row.customer_name}</Td>
                    <Td className="text-right tabular-nums">{row.sales_count}</Td>
                    <Td className="text-right tabular-nums">{formatMoney(row.currency, row.amount)}</Td>
                  </tr>
                ))}
                <tr>
                  <Td className="font-semibold">Total</Td>
                  <Td />
                  <Td className="text-right font-semibold tabular-nums">{formatMoney(report.summary.rows[0]?.currency, report.summary.total)}</Td>
                </tr>
              </tbody>
            </Table>
            <CardBody className="flex flex-wrap gap-2">
              {report.pdf_artifact_id && <DownloadButton artifactId={report.pdf_artifact_id} filename={`${report.report_type}.pdf`} label="Download PDF" />}
              {report.csv_artifact_id && <DownloadButton artifactId={report.csv_artifact_id} filename={`${report.report_type}.csv`} label="Download CSV" />}
            </CardBody>
          </Card>
        ))}
      </div>
    </>
  );
}
