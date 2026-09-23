import type { ReactNode } from "react";
import { CloseIcon } from "./icons";

/** Плашка «сейчас показан только X» — сквозной фильтр по ссылке (риск-кейс/канал/объект).
 * Тот же силуэт, что у карточки-ссылки «по этому риску уже есть заявка» в RiskCard.tsx
 * (border+bg, rounded-xl px-3.5 py-2.5), но фиолетовая — чтобы не путать активный фильтр
 * с кликабельной ссылкой на связанную сущность, хотя вёрстка одна и та же. */
export function FilterBanner({
  children,
  onClear,
  clearLabel,
}: {
  children: ReactNode;
  onClear: () => void;
  clearLabel: string;
}) {
  return (
    <div className="mb-4 flex items-center justify-between rounded-xl border border-violet-200 bg-violet-50 px-3.5 py-2.5 text-sm text-slate-700">
      <span>{children}</span>
      <button
        onClick={onClear}
        className="flex shrink-0 items-center gap-1 font-semibold text-violet-700 transition-colors hover:text-violet-900"
      >
        {clearLabel}
        <CloseIcon className="h-3.5 w-3.5" strokeWidth={2.2} />
      </button>
    </div>
  );
}
