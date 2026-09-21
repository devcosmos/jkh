export function Pagination({
  page,
  pageSize,
  total,
  loadedCount,
  onPageChange,
}: {
  page: number;
  pageSize: number;
  total: number | null;
  loadedCount: number;
  onPageChange: (page: number) => void;
}) {
  const from = total === 0 ? 0 : page * pageSize + 1;
  const to = page * pageSize + loadedCount;
  const lastPage = total !== null ? Math.max(0, Math.ceil(total / pageSize) - 1) : null;
  const hasNext = lastPage !== null ? page < lastPage : loadedCount === pageSize;

  if (total !== null && total <= pageSize) return null;

  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-sm text-slate-500">
      <span>
        {total !== null ? (
          <>
            Показано {from}–{to} из {total}
          </>
        ) : (
          <>Показано {from}–{to}</>
        )}
      </span>
      <div className="flex items-center gap-2">
        <button
          disabled={page === 0}
          onClick={() => onPageChange(page - 1)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
        >
          ← Назад
        </button>
        <span className="px-1 tabular-nums">
          Стр. {page + 1}{lastPage !== null && <>{" "}из {lastPage + 1}</>}
        </span>
        <button
          disabled={!hasNext}
          onClick={() => onPageChange(page + 1)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 font-medium text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Вперёд →
        </button>
      </div>
    </div>
  );
}
