// Offline action queue: writes made while navigator.onLine === false are
// stored in localStorage with an idempotency key and flushed via
// POST /sync/batch when back online.

"use client";

import { STORAGE_KEYS, lsGetJson, lsSetJson } from "@/lib/storage";
import type { SyncAction, SyncActionType } from "@/lib/types";

export interface QueuedAction extends SyncAction {
  queued_at: string;
}

type Listener = () => void;

const listeners = new Set<Listener>();
let flushing = false;

function load(): QueuedAction[] {
  return lsGetJson<QueuedAction[]>(STORAGE_KEYS.queue, []);
}

function save(items: QueuedAction[]): void {
  lsSetJson(STORAGE_KEYS.queue, items);
  emit();
}

function emit(): void {
  for (const l of listeners) l();
}

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for non-secure contexts
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function queueLength(): number {
  return load().length;
}

export function getQueued(): QueuedAction[] {
  return load();
}

export function subscribeQueue(fn: Listener): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** Enqueue a write action. Returns the generated local_id / idempotency_key. */
export function enqueueAction(
  type: SyncActionType,
  payload: Record<string, unknown>,
): string {
  const local_id = uuid();
  const items = load();
  items.push({
    local_id,
    type,
    payload: { ...payload, idempotency_key: payload.idempotency_key ?? local_id },
    queued_at: new Date().toISOString(),
  });
  save(items);
  return local_id;
}

/** Flush the queue via POST /sync/batch. Safe to call repeatedly. */
export async function flushQueue(): Promise<{
  flushed: number;
  errors: number;
}> {
  if (flushing) return { flushed: 0, errors: 0 };
  if (typeof window === "undefined" || !navigator.onLine) {
    return { flushed: 0, errors: 0 };
  }
  const items = load();
  if (items.length === 0) return { flushed: 0, errors: 0 };
  flushing = true;
  try {
    const { apiFetch } = await import("@/lib/api");
    const res = await apiFetch<{ results: { local_id: string; status: string; error?: string | null }[] }>(
      "/sync/batch",
      { method: "POST", body: { actions: items.map(({ local_id, type, payload }) => ({ local_id, type, payload })) }, retryOn401: false },
    );
    let errors = 0;
    const done = new Set<string>();
    for (const r of res.results ?? []) {
      if (r.status === "created" || r.status === "duplicate") done.add(r.local_id);
    }
    const remaining = load().filter((i) => {
      const result = (res.results ?? []).find((r) => r.local_id === i.local_id);
      if (result && result.status === "error") {
        errors += 1;
        done.add(i.local_id); // drop hard errors after one attempt; surfaced to user
        return false;
      }
      return !done.has(i.local_id);
    });
    save(remaining);
    return { flushed: done.size - errors, errors };
  } catch {
    // Network still failing — keep queue intact; retried on next 'online' event.
    return { flushed: 0, errors: 0 };
  } finally {
    flushing = false;
  }
}

/** Install global online-listener that flushes the queue automatically. */
export function installQueueFlusher(): () => void {
  const onOnline = () => {
    void flushQueue().then((r) => {
      if (r.flushed > 0) {
        window.dispatchEvent(new CustomEvent("agriflow:queue-flushed", { detail: r }));
      }
    });
  };
  window.addEventListener("online", onOnline);
  // Also try once on mount (in case we loaded while already online).
  if (navigator.onLine) onOnline();
  return () => window.removeEventListener("online", onOnline);
}
