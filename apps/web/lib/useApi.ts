// Data-fetching hook with loading / error / retry, plus an explicit
// DEMO fallback: when the fetch fails with a NetworkError (server
// unreachable), callers may supply demo data that is rendered with a
// clearly-labeled banner — never silent fakes.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, NetworkError } from "@/lib/api";

export type FetchStatus = "loading" | "success" | "error";

export interface UseApiResult<T> {
  data: T | null;
  status: FetchStatus;
  error: ApiError | NetworkError | Error | null;
  /** true when demo fallback data is being shown */
  demo: boolean;
  reload: () => void;
}

export function useApi<T>(
  fetcher: (() => Promise<T>) | null,
  options: { demoFallback?: () => T; deps?: ReadonlyArray<unknown> } = {},
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [status, setStatus] = useState<FetchStatus>("loading");
  const [error, setError] = useState<ApiError | NetworkError | Error | null>(null);
  const [demo, setDemo] = useState(false);
  const [tick, setTick] = useState(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const deps = options.deps ?? [];

  useEffect(() => {
    let cancelled = false;
    const fn = fetcherRef.current;
    if (!fn) {
      setStatus("error");
      setError(new Error("no fetcher"));
      return;
    }
    setStatus("loading");
    setError(null);
    fn()
      .then((d) => {
        if (cancelled) return;
        setData(d);
        setDemo(false);
        setStatus("success");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        if (e instanceof NetworkError && options.demoFallback) {
          setData(options.demoFallback());
          setDemo(true);
          setStatus("success");
          return;
        }
        setError(e instanceof Error ? e : new Error(String(e)));
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, ...deps]);

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, status, error, demo, reload };
}
