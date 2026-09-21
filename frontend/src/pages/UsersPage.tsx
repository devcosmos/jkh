import { useMemo, useState } from "react";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { Badge } from "../components/Badge";
import { DataState } from "../components/DataState";
import { Select } from "../components/Select";
import type { ObjectOut, UserOut, UserRole } from "../api/types";

const ROLE_LABELS: Record<UserRole, string> = {
  admin: "Администратор",
  dispatcher: "Диспетчер",
  analyst: "Аналитик",
};

export function UsersPage() {
  const users = useApi<UserOut[]>(() => api.get("/access/users"), []);
  const objects = useApi<ObjectOut[]>(() => api.get("/objects?limit=500"), []);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("dispatcher");
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const [grantSelection, setGrantSelection] = useState<Record<number, string>>({});
  const [busyUserId, setBusyUserId] = useState<number | null>(null);

  const objectNameById = useMemo(() => {
    const map = new Map<number, string>();
    objects.data?.forEach((o) => map.set(o.id, o.name));
    return map;
  }, [objects.data]);

  async function createUser() {
    setCreating(true);
    setCreateError(null);
    try {
      await api.post("/access/users", { username: newUsername, password: newPassword, role: newRole });
      setNewUsername("");
      setNewPassword("");
      users.reload();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  }

  async function grantAccess(userId: number) {
    const objectId = grantSelection[userId];
    if (!objectId) return;
    setBusyUserId(userId);
    try {
      await api.post(`/access/users/${userId}/objects`, { object_id: Number(objectId) });
      setGrantSelection((s) => ({ ...s, [userId]: "" }));
      users.reload();
    } finally {
      setBusyUserId(null);
    }
  }

  async function revokeAccess(userId: number, objectId: number) {
    setBusyUserId(userId);
    try {
      await api.delete(`/access/users/${userId}/objects/${objectId}`);
      users.reload();
    } finally {
      setBusyUserId(null);
    }
  }

  return (
    <div className="mx-auto max-w-[100rem] px-6 py-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-slate-900">Пользователи и доступ</h1>
        <p className="mt-1 text-sm text-slate-500">
          Роли и матрица доступа к объектам — у администратора ограничение не действует
        </p>
      </div>

      <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="mb-3 font-display text-sm font-semibold text-slate-900">Новый пользователь</h2>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-500">Логин</label>
            <input
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className="w-48 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-500">Пароль</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-48 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-sky-400 focus:ring-4 focus:ring-sky-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-500">Роль</label>
            <Select value={newRole} onChange={(e) => setNewRole(e.target.value as UserRole)}>
              {Object.entries(ROLE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
          </div>
          <button
            disabled={creating || !newUsername || newPassword.length < 8}
            onClick={createUser}
            className="rounded-xl bg-sky-500 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-sky-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Создать
          </button>
        </div>
        {newPassword && newPassword.length < 8 && (
          <p className="mt-2 text-sm text-slate-400">Пароль должен быть не короче 8 символов</p>
        )}
        {createError && <p className="mt-2 text-sm font-medium text-red-600">{createError}</p>}
      </section>

      <DataState loading={users.loading} error={users.error} empty={!users.data?.length} emptyText="Пользователей нет">
        <div className="space-y-4">
          {users.data?.map((u) => (
            <div key={u.id} className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-display text-sm font-semibold text-slate-900">{u.username}</span>
                  <span className="ml-2">
                    <Badge tone={u.role === "admin" ? "track-a" : "neutral"}>{ROLE_LABELS[u.role]}</Badge>
                  </span>
                  {!u.is_active && (
                    <span className="ml-2">
                      <Badge tone="critical">Отключён</Badge>
                    </span>
                  )}
                </div>
              </div>

              {u.role !== "admin" && (
                <div className="mt-3">
                  <div className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                    Доступ к объектам {u.object_ids.length === 0 && "(без ограничений — доступ ко всему)"}
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {u.object_ids.map((oid) => (
                      <span
                        key={oid}
                        className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pl-2.5 pr-1.5 text-sm font-medium text-slate-700"
                      >
                        {objectNameById.get(oid) ?? `#${oid}`}
                        <button
                          disabled={busyUserId === u.id}
                          onClick={() => revokeAccess(u.id, oid)}
                          className="flex h-4 w-4 items-center justify-center rounded-full text-slate-400 hover:bg-slate-200 hover:text-slate-700"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    <Select
                      value={grantSelection[u.id] ?? ""}
                      onChange={(e) => setGrantSelection((s) => ({ ...s, [u.id]: e.target.value }))}
                      className="!py-1.5 !text-sm"
                    >
                      <option value="">+ добавить объект…</option>
                      {objects.data
                        ?.filter((o) => !u.object_ids.includes(o.id))
                        .map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name}
                          </option>
                        ))}
                    </Select>
                    <button
                      disabled={busyUserId === u.id || !grantSelection[u.id]}
                      onClick={() => grantAccess(u.id)}
                      className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-sm font-medium text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Добавить
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </DataState>
    </div>
  );
}
