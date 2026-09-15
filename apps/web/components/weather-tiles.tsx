// Rain forecast strip (highly visible, next 5 days), weather tile,
// soil moisture tile.

"use client";

import { useI18n } from "@/lib/i18n";
import type { WeatherResponse } from "@/lib/types";
import { Badge, Card, CardHeader, Skeleton } from "@/components/ui";
import { conditionIcon, fmtNumber } from "@/lib/format";

export function RainStrip({ weather }: { weather: WeatherResponse | null | undefined }) {
  const { t } = useI18n();
  if (!weather) {
    return (
      <Card>
        <CardHeader title={t("weather.next5days")} />
        <div className="flex gap-2 px-4 pb-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 flex-1" />
          ))}
        </div>
      </Card>
    );
  }
  if (!weather.available) {
    return (
      <Card className="p-4">
        <p className="text-sm font-semibold text-slate-500">{t("weather.next5days")}</p>
        <p className="mt-1 text-sm text-slate-600">
          ☂️ {t("weather.unavailable")} — {t(weather.reason)}
        </p>
      </Card>
    );
  }
  const days = weather.forecast.slice(0, 5);
  return (
    <Card>
      <CardHeader title={<span className="normal-case tracking-normal text-base font-bold text-slate-900">🌧️ {t("weather.next5days")}</span>} />
      <ul className="grid grid-cols-5 gap-2 px-4 pb-4" aria-label={t("weather.next5days")}>
        {days.map((d) => {
          const wd = new Date(`${d.day}T00:00:00`).toLocaleDateString(undefined, { weekday: "short" });
          const strong = d.rain_prob_pct >= 60 || d.rain_mm >= 8;
          return (
            <li
              key={d.day}
              className={`rounded-xl px-1.5 py-2.5 text-center ring-1 ring-black/5 ${strong ? "bg-sky-600 text-white" : "bg-sky-50 text-sky-950"}`}
            >
              <p className="text-[11px] font-bold uppercase">{wd}</p>
              <p className="my-0.5 text-xl leading-none" aria-hidden="true">
                {conditionIcon(d.condition_code)}
              </p>
              <p className="text-sm font-bold">{d.rain_prob_pct}%</p>
              <p className="text-[11px] opacity-90">{fmtNumber(d.rain_mm, 0)} mm</p>
              <p className="sr-only">
                {wd}: {d.rain_prob_pct}% rain probability, {d.rain_mm} mm
              </p>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export function WeatherTile({ weather }: { weather: WeatherResponse | null | undefined }) {
  const { t } = useI18n();
  if (!weather) {
    return (
      <Card className="p-4">
        <Skeleton className="mb-2 h-5 w-24" />
        <Skeleton className="h-10 w-32" />
      </Card>
    );
  }
  if (!weather.available) {
    return (
      <Card className="p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("weather.title")}</p>
        <p className="mt-1 text-sm text-slate-600">🌡️ {t("weather.unavailable_short")}</p>
        <p className="text-xs text-slate-500">{t(weather.reason)}</p>
      </Card>
    );
  }
  const c = weather.current;
  const desc = t(`condition.${c.condition_code}`);
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("weather.title")}</p>
          <p className="mt-0.5 text-2xl font-bold text-slate-900">
            {fmtNumber(c.temp_c, 0)}°C <span className="text-base font-medium text-slate-600">{desc}</span>
          </p>
        </div>
        <span aria-hidden="true" className="text-4xl">
          {conditionIcon(c.condition_code)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-2 text-xs">
        <Badge>💧 {t("weather.humidity", { pct: c.humidity_pct })}</Badge>
        <Badge>🌬️ {t("weather.wind", { kmh: c.wind_kmh })}</Badge>
        <Badge>🌧️ {t("weather.rainProb", { prob: c.rain_prob_pct })}</Badge>
      </div>
      {weather.alert ? (
        <p role="alert" className="mt-2 rounded-lg bg-orange-50 px-3 py-2 text-sm font-semibold text-orange-900 ring-1 ring-orange-300">
          ⚠️ {t(weather.alert.key, weather.alert.params ?? null)}
        </p>
      ) : null}
      <p className="mt-2 text-[11px] text-slate-400">
        {t("weather.recent7d", { mm: fmtNumber(weather.recent_rainfall_mm.last_7d, 1) })} · {t("weather.provider", { provider: weather.provider })}
      </p>
    </Card>
  );
}

export function SoilMoistureTile({
  value,
  source,
  ageHours,
  target,
  wilting,
}: {
  value: number | null | undefined;
  source?: string | null;
  ageHours?: number | null;
  target?: number | null;
  wilting?: number | null;
}) {
  const { t } = useI18n();
  const pct = value == null ? 0 : Math.max(0, Math.min(100, value));
  const tone =
    value == null
      ? "bg-slate-300"
      : value < (wilting ?? 20) + 8
        ? "bg-red-500"
        : value < (target ?? 45)
          ? "bg-amber-500"
          : "bg-emerald-600";
  return (
    <Card className="p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">🪨 {t("soil.moisture")}</p>
      {value == null ? (
        <p className="mt-1 text-sm text-slate-600">{t("soil.noReading")}</p>
      ) : (
        <>
          <p className="mt-0.5 text-2xl font-bold text-slate-900">{t("soil.moistureValue", { value: fmtNumber(value, 0) })}</p>
          <div
            role="meter"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t("soil.moisture")}
            className="mt-2 h-3 w-full overflow-hidden rounded-full bg-slate-100 ring-1 ring-slate-200"
          >
            <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-1 text-[11px] text-slate-500">
            <span>
              {source ? t(`soil.source${source === "sensor" ? "Sensor" : "Manual"}`) : ""}
              {ageHours != null ? ` · ${t("common.hoursAgo", { hours: Math.round(ageHours) })}` : ""}
            </span>
            {target != null || wilting != null ? (
              <span>{t("soil.moistureTarget", { target: fmtNumber(target ?? 0, 0), wilting: fmtNumber(wilting ?? 0, 0) })}</span>
            ) : null}
          </div>
        </>
      )}
    </Card>
  );
}
