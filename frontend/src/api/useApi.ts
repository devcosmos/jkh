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
      .catch((e) => {
        // eslint-disable-next-line no-console
        console.error("useApi fetch failed:", e);
        if (e instanceof ApiError) {
          setError(e.message);
        } else if (e instanceof Error) {
          // fetch() сам бросает TypeError ("Failed to fetch"/"Load failed") при сетевых
          // сбоях — в т.ч. когда запрос вообще не уходит на сервер (заблокирован
          // расширением браузера/блокировщиком рекламы). message у Error — уже строка.
          setError(e.message);
        } else {
          // Что-то бросило не Error (например, обёртка какого-то расширения браузера
          // вокруг fetch) — String() на произвольном объекте даёт нечитаемое
          // "[object Object]", JSON.stringify хотя бы показывает структуру.
          try {
            setError(JSON.stringify(e));
          } catch {
            setError(String(e));
          }
        }
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}
