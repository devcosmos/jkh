import { useState } from "react";
import { login } from "../api/client";

export function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
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
    <div className="login-screen">
      <form className="login-form" onSubmit={handleSubmit}>
        <h1>ЖКХ — вход диспетчера</h1>
        <label>
          Логин
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoFocus />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>
        {error && <div className="state state-error">{error}</div>}
        <button type="submit" disabled={submitting || !username || !password}>
          {submitting ? "Вход…" : "Войти"}
        </button>
      </form>
    </div>
  );
}
