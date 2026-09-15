// Small localStorage helpers (SSR-safe).

export function lsGet(key: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function lsSet(key: string, value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // storage unavailable (private mode etc.) — degrade silently
  }
}

export function lsRemove(key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* noop */
  }
}

export function lsGetJson<T>(key: string, fallback: T): T {
  const raw = lsGet(key);
  if (raw == null) return fallback;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function lsSetJson(key: string, value: unknown): void {
  lsSet(key, JSON.stringify(value));
}

export const STORAGE_KEYS = {
  token: "agriflow.token",
  user: "agriflow.user",
  lang: "agriflow.lang",
  queue: "agriflow.queue.v1",
} as const;
