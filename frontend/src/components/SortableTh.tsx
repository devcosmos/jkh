import { ChevronIcon } from "./icons";

export function SortableTh<K extends string>({
  label,
  sortKey,
  sortBy,
  sortDir,
  onSort,
}: {
  label: string;
  sortKey: K;
  sortBy: K;
  sortDir: "asc" | "desc";
  onSort: (key: K) => void;
}) {
  const active = sortBy === sortKey;
  return (
    <th className="px-4 py-3 whitespace-nowrap">
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
