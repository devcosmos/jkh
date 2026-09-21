import type { SelectHTMLAttributes } from "react";
import { SECONDARY_FIELD } from "./controlStyles";

// Нативная стрелка <select> у браузеров садится вплотную к тексту без отступа — убираем её
// (appearance-none) и рисуем свою с нормальным правым паддингом.
export function Select({ className = "", children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        {...props}
        className={`appearance-none rounded-xl py-2 pl-3 pr-9 text-sm font-medium ${SECONDARY_FIELD} ${className}`}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        className="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-slate-400"
      >
        <path d="m6 9 6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}
