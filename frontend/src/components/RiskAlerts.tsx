import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { RiskCaseOut } from "../api/types";

const POLL_INTERVAL_MS = 30_000;
const TOAST_TTL_MS = 12_000;

/** Раздел 10 ТЗ требует «уведомление пользователей о критических инцидентах в режиме
 * реального времени». Организаторы подтвердили (тема 13 CSV), что периодический опрос
 * вместо push/WebSocket допустим, «если удобно и не замедляет систему» — поэтому здесь
 * лёгкий поллинг новых критических риск-кейсов, а не отдельная инфраструктура сокетов. */
export function useCriticalRiskCount(enabled: boolean): number | null {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    async function poll() {
      try {
        const { total } = await api.getPage<RiskCaseOut>(
          "/risk-cases?status=new&priority=high&limit=1"
        );
        if (!cancelled) setCount(total ?? 0);
      } catch {
        // Тихо игнорируем — счётчик просто не обновится в этот раз, не критично для UI.
      }
    }
    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [enabled]);
  return count;
}

interface Toast {
  id: number;
  risk: RiskCaseOut;
}

export function RiskAlerts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seenIds = useRef<Set<number> | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const { items } = await api.getPage<RiskCaseOut>(
          "/risk-cases?status=new&priority=high&limit=10&sort_by=opened_at&sort_dir=desc"
        );
        if (cancelled) return;
        if (seenIds.current === null) {
          // Первый опрос — просто запоминаем уже открытые критические риски как базовую
          // линию, чтобы не засыпать диспетчера уведомлениями обо всём сразу при заходе.
          seenIds.current = new Set(items.map((r) => r.id));
          return;
        }
        const fresh = items.filter((r) => !seenIds.current!.has(r.id));
        fresh.forEach((r) => seenIds.current!.add(r.id));
        if (fresh.length > 0) {
          setToasts((prev) => [...prev, ...fresh.map((risk) => ({ id: risk.id, risk }))]);
        }
      } catch {
        // Пропускаем неудачный опрос — попробуем на следующем тике.
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  function dismiss(id: number) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  function open(risk: RiskCaseOut) {
    dismiss(risk.id);
    navigate(`/risks?risk_case_id=${risk.id}`);
  }

  if (toasts.length === 0) return null;

  return (
    <div className="fixed right-4 top-4 z-50 flex w-80 flex-col gap-2.5">
      {toasts.map((t) => (
        <ToastCard key={t.id} risk={t.risk} onOpen={() => open(t.risk)} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  );
}

function ToastCard({ risk, onOpen, onDismiss }: { risk: RiskCaseOut; onOpen: () => void; onDismiss: () => void }) {
  useEffect(() => {
    const id = setTimeout(onDismiss, TOAST_TTL_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-white p-3.5 shadow-lg">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-red-50 text-red-600">
        <BellIcon className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-slate-900">Новый критический риск</div>
        <div className="mt-0.5 truncate text-sm text-slate-500">
          Канал {risk.channel_label ?? `#${risk.channel_id}`}
        </div>
        <button onClick={onOpen} className="mt-1.5 text-sm font-semibold text-sky-700 hover:underline">
          Открыть риск-кейс →
        </button>
      </div>
      <button
        onClick={onDismiss}
        className="shrink-0 text-slate-300 hover:text-slate-500"
        aria-label="Закрыть уведомление"
      >
        <CloseIcon className="h-4 w-4" />
      </button>
    </div>
  );
}

function BellIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M6 10a6 6 0 1 1 12 0c0 3.4 1 5 1.6 5.8H4.4C5 15 6 13.4 6 10Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M9.5 18.5a2.5 2.5 0 0 0 5 0" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function CloseIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
