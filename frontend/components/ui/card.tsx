import type { ComponentProps, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("rounded-lg border border-border bg-surface", className)} {...props} />;
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <header className="flex min-h-12 items-center justify-between gap-3 border-b border-border px-4 py-2">
      <h2 className="text-sm font-semibold">{title}</h2>
      {action}
    </header>
  );
}

export function CardBody({ className, ...props }: ComponentProps<"div">) {
  return <div className={cn("p-4", className)} {...props} />;
}
