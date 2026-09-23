import { api, getRole } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge } from "../components/Badge";
import { BarList } from "../components/BarList";
import { CalibrationChart } from "../components/CalibrationChart";
import { DataState } from "../components/DataState";
import { DetailSection } from "../components/DetailSection";
import type { ModelVersionOut } from "../api/types";

const FEATURE_LABELS: Record<string, string> = {
  n_alarms_1h: "Тревог за 1 час",
  n_alarms_24h: "Тревог за 24 часа",
  n_alarms_7d: "Тревог за 7 суток",
  n_transitions_1h: "Переходов состояния за 1 час",
  n_transitions_24h: "Переходов состояния за 24 часа",
  n_transitions_7d: "Переходов состояния за 7 суток",
  n_events_1h: "Событий за 1 час",
  n_events_24h: "Событий за 24 часа",
  n_events_7d: "Событий за 7 суток",
  seconds_since_last_event: "Секунд с последнего события",
  n_neighbors_in_fault: "Соседей в отказе",
  frac_neighbors_in_fault: "Доля соседей в отказе",
  current_state: "Текущее состояние",
  тип_датчика: "Тип датчика",
};

function metricNumber(metrics: Record<string, unknown> | null, key: string): number | null {
  const v = metrics?.[key];
  return typeof v === "number" ? v : null;
}

// Статичные сведения о двух моделях, которые не версионируются в БД как CatBoost
// (ModelVersion) — сюда просто нечего тянуть через API. IsolationForest — фиксированный
// .joblib-артефакт (ml/training/train_anomaly_model.py, отчёт artifacts/anomaly_model_report.json,
// не меняется без ручного переобучения); Claude Haiku — внешний API, не модель в БД вообще.
// Обновлять вручную при переобучении/смене модели резюме.
const ANOMALY_MODEL_REPORT: Record<
  string,
  { label: string; nTrainRows: number; scoreP01: number; scoreP50: number; scoreP99: number }
> = {
  насос_вентилятор: { label: "Насос/вентилятор", nTrainRows: 3_689_092, scoreP01: -0.0253, scoreP50: 0.3264, scoreP99: 0.3466 },
  дым_газ: { label: "Дым/газ", nTrainRows: 27_528_887, scoreP01: -0.0544, scoreP50: 0.2977, scoreP99: 0.3135 },
};
const ANOMALY_CONTAMINATION = 0.02;
const ANOMALY_FEATURES = [
  "n_alarms_1h",
  "n_alarms_24h",
  "n_alarms_7d",
  "n_transitions_1h",
  "n_transitions_24h",
  "n_transitions_7d",
  "n_events_1h",
  "n_events_24h",
  "n_events_7d",
  "seconds_since_last_event",
  "n_neighbors_in_fault",
  "frac_neighbors_in_fault",
];

export function ModelsPage() {
  const models = useApi<ModelVersionOut[]>(() => api.get("/models/current"), []);
  const isAdmin = getRole() === "admin";
  const history = useApi<ModelVersionOut[]>(() => (isAdmin ? api.get("/models") : Promise.resolve([])), [isAdmin]);
  const replacedVersions = history.data?.filter((m) => !m.is_active) ?? [];

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Модели</h1>
        <p className="mt-1 text-sm text-slate-500">
          Активные версии CatBoost — по одной на независимо оцениваемое направление
        </p>
      </div>

      <DataState loading={models.loading} error={models.error} empty={!models.data?.length} emptyText="Активных моделей нет">
        <div className="space-y-4">
          {models.data?.map((m) => {
            const rocAuc = metricNumber(m.metrics, "roc_auc_test");
            const prAuc = metricNumber(m.metrics, "pr_auc_test");
            const targetPrecision = metricNumber(m.metrics, "target_precision");
            const targetRecall = metricNumber(m.metrics, "target_recall");
            const targetMet = m.metrics?.target_met === true;
            const note = typeof m.metrics?.operating_threshold_note === "string" ? m.metrics.operating_threshold_note : null;
            const featureImportance = m.metrics?.feature_importance as Record<string, number> | undefined;
            const calibration = m.metrics?.calibration as
              | { bin_start: number; bin_end: number; n: number; mean_predicted: number | null; observed_rate: number | null; reliable: boolean }[]
              | undefined;
            const topFeatures = featureImportance
              ? Object.entries(featureImportance)
                  .sort((a, b) => b[1] - a[1])
                  .slice(0, 5)
              : [];

            return (
              <DetailSection
                key={m.id}
                title={m.name}
                right={
                  <Badge tone={targetMet ? "good" : "warning"}>
                    {targetMet ? "Плановая цель достигнута" : "Ниже плановой цели (обоснованно)"}
                  </Badge>
                }
                footer={
                  <span className="text-sm text-slate-400">
                    Обучена {new Date(m.trained_at).toLocaleDateString("ru-RU")}
                  </span>
                }
              >
                <p className="text-sm text-slate-500">{m.sensor_types.split(",").join(", ")}</p>

                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Metric label="Рабочий порог" value={m.threshold?.toFixed(2) ?? "—"} />
                  <Metric label="ROC-AUC (test)" value={rocAuc != null ? rocAuc.toFixed(3) : "—"} />
                  <Metric label="PR-AUC (test)" value={prAuc != null ? prAuc.toFixed(3) : "—"} />
                  <Metric
                    label="Плановая цель P/R"
                    value={targetPrecision != null && targetRecall != null ? `${targetPrecision}/${targetRecall}` : "—"}
                  />
                </div>

                {note && <p className="rounded-xl bg-slate-50 p-3 text-sm text-slate-500">{note}</p>}

                {(topFeatures.length > 0 || calibration) && (
                  <div className="grid gap-6 border-t border-slate-100 pt-4 lg:grid-cols-2">
                    {topFeatures.length > 0 && (
                      <div>
                        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                          Какие признаки важнее всего для этой модели
                        </h4>
                        <BarList
                          variant="fill"
                          items={topFeatures.map(([key, value]) => ({
                            key,
                            label: FEATURE_LABELS[key] ?? key,
                            value,
                          }))}
                          formatValue={(v) => v.toFixed(1)}
                        />
                      </div>
                    )}

                    {calibration && (
                      <div>
                        <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                          Калибровка вероятности (test)
                        </h4>
                        <CalibrationChart bins={calibration} />
                      </div>
                    )}
                  </div>
                )}
              </DetailSection>
            );
          })}
        </div>
      </DataState>

      <div className="mt-8 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">
          Вспомогательные модели — не CatBoost, работают рядом с ним
        </h2>

        <DetailSection
          title="Независимая проверка аномального поведения"
          right={<Badge tone="serious">IsolationForest</Badge>}
        >
          <p className="text-sm text-slate-600">
            Отдельная модель без учителя (scikit-learn IsolationForest), по одной на каждый трек —
            как и у CatBoost. Обучена на тех же поведенческих признаках канала (частота тревог,
            переходов состояния, событий за 1ч/24ч/7д, время с последнего события, доля соседних
            каналов в отказе), но <span className="font-medium text-slate-800">без меток отказа</span> — она не
            учится узнавать конкретные сценарии поломки, а выучивает, как вообще выглядит «обычное»
            поведение канала, и помечает выбросом то, что на это не похоже.
          </p>
          <p className="text-sm text-slate-600">
            Смысл в независимости: CatBoost находит только уже виденные в разметке паттерны отказа.
            IsolationForest может насторожиться на поведение, которого в обучающей выборке отказов
            вообще не было — второе, принципиально другое мнение, а не то же самое другими словами.
            Считается воркером на каждом тике параллельно с прогнозом CatBoost, результат
            (score, is_outlier) сохраняется в объяснении прогноза — это и есть бейдж «Аномальное
            поведение» / «Поведение в норме», который виден на «Рисках», в «Журнале» и в заявках.
          </p>
          <div className="rounded-xl border border-orange-200 bg-orange-50 px-3.5 py-2.5 text-sm text-orange-800">
            Это не просто индикатор: если независимая модель отмечает канал как выброс, риск-кейс
            автоматически получает приоритет «Критично» — даже если вероятность отказа по CatBoost
            ниже 85% (<code className="rounded bg-white/60 px-1 py-0.5">replay_worker.py</code>).
          </div>

          <div className="grid gap-4 border-t border-slate-100 pt-4 sm:grid-cols-2">
            {Object.entries(ANOMALY_MODEL_REPORT).map(([key, t]) => (
              <div key={key} className="rounded-xl bg-slate-50 p-3.5">
                <div className="mb-2 text-sm font-semibold text-slate-800">{t.label}</div>
                <div className="grid grid-cols-2 gap-3">
                  <Metric label="Строк в обучении" value={t.nTrainRows.toLocaleString("ru-RU")} />
                  <Metric label="Ожидаемая доля выбросов" value={`${(ANOMALY_CONTAMINATION * 100).toFixed(0)}%`} />
                  <Metric label="Медианный скор" value={t.scoreP50.toFixed(3)} />
                  <Metric label="1-й перцентиль скора" value={t.scoreP01.toFixed(3)} />
                </div>
              </div>
            ))}
          </div>

          <div>
            <h4 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
              Признаки, на которых обучена
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {ANOMALY_FEATURES.map((f) => (
                <span key={f} className="rounded-full bg-slate-100 px-2.5 py-1 text-sm text-slate-600">
                  {FEATURE_LABELS[f] ?? f}
                </span>
              ))}
            </div>
          </div>
        </DetailSection>

        <DetailSection
          title="Резюме прогноза на естественном языке"
          right={<Badge tone="neutral">Claude Haiku 4.5</Badge>}
        >
          <p className="text-sm text-slate-600">
            Отдельный внешний сервис (Anthropic Claude, модель{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5">claude-haiku-4-5-20251001</code>) — не модель
            прогнозирования, а перевод уже готового объяснения в человеческий текст. На вход подаётся
            вклад признаков (SHAP) в конкретный прогноз и флаг независимой проверки аномальности;
            на выходе — 1-2 предложения разговорным языком вроде «вероятность выросла в основном
            из-за учащения тревог за последний час, канал также отмечен как аномальный». Модели прямо
            запрещено придумывать что-либо про объект/устройство сверх переданных данных.
          </p>
          <p className="text-sm text-slate-600">
            Используется лёгкая модель (Haiku), а не топовая — короткая шаблонная суммаризация не
            требует reasoning топового уровня, а стоимость и задержка у Haiku на порядок ниже.
            Считается лениво — только когда диспетчер открывает конкретную карточку риска, — и
            результат кешируется в БД (<code className="rounded bg-slate-100 px-1 py-0.5">Prediction.llm_summary</code>),
            поэтому повторные просмотры той же карточки не обращаются к API снова.
          </p>
          <p className="text-sm text-slate-500">
            Опциональна: без настроенного ключа API функция просто недоступна (карточка риска
            показывает «резюме недоступно»), остальная система не зависит от стороннего сервиса.
          </p>
        </DetailSection>
      </div>

      {isAdmin && replacedVersions.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
            История версий (заменённые дообучением)
          </h2>
          <p className="mb-3 text-sm text-slate-400">
            Раздел 8 ЖКХ.md — регистрация новой версии описана в{" "}
            <code className="rounded bg-slate-100 px-1 py-0.5">scripts/maintenance/register_model_version.py</code>
          </p>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-3">Название</th>
                  <th className="px-4 py-3">Направление</th>
                  <th className="px-4 py-3">Обучена</th>
                  <th className="px-4 py-3">Порог</th>
                </tr>
              </thead>
              <tbody>
                {replacedVersions.map((m) => (
                  <tr key={m.id} className="border-b border-slate-100 text-slate-500 last:border-0">
                    <td className="px-4 py-3">{m.name}</td>
                    <td className="px-4 py-3">{m.sensor_types.split(",").join(", ")}</td>
                    <td className="px-4 py-3">{new Date(m.trained_at).toLocaleDateString("ru-RU")}</td>
                    <td className="px-4 py-3">{m.threshold?.toFixed(2) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-display text-lg font-semibold text-slate-900">{value}</div>
      <div className="mt-0.5 text-sm text-slate-500">{label}</div>
    </div>
  );
}
