import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-muted">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}…
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 p-10 text-center">
      <Inbox className="size-6 text-muted" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {children && <div className="text-sm text-muted">{children}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: ApiError | string; onRetry?: () => void }) {
  const message = typeof error === "string" ? error : error.message;
  const reference = typeof error === "string" ? null : error.correlationId;
  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-md border border-danger/40 bg-danger-soft p-4 text-sm text-danger"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        <p>{message}</p>
        {reference && <p className="mt-1 font-mono text-xs break-all opacity-80">Reference: {reference}</p>}
      </div>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
