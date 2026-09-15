// Hand-rolled accessible UI primitives (no component library).

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { ApiError, NetworkError } from "@/lib/api";

// ---------- Card ----------

export function Card({
  children,
  className = "",
  as: As = "div",
}: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "section" | "article" | "li";
}) {
  return (
    <As className={`rounded-2xl border border-slate-200 bg-white shadow-sm ${className}`}>
      {children}
    </As>
  );
}

export function CardHeader({ title, action }: { title: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2 px-4 pt-4 pb-2">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{title}</h2>
      {action}
    </div>
  );
}

// ---------- Button ----------

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

export function Button({
  children,
  variant = "primary",
  className = "",
  loading = false,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
}) {
  const base =
    "inline-flex min-h-[48px] items-center justify-center gap-2 rounded-xl px-4 text-base font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60";
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-emerald-700 text-white hover:bg-emerald-800",
    secondary: "bg-white text-slate-800 ring-1 ring-slate-300 hover:bg-slate-50",
    danger: "bg-red-700 text-white hover:bg-red-800",
    ghost: "bg-transparent text-emerald-800 hover:bg-emerald-50",
  };
  return (
    <button className={`${base} ${styles[variant]} ${className}`} disabled={loading || rest.disabled} {...rest}>
      {loading ? <Spinner /> : null}
      {children}
    </button>
  );
}

export function Spinner() {
  return (
    <span
      aria-hidden="true"
      className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent"
    />
  );
}

// ---------- Form fields ----------

export function Field({
  label,
  htmlFor,
  hint,
  error,
  required,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-800">
        {label}
        {required ? (
          <span aria-hidden="true" className="ml-0.5 text-red-700">
            *
          </span>
        ) : null}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${htmlFor}-hint`} className="text-xs text-slate-500">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${htmlFor}-error`} role="alert" className="text-sm font-medium text-red-700">
          {error}
        </p>
      ) : null}
    </div>
  );
}

const inputClass =
  "w-full min-h-[48px] rounded-xl border border-slate-300 bg-white px-3 py-2 text-base text-slate-900 placeholder:text-slate-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 aria-[invalid=true]:border-red-600";

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${inputClass} ${props.className ?? ""}`} />;
}

export function Checkbox({
  label,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  const id = rest.id ?? `cb-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <div className="flex items-center gap-3 py-2">
      <input
        type="checkbox"
        id={id}
        {...rest}
        className="h-6 w-6 rounded border-slate-300 text-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
      />
      <label htmlFor={id} className="text-base text-slate-800">
        {label}
      </label>
    </div>
  );
}

// ---------- Skeleton ----------

export function Skeleton({ className = "h-6 w-full" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded-lg bg-slate-200 ${className}`} />;
}

export function CardSkeleton() {
  return (
    <Card className="p-4">
      <Skeleton className="mb-3 h-5 w-1/3" />
      <Skeleton className="mb-2 h-4 w-full" />
      <Skeleton className="h-4 w-2/3" />
    </Card>
  );
}

// ---------- States ----------

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry?: () => void;
}) {
  const { t } = useI18n();
  let key = "errors.generic";
  if (error instanceof ApiError) key = error.i18nKey;
  else if (error instanceof NetworkError) key = "errors.network";
  return (
    <Card className="p-6 text-center">
      <div aria-hidden="true" className="mb-2 text-4xl">
        📡
      </div>
      <p className="mb-4 text-base text-slate-800">{t(key)}</p>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          {t("common.retry")}
        </Button>
      ) : null}
    </Card>
  );
}

export function EmptyState({
  icon = "🌱",
  title,
  hint,
  action,
}: {
  icon?: string;
  title: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className="p-8 text-center">
      <div aria-hidden="true" className="mb-3 text-5xl">
        {icon}
      </div>
      <h2 className="mb-1 text-lg font-semibold text-slate-900">{title}</h2>
      {hint ? <p className="mx-auto mb-4 max-w-sm text-sm text-slate-600">{hint}</p> : null}
      {action}
    </Card>
  );
}

export function Badge({
  children,
  className = "bg-slate-100 text-slate-800 ring-slate-300",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${className}`}>
      {children}
    </span>
  );
}

// ---------- Banners ----------

export function DemoBanner() {
  const { t } = useI18n();
  return (
    <div role="status" className="rounded-xl border-2 border-dashed border-amber-500 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-900">
      ⚠️ {t("common.demoBanner")}
    </div>
  );
}

export function OfflineBanner() {
  const { t } = useI18n();
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("offline", update);
    window.addEventListener("online", update);
    return () => {
      window.removeEventListener("offline", update);
      window.removeEventListener("online", update);
    };
  }, []);
  if (!offline) return null;
  return (
    <div role="status" className="rounded-xl bg-slate-800 px-4 py-3 text-sm font-medium text-white">
      📴 {t("common.offlineBanner")}
    </div>
  );
}

// ---------- Toasts (aria-live) ----------

interface ToastItem {
  id: number;
  message: string;
  tone: "success" | "error" | "info";
}

let pushToast: ((msg: string, tone: ToastItem["tone"]) => void) | null = null;
let counter = 0;

export function toast(message: string, tone: ToastItem["tone"] = "success") {
  pushToast?.(message, tone);
}

export function ToastRegion() {
  const [items, setItems] = useState<ToastItem[]>([]);
  const timers = useRef<Record<number, ReturnType<typeof setTimeout>>>({});

  const push = useCallback((message: string, tone: ToastItem["tone"]) => {
    const id = ++counter;
    setItems((prev) => [...prev.slice(-3), { id, message, tone }]);
    timers.current[id] = setTimeout(() => {
      setItems((prev) => prev.filter((x) => x.id !== id));
      delete timers.current[id];
    }, 4000);
  }, []);

  useEffect(() => {
    pushToast = push;
    return () => {
      pushToast = null;
    };
  }, [push]);

  useEffect(() => {
    const t = timers.current;
    return () => {
      Object.values(t).forEach(clearTimeout);
    };
  }, []);

  return (
    <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-20 z-50 flex flex-col items-center gap-2 px-4 md:bottom-4">
      {items.map((item) => (
        <div
          key={item.id}
          className={`pointer-events-auto w-full max-w-sm rounded-xl px-4 py-3 text-sm font-semibold text-white shadow-lg ${
            item.tone === "error" ? "bg-red-700" : item.tone === "info" ? "bg-slate-800" : "bg-emerald-700"
          }`}
        >
          {item.message}
        </div>
      ))}
    </div>
  );
}
