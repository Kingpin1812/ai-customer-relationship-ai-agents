import {
  Ban,
  CheckCircle2,
  CircleDashed,
  Clock,
  Hand,
  Loader2,
  type LucideIcon,
  MinusCircle,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { cn, humanize } from "@/lib/utils";

const STYLES: Record<string, { className: string; icon: LucideIcon; label?: string }> = {
  queued: { className: "bg-neutral-soft text-foreground", icon: Clock },
  pending: { className: "bg-gate-soft text-gate", icon: Clock },
  running: { className: "bg-info-soft text-info", icon: Loader2 },
  waiting_for_approval: { className: "bg-gate-soft text-gate", icon: Hand, label: "Waiting for approval" },
  succeeded: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  approved: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  connected: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  issued: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  sent: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  success: { className: "bg-success-soft text-success", icon: CheckCircle2 },
  failed: { className: "bg-danger-soft text-danger", icon: XCircle },
  rejected: { className: "bg-danger-soft text-danger", icon: XCircle },
  manual_review_required: { className: "bg-danger-soft text-danger", icon: Hand, label: "Needs manual review" },
  unknown_outcome: { className: "bg-gate-soft text-gate", icon: CircleDashed },
  retry_scheduled: { className: "bg-info-soft text-info", icon: RefreshCw },
  changes_requested: { className: "bg-gate-soft text-gate", icon: RefreshCw },
  cancelled: { className: "bg-neutral-soft text-foreground", icon: Ban },
  expired: { className: "bg-neutral-soft text-foreground", icon: MinusCircle },
  disconnected: { className: "bg-neutral-soft text-foreground", icon: MinusCircle },
  draft: { className: "bg-neutral-soft text-foreground", icon: CircleDashed },
};

/** Status is always written out; colour and icon only reinforce it. */
export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const style = STYLES[status] ?? { className: "bg-neutral-soft text-foreground", icon: CircleDashed };
  const Icon = style.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap",
        style.className,
        className,
      )}
    >
      <Icon className={cn("size-3.5", status === "running" && "animate-spin")} aria-hidden />
      {style.label ?? humanize(status)}
    </span>
  );
}
