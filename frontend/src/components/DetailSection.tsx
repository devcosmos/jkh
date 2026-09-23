import type { ReactNode } from "react";

/** Карточка-секция для правой панели детализации (риск-кейс/прогноз/заявка) — заголовок
 * с необязательным контекстным значением справа, отделённый от тела полосой снизу.
 * `footer` — необязательная нижняя полоса во всю ширину карточки (без отступа тела),
 * для одного итогового факта вроде «Создана: <дата>» под основным содержимым. */
export function DetailSection({
  title,
  right,
  footer,
  children,
  className = "",
}: {
  title: string;
  right?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  /** Доп. классы на внешний контейнер — например self-start, чтобы карточка не
   * растягивалась на всю высоту грид-ячейки вслед за более высоким соседом. */
  className?: string;
}) {
  return (
    <div className={`flex flex-col h-full rounded-2xl border border-slate-200 bg-white ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-x-5 gap-y-2 border-b border-slate-100 px-5 py-3">
        <h3 className="font-display text-sm font-semibold text-slate-900">{title}</h3>
        {right}
      </div>
      <div className="flex flex-col gap-4 px-5 py-4 flex-1">{children}</div>
      {footer && <div className="border-t border-slate-100 px-5 py-3">{footer}</div>}
    </div>
  );
}
