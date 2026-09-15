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
  if (loading) return <div className="state state-loading">Загрузка…</div>;
  if (error) return <div className="state state-error">Ошибка: {error}</div>;
  if (empty) return <div className="state state-empty">{emptyText ?? "Нет данных"}</div>;
  return <>{children}</>;
}
