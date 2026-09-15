// Formatting helpers: dates, numbers, condition codes, urgency styling.

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function fmtDate(isoOrDay: string | null | undefined): string {
  if (!isoOrDay) return "—";
  const d = new Date(isoOrDay.length === 10 ? `${isoOrDay}T00:00:00` : isoOrDay);
  if (Number.isNaN(d.getTime())) return isoOrDay;
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

export function fmtShortDay(isoOrDay: string): string {
  const d = new Date(isoOrDay.length === 10 ? `${isoOrDay}T00:00:00` : isoOrDay);
  if (Number.isNaN(d.getTime())) return isoOrDay;
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric" });
}

export function relativeAge(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const hours = (Date.now() - then) / 3_600_000;
  if (hours < 1) return "now";
  if (hours < 24) return `${Math.round(hours)} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function fmtNumber(n: number | null | undefined, digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

export function fmtLiters(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1000) return `${fmtNumber(n / 1000, 1)}k L`;
  return `${fmtNumber(n, 0)} L`;
}

/** WMO condition code → emoji (paired with a text label — never emoji-only). */
export function conditionIcon(code: number): string {
  if (code === 0) return "☀️";
  if (code === 1) return "🌤️";
  if (code === 2) return "⛅";
  if (code === 3) return "☁️";
  if (code === 45 || code === 48) return "🌫️";
  if (code >= 51 && code <= 57) return "🌦️";
  if (code >= 61 && code <= 67) return "🌧️";
  if (code >= 71 && code <= 77) return "❄️";
  if (code >= 80 && code <= 82) return "🌧️";
  if (code >= 85 && code <= 86) return "🌨️";
  if (code >= 95) return "⛈️";
  return "🌡️";
}

export interface UrgencyStyle {
  /** Tailwind classes for the badge */
  badge: string;
  icon: string;
  /** used for CSS var-driven accents */
  hex: string;
}

export function urgencyStyle(u: string | null | undefined): UrgencyStyle {
  switch (u) {
    case "CRITICAL":
      return { badge: "bg-red-100 text-red-900 ring-red-300", icon: "🔥", hex: "#dc2626" };
    case "HIGH":
      return { badge: "bg-orange-100 text-orange-900 ring-orange-300", icon: "⚠️", hex: "#ea580c" };
    case "MEDIUM":
      return { badge: "bg-yellow-100 text-yellow-900 ring-yellow-300", icon: "❕", hex: "#ca8a04" };
    case "LOW":
      return { badge: "bg-emerald-100 text-emerald-900 ring-emerald-300", icon: "✓", hex: "#059669" };
    default:
      return { badge: "bg-slate-100 text-slate-800 ring-slate-300", icon: "•", hex: "#475569" };
  }
}

export function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
