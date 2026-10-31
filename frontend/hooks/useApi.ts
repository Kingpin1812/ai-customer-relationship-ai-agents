"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiGet } from "@/lib/api";

interface Options<T> {
  /** Poll while this returns a positive interval in ms. */
  pollMs?: (data: T | null) => number;
}

const IDLE_CHECK_MS = 2000;

export function useApi<T>(path: string | null, options: Options<T> = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const requestId = useRef(0);
  const latest = useRef<{ data: T | null; pollMs: Options<T>["pollMs"] }>({
    data: null,
    pollMs: options.pollMs,
  });

  useEffect(() => {
    latest.current = { data, pollMs: options.pollMs };
  });

  const load = useCallback(async () => {
    if (path === null) return;
    const id = ++requestId.current;
    try {
      const result = await apiGet<T>(path);
      if (id !== requestId.current) return;
      setData(result);
      setError(null);
    } catch (e) {
      if (id !== requestId.current) return;
      setError(e instanceof ApiError ? e : new ApiError(0, "unknown", "Something went wrong."));
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    // Fetching on mount and when the path changes is the point of this hook.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    let stopped = false;
    const tick = () => {
      const interval = latest.current.pollMs?.(latest.current.data) ?? 0;
      timer = setTimeout(
        async () => {
          if (interval > 0 && !document.hidden) await load();
          if (!stopped) tick();
        },
        interval > 0 ? interval : IDLE_CHECK_MS,
      );
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [load]);

  return { data, error, loading, reload: load };
}
