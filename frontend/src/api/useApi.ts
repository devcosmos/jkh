import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./client";

interface Result<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Общий хук загрузки: явно различает загрузку/ошибку/данные, без скрытых состояний. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[] = []): Result<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then((d) => setData(d))
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
