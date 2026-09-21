import { Badge } from "./Badge";

const ANOMALY_TEXT =
  "Аномальное поведение — сочетание тревог, переходов состояния и пауз между событиями по этому датчику необычное: такого раньше почти не встречалось, даже среди уже случавшихся поломок. Это независимая проверка, отдельная от процента вероятности отказа выше — она может насторожить, даже если сама вероятность невысокая.";
const NORMAL_TEXT =
  "Поведение в норме — сочетание тревог, переходов состояния и пауз между событиями по этому датчику уже встречалось раньше и само по себе ни о чём необычном не говорит. Независимая проверка не нашла отклонений — это не отменяет процент вероятности отказа выше, а просто отдельный сигнал.";

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
