import type { ReactNode } from "react";

interface Props {
  loading: boolean;
  error: string | null;
  empty: boolean;
  emptyText?: string;
  children: ReactNode;
}

/** Явно различает нормальное/пустое/ошибочное состояния — требование раздела 2 ТЗ MVP. */
export function DataState({ loading, error, empty, emptyText, children }: Props) {
  if (loading) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-slate-200 bg-white px-5 py-8 text-sm text-slate-500">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-sky-500" />
        Загрузка…
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-2xl border border-red-100 bg-red-50 px-5 py-8 text-sm font-medium text-red-600">
        Ошибка: {error}
      </div>
    );
  }
  if (empty) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white px-5 py-10 text-center text-sm text-slate-500">
        {emptyText ?? "Нет данных"}
      </div>
    );
  }
  return <>{children}</>;
}
