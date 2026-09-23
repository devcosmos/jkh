import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { usePagedApi } from "../api/usePagedApi";
import { Badge } from "../components/Badge";
import { SECONDARY_FIELD } from "../components/controlStyles";
import { DataState } from "../components/DataState";
import { DegradationTrendBadge } from "../components/DegradationTrendBadge";
import { FilterBanner } from "../components/FilterBanner";
import { Pagination } from "../components/Pagination";
import { Select } from "../components/Select";
import type { ChannelOut, ObjectOut } from "../api/types";

const SENSOR_TYPES = ["Состояние насоса", "Состояние вентилятора", "Датчик дыма", "Газовый датчик"];

export function RegistryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [sensorType, setSensorType] = useState("");
  // Начальные значения — из query-параметров сквозной ссылки (ID канала из «Рисков», ID
  // объекта из «Обзора»/схемы объектов), дальше это обычные локальные фильтры страницы.
  const [objectFilter, setObjectFilter] = useState<number | null>(() => {
    const v = searchParams.get("object_id");
    return v ? Number(v) : null;
  });
  const [channelIdFilter, setChannelIdFilter] = useState<number | null>(() => {
    const v = searchParams.get("channel_id");
    return v ? Number(v) : null;
  });

  const objects = useApi<ObjectOut[]>(() => api.get("/objects?limit=500"), []);
  const channels = usePagedApi<ChannelOut>(
    (limit, offset) =>
      `/channels?limit=${limit}&offset=${offset}&include_trend=true${
        sensorType ? `&sensor_type=${encodeURIComponent(sensorType)}` : ""
      }${search ? `&search=${encodeURIComponent(search)}` : ""}${
        objectFilter ? `&object_id=${objectFilter}` : ""
      }${channelIdFilter ? `&external_channel_id=${channelIdFilter}` : ""}`,
    [sensorType, search, objectFilter, channelIdFilter],
    20
  );

  function clearChannelIdFilter() {
    setChannelIdFilter(null);
    const next = new URLSearchParams(searchParams);
    next.delete("channel_id");
    setSearchParams(next);
  }

  const objectNameById = useMemo(() => {
    const map = new Map<number, string>();
    objects.data?.forEach((o) => map.set(o.id, o.name));
    return map;
  }, [objects.data]);

  const sortedObjects = useMemo(
    () => [...(objects.data ?? [])].sort((a, b) => a.name.localeCompare(b.name, "ru")),
    [objects.data]
  );

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Объекты и каналы</h1>
        <p className="mt-1 text-sm text-slate-500">
          Реестр {objects.data?.length ?? "…"} объектов и подключённых к ним каналов датчиков
        </p>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию канала или тегу расположения…"
          className={`w-72 rounded-xl px-3.5 py-2 text-sm ${SECONDARY_FIELD}`}
        />
        <Select value={sensorType} onChange={(e) => setSensorType(e.target.value)}>
          <option value="">Все типы датчиков</option>
          {SENSOR_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </Select>
        <Select
          value={objectFilter ?? ""}
          onChange={(e) => setObjectFilter(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">Все объекты</option>
          {sortedObjects.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </Select>
        {objectFilter && (
          <button
            onClick={() => setObjectFilter(null)}
            className="text-sm font-medium text-slate-500 hover:text-slate-900"
          >
            Сбросить фильтр по объекту ×
          </button>
        )}
      </div>

      {channelIdFilter && (
        <FilterBanner onClear={clearChannelIdFilter} clearLabel="Показать все каналы">
          Показан только канал <span className="font-semibold">#{channelIdFilter}</span>
        </FilterBanner>
      )}

      <DataState
        loading={channels.loading}
        error={channels.error}
        empty={!channels.data?.length}
        emptyText="Каналов не найдено"
      >
        <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/80 text-left text-sm font-semibold uppercase tracking-wide text-slate-500">
                <th className="px-4 py-3">ID&nbsp;канала</th>
                <th className="px-4 py-3">Название</th>
                <th className="px-4 py-3">Устройство</th>
                <th className="px-4 py-3">Тип датчика</th>
                <th className="px-4 py-3">Объект</th>
                <th className="px-4 py-3">Расположение</th>
                <th className="px-4 py-3">Тренд</th>
              </tr>
            </thead>
            <tbody>
              {channels.data?.map((c) => (
                <tr key={c.id} className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-400">
                    <Link
                      to={`/risks?channel_id=${c.external_channel_id}`}
                      className="text-sky-700 hover:underline"
                      title="Показать риски по этому каналу"
                    >
                      {c.external_channel_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-medium text-slate-900">{c.display_name ?? "—"}</td>
                  <td className="px-4 py-3 text-slate-500">
                    {c.device_label ?? <span className="text-slate-300 whitespace-nowrap">не{" "}сопоставлено</span>}
                  </td>
                  <td className="px-4 py-3">
                    <Badge tone="neutral">{c.sensor_type}</Badge>
                  </td>
                  <td className="px-4 py-3 text-slate-700">
                    {c.object_id ? (
                      <span className="flex items-center gap-2">
                        <button
                          onClick={() => setObjectFilter(c.object_id)}
                          className="text-left text-sky-700 hover:underline"
                          title="Показать только каналы этого объекта"
                        >
                          {objectNameById.get(c.object_id) ?? `#${c.object_id}`}
                        </button>
                        <Link
                          to={`/risks?object_id=${c.object_id}`}
                          className="text-sm text-slate-400 hover:text-sky-700 hover:underline"
                          title="Показать риски по этому объекту"
                        >
                          риски
                        </Link>
                      </span>
                    ) : (
                      "не сопоставлен"
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{c.location_tag ?? "—"}</td>
                  <td className="px-4 py-3">
                    {c.degradation_trend ? <DegradationTrendBadge trend={c.degradation_trend} /> : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination
            page={channels.page}
            pageSize={channels.pageSize}
            total={channels.total}
            loadedCount={channels.data?.length ?? 0}
            onPageChange={channels.setPage}
          />
        </div>
      </DataState>
    </div>
  );
}
