import { Button } from "@/components/ui/button";

export function Pager({
  total,
  limit,
  offset,
  onChange,
}: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  if (total <= limit) return null;
  return (
    <nav aria-label="Pages" className="flex items-center justify-between gap-3 px-4 py-3 text-sm text-muted">
      <span>
        {offset + 1}–{Math.min(offset + limit, total)} of {total}
      </span>
      <span className="flex gap-2">
        <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </Button>
        <Button size="sm" variant="secondary" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>
          Next
        </Button>
      </span>
    </nav>
  );
}
