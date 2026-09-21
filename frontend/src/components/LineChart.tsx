import { useId } from "react";
import { useEnterAnimation } from "./useEnterAnimation";

interface Series {
  label: string;
  color: string;
  values: number[];
}

/** Простой многосерийный линейный график без внешних зависимостей. Легенда обязательна
 * (>=2 серий) — цвет не единственный носитель идентичности серии.
 * `area` — заливка градиентом под линией (для карточек, где серии уже подписаны иначе,
 * например вкладками, легенду можно отключить через `legend={false}`). */
export function LineChart({
  dates,
  series,
  height = 140,
  area = false,
  legend = true,
}: {
  dates: string[];
  series: Series[];
  height?: number;
  area?: boolean;
  legend?: boolean;
}) {
  const width = 600;
  const gradientId = useId();
  const entered = useEnterAnimation();
  const max = Math.max(...series.flatMap((s) => s.values), 1);
  const stepX = dates.length > 1 ? width / (dates.length - 1) : 0;
  const toY = (v: number) => height - (v / max) * (height - 8) - 4;
  const baseline = height - 1;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none" style={{ height }}>
        {area && (
          <defs>
            {series.map((s, i) => (
              <linearGradient key={s.label} id={`${gradientId}-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={s.color} stopOpacity={0.25} />
                <stop offset="100%" stopColor={s.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
        )}
        <line x1={0} y1={baseline} x2={width} y2={baseline} stroke="#e2e8f0" strokeWidth={1} />
        <g
          className="transition-all duration-700 ease-out"
          style={{
            opacity: entered ? 1 : 0,
            transform: entered ? "scaleY(1)" : "scaleY(0.85)",
            transformOrigin: `0px ${baseline}px`,
          }}
        >
          {series.map((s, i) => {
            const points = s.values.map((v, j) => `${j * stepX},${toY(v)}`).join(" ");
            return (
              <g key={s.label}>
                {area && (
                  <polygon
                    points={`0,${baseline} ${points} ${width},${baseline}`}
                    fill={`url(#${gradientId}-${i})`}
                    stroke="none"
                  />
                )}
                <polyline
                  points={points}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={2}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </g>
            );
          })}
        </g>
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-slate-400">
        <span>{dates[0]}</span>
        <span>{dates[dates.length - 1]}</span>
      </div>
      {legend && (
        <div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-500">
          {series.map((s) => (
            <span key={s.label} className="flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
