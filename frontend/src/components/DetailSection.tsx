import type { ReactNode } from "react";

/** Карточка-секция для правой панели детализации (риск-кейс/прогноз/заявка) — заголовок
 * с необязательным контекстным значением справа, отделённый от тела полосой снизу. */
export function DetailSection({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col rounded-2xl border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 border-b border-slate-100 px-5 py-3">
        <h3 className="font-display text-sm font-semibold text-slate-900">{title}</h3>
        {right}
      </div>
      <div className="flex flex-col gap-4 px-5 py-4">{children}</div>
    </div>
  );
}
