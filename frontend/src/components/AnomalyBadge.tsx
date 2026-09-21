import { Badge } from "./Badge";

const ANOMALY_TEXT =
  "Отдельная модель, не обученная на размеченных отказах (IsolationForest), сама заметила необычную комбинацию показаний датчика — не похожую ни на один известный сценарий поломки в обучающих данных.";
const NORMAL_TEXT = "Та же независимая проверка (не обученная на размеченных отказах) не нашла ничего необычного в показаниях датчика.";

/** Бейдж «независимой модели» (IsolationForest) с пояснением на ховере — сам по себе
 * термин без контекста непонятен диспетчеру, поэтому полное объяснение спрятано в тултип,
 * а не выводится текстом рядом всегда. */
export function AnomalyBadge({ isOutlier }: { isOutlier: boolean }) {
  return (
    <div className="group relative inline-block cursor-help">
      {isOutlier ? <Badge tone="serious">Аномальное поведение</Badge> : <Badge tone="neutral">Поведение в норме</Badge>}
      <div className="pointer-events-none absolute top-full left-0 z-10 mt-1.5 w-72 max-w-[80vw] rounded-lg bg-slate-900 px-3 py-2 text-sm text-slate-100 opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
        {isOutlier ? ANOMALY_TEXT : NORMAL_TEXT}
      </div>
    </div>
  );
}
