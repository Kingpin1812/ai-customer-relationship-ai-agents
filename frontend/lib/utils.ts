import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string): string {
  // Date-only values parse as UTC midnight, so printing them in local time can show the wrong day.
  const timeZone = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? "UTC" : undefined;
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium", timeZone });
}

/** Display only. The backend computes every amount; this never does arithmetic on money. */
export function formatMoney(currency: string | null | undefined, amount: string | null | undefined) {
  if (amount == null) return "—";
  const [whole = "0", fraction = "00"] = amount.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const symbol = currency === "INR" ? "₹" : currency ? `${currency} ` : "";
  return `${symbol}${grouped}.${fraction.padEnd(2, "0").slice(0, 2)}`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds / 60)}m`;
}

export function humanize(value: string): string {
  const text = value.replace(/[._]/g, " ").replace(/\bcrm\b/gi, "CRM");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
