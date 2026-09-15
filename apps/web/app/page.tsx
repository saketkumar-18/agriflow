// Dashboard — answers the #1 question in seconds.
"use client";

import Link from "next/link";
import { Protected } from "@/components/protected";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { demoFarmSummary } from "@/lib/fixtures";
import { IrrigationStatusCard } from "@/components/irrigation-status";
import { RainStrip, WeatherTile, SoilMoistureTile } from "@/components/weather-tiles";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  DemoBanner,
  EmptyState,
  ErrorState,
} from "@/components/ui";
import { fmtNumber, fmtShortDay } from "@/lib/format";

function Dashboard() {
  const { t } = useI18n();
  // Growth stage codes come from the API; prefer the shared i18n label,
  // fall back to the raw code (never crash on missing keys).
  const stageLabel = (code: string) => {
    const key = `crop.stage.${code}`;
    const out = t(key);
    return out === key ? code : out;
  };
  const farms = useApi(() => api.listFarms(1), { demoFallback: () => ({ items: [demoFarmSummary.farm], page: 1, page_size: 20, total: 1 }) });
  const farmId = farms.data?.items[0]?.id;
  const summary = useApi(farmId != null ? () => api.farmSummary(farmId) : null, {
    deps: [farmId],
    demoFallback: () => demoFarmSummary,
  });

  const farmsLoading = farms.status === "loading";
  if (farms.status === "error") return <ErrorState error={farms.error} onRetry={farms.reload} />;
  if (farmsLoading) {
    return (
      <div className="space-y-3" aria-busy="true">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  const farmList = farms.data?.items ?? [];
  if (farmList.length === 0) {
    return (
      <EmptyState
        icon="🚜"
        title={t("farm.noFarms")}
        hint={t("farm.noFarmsHint")}
        action={
          <Link href="/farms/new">
            <Button>{t("farm.addFarm")}</Button>
          </Link>
        }
      />
    );
  }

  if (summary.status === "error") return <ErrorState error={summary.error} onRetry={summary.reload} />;
  if (summary.status === "loading") {
    return (
      <div className="space-y-3" aria-busy="true">
        <CardSkeleton />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  }
  const s = summary.data;
  if (!s) return <ErrorState error={new Error("empty")} onRetry={summary.reload} />;

  // Pick the most urgent field for the hero card.
  const ranked = [...s.fields].sort((a, b) => rank(b.recommendation) - rank(a.recommendation));
  const hero = ranked[0];
  const rainDays =
    s.weather_snapshot?.available
      ? s.weather_snapshot.forecast.slice(0, 5).map((f) => f.rain_prob_pct)
      : [];
  const [bestIdx, bestProb] = rainDays.reduce<[number, number]>(
    (acc, p, i) => (p > acc[1] ? [i, p] : acc),
    [-1, 0],
  );

  return (
    <div className="space-y-3">
      {summary.demo ? <DemoBanner /> : null}
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-extrabold text-slate-900">{s.farm.name}</h1>
          <p className="text-xs text-slate-500">
            {t("farm.fieldCount", { count: s.fields.length })}
            {s.farm.demo ? ` · ${t("common.demoLabel")}` : ""}
          </p>
        </div>
        <Link href={`/farms/${s.farm.id}`} className="shrink-0 text-sm font-semibold text-emerald-800 underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
          {t("farm.farmDetails")}
        </Link>
      </div>

      {hero ? (
        <IrrigationStatusCard rec={hero.recommendation} fieldName={hero.name} fieldId={hero.id} />
      ) : (
        <Card className="p-6 text-center">
          <p className="text-lg font-semibold text-slate-700">{t("irrigation.noRecommendation")}</p>
          <p className="mt-1 text-sm text-slate-500">{t("irrigation.noRecommendationHint")}</p>
        </Card>
      )}

      {bestIdx >= 0 && bestProb >= 40 ? (
        <p role="status" className="rounded-xl bg-sky-600 px-4 py-3 text-base font-bold text-white">
          ☔ {t("weather.rainTomorrow", { prob: bestProb })}
        </p>
      ) : null}

      <RainStrip weather={s.weather_snapshot} />

      <div className="grid gap-3 sm:grid-cols-2">
        <WeatherTile weather={s.weather_snapshot} />
        <SoilMoistureTile
          value={hero?.soil_moisture?.value}
          source={hero?.soil_moisture?.source}
          ageHours={hero?.soil_moisture?.age_hours}
          target={45}
          wilting={18}
        />
      </div>

      {ranked.length > 1 ? (
        <ul className="space-y-2">
          {ranked.map((f) => (
            <li key={f.id}>
              <Link href={`/fields/${f.id}`} className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
                <Card className="p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-bold text-slate-900">{f.name}</p>
                      <p className="text-xs text-slate-500">
                        {f.crop_name} · {stageLabel(f.growth_stage)}
                        {f.soil_moisture ? ` · 💧${t("soil.moistureValue", { value: fmtNumber(f.soil_moisture.value, 0) })}` : ""}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge
                        className={
                          f.status === "needs_irrigation"
                            ? "bg-sky-100 text-sky-900 ring-sky-300"
                            : f.status === "ok"
                              ? "bg-emerald-100 text-emerald-900 ring-emerald-300"
                              : "bg-slate-100 text-slate-700 ring-slate-300"
                        }
                      >
                        {f.status === "needs_irrigation" ? "💧" : f.status === "ok" ? "✅" : "⏸️"} {t(`status.${f.status}`)}
                      </Badge>
                      {f.recommendation?.demo ? <Badge className="bg-amber-100 text-amber-900 ring-amber-300">{t("common.demoLabel")}</Badge> : null}
                    </div>
                  </div>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex gap-2">
        <Link href="/fields/new" className="flex-1">
          <Button variant="secondary" className="w-full">
            {t("field.addField")}
          </Button>
        </Link>
        {ranked[0] ? (
          <Link href={`/fields/${ranked[0].id}/record-irrigation`} className="flex-1">
            <Button variant="secondary" className="w-full">
              {t("field.recordIrrigation")}
            </Button>
          </Link>
        ) : null}
      </div>

      {s.weather_snapshot?.available && (s.weather_snapshot.forecast?.length ?? 0) > 0 && bestIdx >= 0 ? (
        <p className="text-center text-xs text-slate-400">
          {t("weather.next5days")}: {fmtShortDay(s.weather_snapshot.forecast[0].day)} → {fmtShortDay(s.weather_snapshot.forecast[Math.min(4, s.weather_snapshot.forecast.length - 1)].day)}
        </p>
      ) : null}
    </div>
  );
}

function rank(rec: { irrigation_needed: boolean; urgency: string } | null): number {
  if (!rec) return 0;
  const order: Record<string, number> = { CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1 };
  return rec.irrigation_needed ? (order[rec.urgency] ?? 0) : -1;
}

export default function HomePage() {
  return (
    <Protected>
      <Dashboard />
    </Protected>
  );
}
