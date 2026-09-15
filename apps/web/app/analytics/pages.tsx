"use client";

// /analytics — farm water usage, month view.

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { demoAnalytics, demoFarmSummary } from "@/lib/fixtures";
import { BarChart } from "@/components/charts";
import { Card, CardHeader, CardSkeleton, DemoBanner, EmptyState, ErrorState, Select } from "@/components/ui";
import { currentMonth, fmtNumber } from "@/lib/format";

export function AnalyticsPage() {
  const { t } = useI18n();
  const [farmId, setFarmId] = useState<string>("");
  const [month, setMonth] = useState(currentMonth());

  const farms = useApi(() => api.listFarms(1), { demoFallback: () => ({ items: [demoFarmSummary.farm], page: 1, page_size: 20, total: 1 }) });
  const chosen = farmId || farms.data?.items[0]?.id?.toString() || "";
  const data = useApi(chosen ? () => api.analytics(chosen, month) : null, { deps: [chosen, month], demoFallback: () => demoAnalytics });

  if (farms.status === "error") return <ErrorState error={farms.error} onRetry={farms.reload} />;
  if (farms.status === "loading" || !farms.data?.items.length) {
    return (
      <div className="space-y-3" aria-busy="true">
        <CardSkeleton />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("analytics.title")}</h1>
      {data.demo ? <DemoBanner /> : null}
      <Card className="p-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="farm" className="mb-1 block text-sm font-medium text-slate-800">{t("farm.title")}</label>
            <Select id="farm" value={chosen} onChange={(e) => setFarmId(e.target.value)}>
              {farms.data.items.map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </Select>
          </div>
          <div>
            <label htmlFor="month" className="mb-1 block text-sm font-medium text-slate-800">{t("analytics.month")}</label>
            <Select id="month" value={month} onChange={(e) => setMonth(e.target.value)}>
              {monthOptions().map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </Select>
          </div>
        </div>
      </Card>

      {data.status === "loading" ? (
        <div className="space-y-3" aria-busy="true"><CardSkeleton /><CardSkeleton /></div>
      ) : data.status === "error" ? (
        <ErrorState error={data.error} onRetry={data.reload} />
      ) : !data.data ? (
        <EmptyState icon="📊" title={t("analytics.noData")} />
      ) : (
        <>
          <div className="grid grid-cols-3 gap-2">
            <Stat label={t("analytics.totalIrrigated")} value={fmtNumber(data.data.total_irrigation_liters / 1000, 1)} unit="k L" tone="text-sky-700" />
            <Stat label={t("analytics.totalRecommended")} value={fmtNumber(data.data.recommended_liters / 1000, 1)} unit="k L" tone="text-emerald-700" />
            <Stat label={t("analytics.potentialDifference")} value={fmtNumber(data.data.potential_difference_liters / 1000, 1)} unit="k L" tone={data.data.potential_difference_liters > 0 ? "text-amber-700" : "text-emerald-700"} />
          </div>
          <p className="rounded-lg bg-white px-4 py-3 text-sm text-slate-700 ring-1 ring-slate-200">
            💡 {t(data.data.wording_key, { value: fmtNumber(Math.abs(data.data.potential_difference_liters), 0) })}
          </p>
          <p className="text-xs text-slate-500">{t("analytics.eventsCount", { count: data.data.events_count })}</p>
          <Card>
            <CardHeader title={t("analytics.weekly")} />
            <div className="px-4 pb-4">
              {data.data.weekly.length ? (
                <BarChart
                  title={t("analytics.weekly")}
                  unit="L"
                  points={data.data.weekly.map((w) => ({ label: w.week.slice(5), value: w.irrigated_liters / 1000 }))}
                />
              ) : (
                <p className="text-sm text-slate-500">{t("analytics.noData")}</p>
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}

function Stat({ label, value, unit, tone }: { label: string; value: string; unit: string; tone: string }) {
  return (
    <Card className="p-3 text-center">
      <p className={`text-xl font-extrabold ${tone}`}>{value}<span className="text-xs font-semibold"> {unit}</span></p>
      <p className="mt-0.5 text-[11px] font-medium text-slate-500">{label}</p>
    </Card>
  );
}

function monthOptions(): string[] {
  const out: string[] = [];
  const d = new Date();
  for (let i = 0; i < 6; i++) {
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
    d.setMonth(d.getMonth() - 1);
  }
  return out;
}
