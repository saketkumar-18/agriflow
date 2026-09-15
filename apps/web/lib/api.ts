// Single typed API client for the AgriFlow backend (docs/api-contract.md).
// - Bearer auth from localStorage, redirect to /login on 401.
// - Errors normalized to ApiError (contract error shape).
// - Writes while offline are queued via lib/queue instead of throwing.

import { STORAGE_KEYS, lsGet, lsSet, lsRemove } from "@/lib/storage";
import type { ApiErrorBody, LoginResponse, User } from "@/lib/types";

export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

const V1 = `${API_BASE}/api/v1`;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** i18n key a UI can translate for this error. */
  get i18nKey(): string {
    if (this.code.startsWith("errors.")) return this.code;
    switch (this.status) {
      case 401:
        return "errors.unauthorized";
      case 403:
        return "errors.forbidden";
      case 404:
        return "errors.not_found";
      case 422:
        return "errors.validation";
      case 429:
        return "errors.rate_limited";
      default:
        return this.status >= 500 ? "errors.server" : "errors.generic";
    }
  }
}

export class NetworkError extends Error {
  constructor(message = "Network unreachable") {
    super(message);
    this.name = "NetworkError";
  }
}

// ---------- auth token/session ----------

export function getToken(): string | null {
  return lsGet(STORAGE_KEYS.token);
}

export function setSession(token: string, user: User): void {
  lsSet(STORAGE_KEYS.token, token);
  lsSet(STORAGE_KEYS.user, JSON.stringify(user));
}

export function clearSession(): void {
  lsRemove(STORAGE_KEYS.token);
  lsRemove(STORAGE_KEYS.user);
}

export function getCachedUser(): User | null {
  const raw = lsGet(STORAGE_KEYS.user);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function isLoggedIn(): boolean {
  return getToken() != null;
}

let redirecting = false;

function redirectToLogin(): void {
  if (typeof window === "undefined" || redirecting) return;
  redirecting = true;
  clearSession();
  const next = encodeURIComponent(window.location.pathname + window.location.search);
  window.location.href = `/login?next=${next}`;
}

// ---------- core fetch wrapper ----------

export interface FetchOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  /** Attach Authorization header (default true). */
  auth?: boolean;
  /** Redirect to /login on 401 (default true for authed calls). */
  retryOn401?: boolean;
  signal?: AbortSignal;
  /** Set true on replayed queued actions to avoid re-queueing loops. */
  skipQueue?: boolean;
}

export async function apiFetch<T>(path: string, opts: FetchOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true, retryOn401 = true, signal } = opts;
  const url = path.startsWith("/api/health") ? `${API_BASE}${path}` : `${V1}${path}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new NetworkError(e instanceof Error ? e.message : "Network error");
  }

  if (res.status === 401 && auth && retryOn401) {
    redirectToLogin();
    throw new ApiError(401, "auth.unauthorized", "Session expired");
  }

  if (res.status === 204) return undefined as T;

  let data: unknown = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }

  if (!res.ok) {
    const errBody = data as ApiErrorBody | null;
    const code = errBody?.error?.code ?? `http.${res.status}`;
    const message = errBody?.error?.message ?? res.statusText;
    const details = errBody?.error?.details ?? null;
    throw new ApiError(res.status, code, message, details);
  }
  return data as T;
}

// ---------- offline-aware write helper ----------

/**
 * Perform a write; if offline (navigator.onLine === false), enqueue for
 * /sync/batch replay instead of throwing. Returns { queued: true } or the
 * server response.
 */
export async function writeWithQueue<T>(
  type: "irrigation_event" | "reading" | "feedback",
  path: string,
  body: Record<string, unknown>,
  idempotencyKey: string,
): Promise<{ queued: true } | { queued: false; data: T }> {
  if (typeof navigator !== "undefined" && !navigator.onLine) {
    const { enqueueAction } = await import("@/lib/queue");
    enqueueAction(type, { ...body, idempotency_key: idempotencyKey });
    return { queued: true };
  }
  try {
    const data = await apiFetch<T>(path, { method: "POST", body });
    return { queued: false, data };
  } catch (e) {
    if (e instanceof NetworkError) {
      const { enqueueAction } = await import("@/lib/queue");
      enqueueAction(type, { ...body, idempotency_key: idempotencyKey });
      return { queued: true };
    }
    throw e;
  }
}

// ---------- typed endpoint functions ----------

import type {
  AdminStats,
  Advisory,
  AgronomistFarm,
  AppNotification,
  Crop,
  Farm,
  FarmAnalytics,
  Field,
  FieldDetail,
  HealthResponse,
  IrrigationEvent,
  IrrigationEventCreate,
  NotificationPreferences,
  Paginated,
  Reading,
  Recommendation,
  SoilType,
  WaterOverTimePoint,
} from "@/lib/types";

export const api = {
  health: () => apiFetch<HealthResponse>("/api/health", { auth: false, retryOn401: false }),

  register: (input: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    language?: string;
  }) => apiFetch<LoginResponse>("/auth/register", { method: "POST", body: input, auth: false, retryOn401: false }),

  login: (email: string, password: string) =>
    apiFetch<LoginResponse>("/auth/login", { method: "POST", body: { email, password }, auth: false, retryOn401: false }),

  me: () => apiFetch<User>("/auth/me"),
  savePreferences: (p: NotificationPreferences) =>
    apiFetch<NotificationPreferences>("/auth/me/preferences", { method: "PUT", body: p }),

  listFarms: (page = 1) => apiFetch<Paginated<Farm>>(`/farms?page=${page}`),
  createFarm: (input: {
    name: string;
    location_text?: string;
    latitude?: number;
    longitude?: number;
    total_area?: number;
    area_unit: "ha" | "acre";
  }) => apiFetch<Farm>("/farms", { method: "POST", body: input }),
  getFarm: (id: number | string) => apiFetch<Farm>(`/farms/${id}`),
  farmSummary: (id: number | string) =>
    apiFetch<import("@/lib/types").FarmSummary>(`/farms/${id}/summary`),

  createField: (
    farmId: number | string,
    input: {
      name: string;
      area: number;
      area_unit: "ha" | "acre";
      soil_type_id: number;
      crop_id: number;
      growth_stage_code: string;
      irrigation_method: Field["irrigation_method"];
      water_source?: string;
    },
  ) => apiFetch<Field>(`/farms/${farmId}/fields`, { method: "POST", body: input }),
  getField: (id: number | string) => apiFetch<Field>(`/fields/${id}`),
  fieldDetail: (id: number | string) => apiFetch<FieldDetail>(`/fields/${id}/detail`),
  fieldHistory: (id: number | string, days = 30) =>
    apiFetch<import("@/lib/types").HistoryResponse>(`/fields/${id}/history?days=${days}`),

  crops: () => apiFetch<Crop[]>("/crops"),
  soilTypes: () => apiFetch<SoilType[]>("/soil-types"),

  weatherForField: (fieldId: number | string) =>
    apiFetch<import("@/lib/types").WeatherResponse>(`/weather/field/${fieldId}`),

  addReading: (fieldId: number | string, input: { soil_moisture_pct: number; taken_at?: string }) =>
    apiFetch<Reading>(`/fields/${fieldId}/readings`, { method: "POST", body: input }),
  readings: (fieldId: number | string, limit = 50) =>
    apiFetch<Reading[]>(`/fields/${fieldId}/readings?limit=${limit}`),

  recommendation: (fieldId: number | string) =>
    apiFetch<Recommendation>(`/recommendations/field/${fieldId}`),
  refreshRecommendation: (fieldId: number | string) =>
    apiFetch<Recommendation>(`/recommendations/field/${fieldId}/refresh`, { method: "POST" }),
  recommendationHistory: (fieldId: number | string, limit = 20) =>
    apiFetch<Recommendation[]>(`/recommendations/field/${fieldId}/history?limit=${limit}`),
  overrideRecommendation: (id: number | string, input: { action: "defer" | "approve" | "cancel"; reason: string }) =>
    apiFetch<Recommendation>(`/recommendations/${id}/override`, { method: "POST", body: input }),

  recordIrrigation: (input: IrrigationEventCreate) =>
    apiFetch<IrrigationEvent>("/irrigation-events", { method: "POST", body: input }),
  irrigationEvents: (params: { field_id?: number; farm_id?: number; page?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.field_id) q.set("field_id", String(params.field_id));
    if (params.farm_id) q.set("farm_id", String(params.farm_id));
    q.set("page", String(params.page ?? 1));
    return apiFetch<Paginated<IrrigationEvent>>(`/irrigation-events?${q.toString()}`);
  },

  sendFeedback: (input: { recommendation_id: number; useful: boolean | null; comment?: string }) =>
    apiFetch<unknown>("/feedback", { method: "POST", body: input }),

  notifications: (unreadOnly = false, page = 1) =>
    apiFetch<Paginated<AppNotification>>(`/notifications?${unreadOnly ? "unread=true&" : ""}page=${page}`),
  markNotificationRead: (id: number) => apiFetch<unknown>(`/notifications/${id}/read`, { method: "POST" }),
  markAllNotificationsRead: () => apiFetch<unknown>("/notifications/read-all", { method: "POST" }),

  analytics: (farmId: number | string, month: string) =>
    apiFetch<FarmAnalytics>(`/analytics/farm/${farmId}?month=${month}`),
  waterOverTime: (farmId: number | string, days = 90) =>
    apiFetch<WaterOverTimePoint[]>(`/analytics/farm/${farmId}/water-over-time?days=${days}`),

  agronomistFarms: () => apiFetch<AgronomistFarm[]>("/agronomist/farms"),
  advisories: (fieldId: number | string) => apiFetch<Advisory[]>(`/fields/${fieldId}/advisories`),
  addAdvisory: (field_id: number, note: string) =>
    apiFetch<Advisory>("/advisories", { method: "POST", body: { field_id, note } }),

  adminUsers: (params: { role?: string; page?: number } = {}) => {
    const q = new URLSearchParams();
    if (params.role) q.set("role", params.role);
    q.set("page", String(params.page ?? 1));
    return apiFetch<Paginated<User>>(`/admin/users?${q.toString()}`);
  },
  adminPatchUser: (id: number, input: { role?: User["role"]; is_active?: boolean }) =>
    apiFetch<User>(`/admin/users/${id}`, { method: "PATCH", body: input }),
  adminStats: () => apiFetch<AdminStats>("/admin/stats"),
  adminAudit: (page = 1) => apiFetch<Paginated<import("@/lib/types").AuditLog>>(`/admin/audit?page=${page}`),
  assignAgronomist: (farmId: number | string, user_id: number) =>
    apiFetch<unknown>(`/admin/farms/${farmId}/assign-agronomist`, { method: "POST", body: { user_id } }),
};
