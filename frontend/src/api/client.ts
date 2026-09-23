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
    let detail: string = res.statusText;
    try {
      const body = await res.json();
      // detail у FastAPI — либо строка (наш HTTPException), либо список объектов ошибок
      // валидации ({type, loc, msg, input} на каждый невалидный параметр, см. 422). Раньше
      // объект/массив передавался в ApiError как есть — Error приводит message к строке
      // через ToString, и для объекта/массива объектов это буквально "[object Object]" —
      // отображалось на экране, а реальный текст ошибки был не виден нигде (ни на плашке,
      // ни в консоли).
      if (Array.isArray(body.detail)) {
        detail = body.detail.map((e: { loc?: unknown[]; msg?: string }) => `${e.loc?.join(".") ?? "?"}: ${e.msg ?? e}`).join("; ");
      } else if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (body.detail != null) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      /* тело не JSON — оставляем statusText */
    }
    // eslint-disable-next-line no-console
    console.error(`API ${res.status} ${path}:`, detail);
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
  // Файловые экспорты (XLSX/PDF) — защищённые эндпоинты, обычная ссылка <a href> не
  // отправит Authorization-заголовок, поэтому скачиваем как blob через fetch.
  downloadFile: async (path: string, filename: string): Promise<void> => {
    const res = await requestRaw(path);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
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
