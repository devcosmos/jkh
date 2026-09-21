interface Series {
  label: string;
  color: string;
  values: number[];
}

/** Простой многосерийный линейный график без внешних зависимостей. Легенда обязательна
 * (>=2 серий) — цвет не единственный носитель идентичности серии. */
export function LineChart({
  dates,
  series,
  height = 140,
}: {
  dates: string[];
  series: Series[];
  height?: number;
}) {
  const width = 600;
  const max = Math.max(...series.flatMap((s) => s.values), 1);
  const stepX = dates.length > 1 ? width / (dates.length - 1) : 0;
  const toY = (v: number) => height - (v / max) * (height - 8) - 4;

  return (
    <div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="none" style={{ height }}>
        <line x1={0} y1={height - 1} x2={width} y2={height - 1} stroke="#e2e8f0" strokeWidth={1} />
        {series.map((s) => (
          <polyline
            key={s.label}
            points={s.values.map((v, i) => `${i * stepX},${toY(v)}`).join(" ")}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-slate-400">
        <span>{dates[0]}</span>
        <span>{dates[dates.length - 1]}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-500">
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
