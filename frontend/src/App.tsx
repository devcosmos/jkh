import { useState } from "react";
import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { clearSession, getRole, getToken } from "./api/client";
import { LoginPage } from "./pages/LoginPage";
import { RisksPage } from "./pages/RisksPage";
import { JournalPage } from "./pages/JournalPage";
import { RequestsPage } from "./pages/RequestsPage";

export function App() {
  const [authed, setAuthed] = useState(!!getToken());

  if (!authed) {
    return <LoginPage onLoggedIn={() => setAuthed(true)} />;
  }

  function logout() {
    clearSession();
    setAuthed(false);
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>ЖКХ — «Отказ датчика»</h1>
        <nav>
          <NavLink to="/risks" className={({ isActive }) => (isActive ? "active" : "")}>
            Риски
          </NavLink>
          <NavLink to="/journal" className={({ isActive }) => (isActive ? "active" : "")}>
            Журнал
          </NavLink>
          <NavLink to="/requests" className={({ isActive }) => (isActive ? "active" : "")}>
            Заявки
          </NavLink>
        </nav>
        <div className="user-badge">
          Роль: {getRole()}
          <button onClick={logout}>Выйти</button>
        </div>
      </header>
      <main>
        <Routes>
          <Route path="/risks" element={<RisksPage />} />
          <Route path="/journal" element={<JournalPage />} />
          <Route path="/requests" element={<RequestsPage />} />
          <Route path="*" element={<Navigate to="/risks" replace />} />
        </Routes>
      </main>
    </div>
  );
}
