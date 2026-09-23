import { ChevronIcon } from "./icons";

export function SortableTh<K extends string>({
  label,
  sortKey,
  sortBy,
  sortDir,
  onSort,
  className = "px-4 py-3 whitespace-nowrap",
}: {
  label: string;
  sortKey: K;
  sortBy: K;
  sortDir: "asc" | "desc";
  onSort: (key: K) => void;
  /** Переопределить паддинги заголовка — чтобы совпадали с <td> конкретной таблицы. */
  className?: string;
}) {
  const active = sortBy === sortKey;
  return (
    <th className={className}>
      <button
        onClick={() => onSort(sortKey)}
        className={`flex items-center gap-1 uppercase tracking-wide transition-colors ${
          active ? "text-slate-900" : "text-slate-500 hover:text-slate-700"
        }`}
      >
        {label}
        <ChevronIcon
          className={`h-3 w-3 transition-transform ${active ? "opacity-100" : "opacity-30"} ${
            sortDir === "desc" ? "rotate-90" : "-rotate-90"
          }`}
          strokeWidth={2.5}
        />
      </button>
    </th>
  );
}
