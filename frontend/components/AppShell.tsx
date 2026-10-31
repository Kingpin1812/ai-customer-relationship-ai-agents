"use client";

import {
  FileText,
  Gauge,
  Hand,
  Inbox,
  LogOut,
  type LucideIcon,
  Menu,
  PlugZap,
  ReceiptText,
  ScrollText,
  Settings,
  ShieldCheck,
  Workflow,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";
import { setToken } from "@/lib/api";
import { useSession } from "@/hooks/useSession";
import { cn, humanize } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  needs?: string[];
  sandbox?: boolean;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Overview", icon: Gauge },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/approvals", label: "Approvals", icon: Hand },
  { href: "/invoices", label: "Invoices", icon: ReceiptText },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/integrations", label: "Integrations", icon: PlugZap },
  { href: "/audit", label: "Audit log", icon: ScrollText },
  { href: "/outbox", label: "Sandbox outbox", icon: Inbox, needs: ["business_view_all"], sandbox: true },
  { href: "/settings", label: "Settings", icon: Settings, needs: ["user_manage"] },
];

export function AppShell({ children }: { children: ReactNode }) {
  const me = useSession();
  const pathname = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const items = NAV.filter(
    (item) =>
      (!item.needs || item.needs.some((p) => me.permissions.includes(p))) &&
      (!item.sandbox || me.sandbox_enabled),
  );

  const nav = (
    <nav aria-label="Main" className="flex flex-col gap-1">
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex h-10 items-center gap-3 rounded-md px-3 text-sm",
              active ? "bg-primary text-primary-foreground" : "hover:bg-surface-muted",
            )}
          >
            <item.icon className="size-4" aria-hidden />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  const account = (
    <div className="border-t border-border pt-3 text-sm">
      <p className="truncate font-medium">{me.display_name}</p>
      <p className="truncate text-xs text-muted">
        {humanize(me.role)} · {me.organization_name}
      </p>
      <Button
        variant="ghost"
        size="sm"
        className="mt-2 -ml-3"
        onClick={() => {
          setToken(null);
          router.replace("/login");
        }}
      >
        <LogOut aria-hidden />
        Sign out
      </Button>
    </div>
  );

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[15rem_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-surface focus:p-2">
        Skip to content
      </a>
      <header className="flex h-14 items-center justify-between border-b border-border bg-surface px-4 lg:hidden">
        <span className="flex items-center gap-2 font-semibold text-primary">
          <ShieldCheck className="size-5" aria-hidden />
          Workflow Control
        </span>
        <Button variant="ghost" size="icon" aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open} onClick={() => setOpen(!open)}>
          {open ? <X aria-hidden /> : <Menu aria-hidden />}
        </Button>
      </header>
      {open && (
        <div className="flex flex-col gap-4 border-b border-border bg-surface p-4 lg:hidden">
          {nav}
          {account}
        </div>
      )}
      <aside className="hidden border-r border-border bg-surface lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col lg:justify-between lg:p-4">
        <div>
          <div className="mb-6 flex items-center gap-2 px-3 font-semibold text-primary">
            <ShieldCheck className="size-5" aria-hidden />
            Workflow Control
          </div>
          {nav}
        </div>
        {account}
      </aside>
      <main id="main" className="min-w-0 p-4 sm:p-6 lg:p-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold sm:text-2xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  );
}
