import { useEnterAnimation } from "./useEnterAnimation";

interface CalibrationBin {
  bin_start: number;
  bin_end: number;
  n: number;
  mean_predicted: number | null;
  observed_rate: number | null;
  reliable: boolean;
}

/** Калибровочная кривая (reliability diagram): по оси X — что предсказала модель, по оси Y —
 * что случилось на самом деле, на test-сплите (ml/evaluation/compute_calibration.py). Диагональ —
 * идеальная калибровка (X% предсказания = X% реальных отказов). Полые точки — бины с малым
 * числом наблюдений, им доверять меньше. */
export function CalibrationChart({ bins }: { bins: CalibrationBin[] }) {
  const entered = useEnterAnimation();
  const size = 180;
  const pad = 6;
  const scale = size - 2 * pad;
  const toX = (v: number) => pad + v * scale;
  const toY = (v: number) => size - pad - v * scale;
  const valid = bins.filter((b) => b.n > 0 && b.mean_predicted != null && b.observed_rate != null);

  if (valid.length === 0) {
    return <p className="text-sm text-slate-400">Недостаточно данных для калибровки</p>;
  }

  return (
    <div className="flex w-full flex-wrap items-center gap-5">
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="h-40 w-40 shrink-0 transition-all duration-700 ease-out"
        style={{ opacity: entered ? 1 : 0, transform: entered ? "scale(1)" : "scale(0.94)" }}
      >
        <line x1={toX(0)} y1={toY(0)} x2={toX(0)} y2={toY(1)} stroke="#e2e8f0" strokeWidth={1} />
        <line x1={toX(0)} y1={toY(0)} x2={toX(1)} y2={toY(0)} stroke="#e2e8f0" strokeWidth={1} />
        <line
          x1={toX(0)}
          y1={toY(0)}
          x2={toX(1)}
          y2={toY(1)}
          stroke="#cbd5e1"
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
        <polyline
          points={valid.map((b) => `${toX(b.mean_predicted!)},${toY(b.observed_rate!)}`).join(" ")}
          fill="none"
          stroke="#0284c7"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {valid.map((b) => (
          <circle
            key={b.bin_start}
            cx={toX(b.mean_predicted!)}
            cy={toY(b.observed_rate!)}
            r={b.reliable ? 3.5 : 2.5}
            fill={b.reliable ? "#0284c7" : "white"}
            stroke="#0284c7"
            strokeWidth={1.5}
          />
        ))}
        <text x={pad} y={size - 1} fontSize={7} fill="#94a3b8">0%</text>
        <text x={size - 18} y={size - 1} fontSize={7} fill="#94a3b8">100%</text>
      </svg>
      <div className="min-w-56 flex-1 space-y-1.5 text-sm text-slate-500">
        <div className="flex items-center gap-1.5">
          <svg width="16" height="8"><line x1="0" y1="4" x2="16" y2="4" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="3 2" /></svg>
          идеальная калибровка (X% = X%)
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-sky-600" />
          фактическая частота отказов
        </div>
        <p className="pt-1">
          Ось X — предсказанная вероятность, ось Y — реально наблюдаемая частота. Кривая ниже
          диагонали — вероятность стоит читать как ранжирующий сигнал (выше/ниже), а не как
          точный процент шанса отказа.
        </p>
      </div>
    </div>
  );
}
