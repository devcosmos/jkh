import { useState } from "react";
import { login } from "../api/client";

// Демо-доступ прямо в форме — это тестовый проект без реальных данных (хакатон-демо),
// смотрящему не нужно отдельно запрашивать логин/пароль, а факт наличия авторизации всё
// равно виден на этом экране.
const DEMO_USERNAME = "admin";
const DEMO_PASSWORD = "demo-local-2026";

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState(DEMO_USERNAME);
  const [password, setPassword] = useState(DEMO_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
      onLoggedIn();
    } catch {
      setError("Неверный логин или пароль");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-navy-950 px-4">
      <div
        className="pointer-events-none absolute -top-40 left-1/2 h-130 w-205 -translate-x-1/2 rounded-full opacity-40 blur-3xl"
        style={{ background: "radial-gradient(closest-side, #0ea5e9, transparent)" }}
      />
      <div className="pointer-events-none absolute inset-0 bg-linear-to-b from-transparent via-navy-950/60 to-navy-950" />

      <div className="relative w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-400">
            <svg viewBox="0 0 24 24" fill="none" className="h-6 w-6">
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
            <h1 className="font-display text-xl font-semibold text-white">ЖКХ Прогноз</h1>
            <p className="mt-1 text-sm text-slate-400">Вход диспетчера</p>
          </div>
        </div>

        <form
          className="flex flex-col gap-4 rounded-3xl border border-white/10 bg-white p-7 shadow-2xl shadow-black/40"
          onSubmit={handleSubmit}
        >
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-600">Логин</span>
            <input
              className="rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-sm font-medium text-slate-600">Пароль</span>
            <input
              className="rounded-xl border border-slate-200 px-3.5 py-2.5 text-sm text-slate-900 outline-none transition-colors focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <div className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm font-medium text-red-600">{error}</div>
          )}
          <button
            type="submit"
            disabled={submitting || !username || !password}
            className="mt-1 rounded-xl bg-sky-500 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400"
          >
            {submitting ? "Вход…" : "Войти"}
          </button>
          <p className="text-center text-sm text-slate-400">
            Демо-доступ: {DEMO_USERNAME} / {DEMO_PASSWORD} — поля уже заполнены
          </p>
        </form>
      </div>
    </div>
  );
}
