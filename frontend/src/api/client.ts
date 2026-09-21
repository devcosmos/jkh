const TOKEN_KEY = "jkh_token";
const ROLE_KEY = "jkh_role";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRole(): string | null {
  return localStorage.getItem(ROLE_KEY);
}

export function setSession(token: string, role: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(ROLE_KEY, role);
}

export function clearSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ROLE_KEY);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
  }
}

async function requestRaw(path: string, init?: RequestInit): Promise<Response> {
  const token = getToken();
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !(init.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`/api${path}`, { ...init, headers });
  if (res.status === 401) {
    clearSession();
    throw new ApiError(401, "Сессия истекла — войдите заново");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* тело не JSON — оставляем statusText */
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await requestRaw(path, init);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  // Списковые эндпоинты отдают общее число строк (без учёта limit/offset) в заголовке
  // X-Total-Count — нужен для постраничной навигации (см. usePagedApi).
  getPage: async <T>(path: string): Promise<{ items: T[]; total: number | null }> => {
    const res = await requestRaw(path);
    const items = (await res.json()) as T[];
    const totalHeader = res.headers.get("X-Total-Count");
    return { items, total: totalHeader !== null ? Number(totalHeader) : null };
  },
};

export async function login(username: string, password: string): Promise<{ role: string }> {
  const body = new URLSearchParams({ username, password });
  const res = await fetch("/api/auth/login", { method: "POST", body });
  if (!res.ok) {
    throw new ApiError(res.status, "Неверный логин или пароль");
  }
  const data = await res.json();
  setSession(data.access_token, data.role);
  return { role: data.role };
}
