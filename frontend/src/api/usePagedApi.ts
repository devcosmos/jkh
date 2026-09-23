import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "./client";

interface PagedResult<T> {
  data: T[] | null;
  total: number | null;
  page: number;
  pageSize: number;
  setPage: (page: number) => void;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/** Постраничная загрузка списка: `buildUrl(limit, offset)` строит URL текущей страницы,
 * `deps` — фильтры/сортировка, при смене которых страница сбрасывается на первую (иначе
 * легко зависнуть на несуществующей странице 5 после сужения фильтра до двух строк).
 * `total` берётся из заголовка X-Total-Count (см. api.getPage) — null, если бэкенд его не
 * прислал (тогда Pagination показывает только "вперёд", без номера последней страницы). */
export function usePagedApi<T>(
  buildUrl: (limit: number, offset: number) => string,
  deps: unknown[],
  pageSize = 20
): PagedResult<T> {
  const [page, setPageState] = useState(0);
  const [data, setData] = useState<T[] | null>(null);
  const [total, setTotal] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // Смена фильтров/сортировки — на первую страницу, иначе можно застрять на пустой
  // странице N после того, как выборка сузилась.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => setPageState(0), deps);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .getPage<T>(buildUrl(pageSize, page * pageSize))
      .then(({ items, total }) => {
        setData(items);
        setTotal(total);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, page, pageSize, tick]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    data,
    total,
    page,
    pageSize,
    setPage: setPageState,
    loading,
    error,
    reload: () => setTick((t) => t + 1),
  };
}
