import { useState, type ReactElement } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { clearSession, getRole, getToken } from "./api/client";
import { RiskAlerts, useOpenRiskCount } from "./components/RiskAlerts";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { RisksPage } from "./pages/RisksPage";
import { JournalPage } from "./pages/JournalPage";
import { RequestsPage } from "./pages/RequestsPage";
import { ModelsPage } from "./pages/ModelsPage";
import { RegistryPage } from "./pages/RegistryPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { UsersPage } from "./pages/UsersPage";
import { HelpPage } from "./pages/HelpPage";

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  analyst: "Аналитик",
};

const NAV_ITEMS = [
  { to: "/dashboard", label: "Обзор", icon: DashboardIcon },
  { to: "/risks", label: "Риски", icon: WarningIcon },
  { to: "/journal", label: "Журнал", icon: JournalIcon },
  { to: "/requests", label: "Заявки", icon: RequestsIcon },
  { to: "/models", label: "Модели", icon: ModelsIcon },
  { to: "/registry", label: "Объекты и каналы", icon: RegistryIcon },
  { to: "/analytics", label: "Аналитика", icon: AnalyticsIcon },
  { to: "/help", label: "Справка", icon: HelpIcon },
];

const ADMIN_NAV_ITEMS = [
  { to: "/audit-log", label: "Журнал аудита", icon: AuditIcon },
  { to: "/users", label: "Пользователи", icon: UsersIcon },
];

export function App() {
  const [authed, setAuthed] = useState(!!getToken());
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const openRiskCount = useOpenRiskCount(authed);

  if (!authed) {
    return <LoginPage onLoggedIn={() => setAuthed(true)} />;
  }

  function logout() {
    clearSession();
    setAuthed(false);
  }

  const role = getRole();

  return (
    <div className="flex min-h-screen bg-slate-50">
      <RiskAlerts />
      {mobileNavOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/40 lg:hidden"
          onClick={() => setMobileNavOpen(false)}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 shrink-0 flex-col bg-navy-900 text-slate-200 transition-transform duration-200 lg:static lg:translate-x-0 ${
          mobileNavOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 px-5 py-6">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-sky-500/15 text-sky-400">
            <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
              <path
                d="M12 2 3 7v6c0 5 3.8 8.7 9 9 5.2-.3 9-4 9-9V7l-9-5Z"
                stroke="currentColor"
                strokeWidth="1.7"
                strokeLinejoin="round"
              />
              <path d="M9 12.5 11 14.5 15 10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="font-display text-sm font-semibold text-white">ЖКХ Прогноз</div>
            <div className="text-[11px] text-slate-400">Отказ датчика</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map((item) => (
            <NavItemLink
              key={item.to}
              {...item}
              badge={item.to === "/risks" ? openRiskCount : undefined}
              onNavigate={() => setMobileNavOpen(false)}
            />
          ))}
          {role === "admin" && (
            <>
              <div className="my-2 border-t border-white/10" />
              {ADMIN_NAV_ITEMS.map((item) => (
                <NavItemLink key={item.to} {...item} onNavigate={() => setMobileNavOpen(false)} />
              ))}
            </>
          )}
        </nav>

        <div className="border-t border-white/10 px-4 py-4">
          <div className="mb-3 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-700 text-xs font-semibold text-slate-200">
              {(role ?? "?").slice(0, 1).toUpperCase()}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-100">{ROLE_LABELS[role ?? ""] ?? role}</div>
              <div className="text-[11px] text-slate-500">jkh.devcosmos.ru</div>
            </div>
          </div>
          <button
            onClick={logout}
            className="w-full rounded-lg border border-white/10 px-3 py-2 text-left text-sm font-medium text-slate-300 transition-colors hover:bg-white/5 hover:text-white"
          >
            Выйти
          </button>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100"
            aria-label="Открыть меню"
          >
            <MenuIcon className="h-5 w-5" />
          </button>
          <span className="font-display text-sm font-semibold text-slate-900">ЖКХ Прогноз</span>
        </div>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/risks" element={<RisksPage />} />
          <Route path="/journal" element={<JournalPage />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/registry" element={<RegistryPage />} />
          <Route path="/analytics" element={<AnalyticsPage />} />
          <Route path="/help" element={<HelpPage />} />
          {role === "admin" && <Route path="/audit-log" element={<AuditLogPage />} />}
          {role === "admin" && <Route path="/users" element={<UsersPage />} />}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </main>
    </div>
  );
}

function NavItemLink({
  to,
  label,
  icon: Icon,
  badge,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: (p: { className?: string }) => ReactElement;
  badge?: number | null;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
      to={to}
      onClick={onNavigate}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
          isActive ? "bg-sky-500/15 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-100"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <Icon className={`h-4.5 w-4.5 ${isActive ? "text-sky-400" : "text-slate-500"}`} />
          <span className="flex-1">{label}</span>
          {!!badge && (
            <span className="rounded-full bg-red-500 px-1.5 py-0.5 text-[11px] font-semibold leading-none text-white">
              {badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

function WarningIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path
        d="M10.3 3.9 2.6 17a1.7 1.7 0 0 0 1.5 2.6h15.8a1.7 1.7 0 0 0 1.5-2.6L13.7 3.9a1.7 1.7 0 0 0-3 0Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
      <path d="M12 9.5v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M12 16.7h.01" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function JournalIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="4" y="3" width="16" height="18" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function RequestsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M9 3h6l1 3H8l1-3Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <rect x="5" y="6" width="14" height="15" rx="2" stroke="currentColor" strokeWidth="1.7" />
      <path d="m9 13 2 2 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function DashboardIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13" y="3.5" width="7.5" height="4.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13" y="10" width="7.5" height="10.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
      <rect x="3.5" y="13" width="7.5" height="7.5" rx="1.5" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function ModelsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="6" cy="6" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="18" cy="6" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="12" cy="18" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8 7.2 10.5 16M16 7.2 13.5 16M8.3 6h7.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function RegistryIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4 6a2 2 0 0 1 2-2h9l5 5v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M15 4v4a1 1 0 0 0 1 1h4" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M8 13h8M8 16.5h5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function AnalyticsIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4 20V10M10 20V4M16 20v-7M20 20V8" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AuditIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.7" />
      <path d="m20 20-4.3-4.3M8.5 11h5M11 8.5v5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function UsersIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.5 19c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="17.5" cy="8.5" r="2.3" stroke="currentColor" strokeWidth="1.7" />
      <path d="M15.5 14.2c2.4.3 4 2.1 4 4.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function HelpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.7" />
      <path
        d="M9.5 9.3a2.5 2.5 0 1 1 3.7 2.2c-.7.4-1.2.9-1.2 1.8v.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M12 17h.01" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

function MenuIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className}>
      <path d="M4 6h16M4 12h16M4 18h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
