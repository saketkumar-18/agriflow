"use client";

// Field pages: list, new (with ?farm=), detail (+ lazy-loaded charts).

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { demoCrops, demoSoilTypes } from "@/lib/fixtures";
import { IrrigationStatusCard } from "@/components/irrigation-status";
import { RainStrip, WeatherTile, SoilMoistureTile } from "@/components/weather-tiles";
import dynamic from "next/dynamic";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  DemoBanner,
  EmptyState,
  ErrorState,
  Field as FormField,
  Input,
  Select,
  Skeleton,
  toast,
} from "@/components/ui";
import { fmtNumber, relativeAge } from "@/lib/format";
import type { IrrigationMethod } from "@/lib/types";

// Charts are lazy-loaded so the dashboard/field pages stay light.
const LazyFieldCharts = dynamic(
  () => import("@/components/charts").then((m) => m.FieldCharts),
  {
    ssr: false,
    loading: () => (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    ),
  },
);

import { Suspense } from "react";
import type { HistoryResponse } from "@/lib/types";

function ChartsLoader({ fieldId }: { fieldId: number }) {
  const { t } = useI18n();
  const hist = useApi(() => api.fieldHistory(fieldId, 30), { deps: [fieldId] });
  if (hist.status === "loading")
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    );
  if (hist.status === "error") return <ErrorState error={hist.error} onRetry={hist.reload} />;
  const history = hist.data as HistoryResponse | null;
  if (!history) return <p className="text-sm text-slate-500">{t("common.noData")}</p>;
  return <LazyFieldCharts history={history} />;
}

// ---------- /fields (list) ----------

export function FieldsListPage() {
  const { t } = useI18n();
  const farms = useApi(() => api.listFarms(1), { demoFallback: () => ({ items: [], page: 1, page_size: 20, total: 0 }) });
  const farmId = farms.data?.items[0]?.id;
  const summary = useApi(farmId != null ? () => api.farmSummary(farmId) : null, { deps: [farmId] });

  if (farms.status === "error") return <ErrorState error={farms.error} onRetry={farms.reload} />;
  if (farms.status === "loading") return <div className="space-y-3" aria-busy="true"><CardSkeleton /></div>;
  if (!farmId) {
    return <EmptyState icon="🚜" title={t("farm.noFarms")} hint={t("farm.noFarmsHint")} action={<Link href="/farms/new"><Button>{t("farm.addFarm")}</Button></Link>} />;
  }
  if (summary.status === "loading") return <div className="space-y-3" aria-busy="true"><CardSkeleton /><CardSkeleton /></div>;
  if (summary.status === "error") return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const fields = summary.data?.fields ?? [];
  if (fields.length === 0) {
    return <EmptyState icon="🌾" title={t("field.noFields")} hint={t("field.noFieldsHint")} action={<Link href={`/fields/new?farm=${farmId}`}><Button>{t("field.addField")}</Button></Link>} />;
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-extrabold text-slate-900">{t("field.myFields")}</h1>
        <Link href="/fields/new"><Button variant="secondary">{t("field.addField")}</Button></Link>
      </div>
      <ul className="space-y-2">
        {fields.map((f) => (
          <li key={f.id}>
            <Link href={`/fields/${f.id}`} className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
              <Card className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-bold text-slate-900">{f.name}</p>
                    <p className="text-xs text-slate-500">
                      {f.crop_name} · {f.growth_stage}
                      {f.soil_moisture ? ` · ${t("soil.moisture")}: ${fmtNumber(f.soil_moisture.value, 0)}%` : ""}
                    </p>
                  </div>
                  <Badge className={f.status === "needs_irrigation" ? "bg-sky-100 text-sky-900 ring-sky-300" : f.status === "ok" ? "bg-emerald-100 text-emerald-900 ring-emerald-300" : "bg-slate-100 text-slate-700 ring-slate-300"}>
                    {f.status === "needs_irrigation" ? "💧" : f.status === "ok" ? "✅" : "⏸️"} {t(`status.${f.status}`)}
                  </Badge>
                </div>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ---------- /fields/new?farm= ----------

export function NewFieldPage() {
  const { t } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const presetFarm = params.get("farm");
  const farms = useApi(() => api.listFarms(1), { demoFallback: () => ({ items: [], page: 1, page_size: 20, total: 0 }) });
  const crops = useApi(() => api.crops(), { demoFallback: () => demoCrops });
  const soils = useApi(() => api.soilTypes(), { demoFallback: () => demoSoilTypes });

  const [farmId, setFarmId] = useState(presetFarm ?? "");
  const [form, setForm] = useState({ name: "", area: "", soil_type_id: "", crop_id: "", growth_stage_code: "", irrigation_method: "furrow" as IrrigationMethod, water_source: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const chosenFarm = farmId || farms.data?.items[0]?.id || "";
  const chosenCrop = crops.data?.find((c) => String(c.id) === form.crop_id);
  const stages = chosenCrop?.stages ?? [];

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!chosenFarm) return;
    setBusy(true);
    setError(null);
    try {
      const field = await api.createField(chosenFarm, {
        name: form.name.trim(),
        area: Number(form.area),
        area_unit: "ha",
        soil_type_id: Number(form.soil_type_id),
        crop_id: Number(form.crop_id),
        growth_stage_code: form.growth_stage_code || stages[0]?.code || "VEGETATIVE",
        irrigation_method: form.irrigation_method,
        water_source: form.water_source.trim() || undefined,
      });
      toast(t("toast.saved"));
      router.push(`/fields/${field.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.i18nKey : "errors.network");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold text-slate-900">{t("field.newField")}</h1>
      {crops.demo || soils.demo ? <DemoBanner /> : null}
      <Card className="p-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error ? <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">{t(error)}</p> : null}
          <FormField label={t("field.selectFarmFirst")} htmlFor="farm" required>
            <Select id="farm" required value={chosenFarm} onChange={(e) => setFarmId(e.target.value)}>
              {(farms.data?.items ?? []).map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label={t("field.name")} htmlFor="name" required>
            <Input id="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label={`${t("field.area")} (${t("common.ha")})`} htmlFor="area" required>
            <Input id="area" inputMode="decimal" required value={form.area} onChange={(e) => setForm({ ...form, area: e.target.value })} />
          </FormField>
          <FormField label={t("field.crop")} htmlFor="crop" required>
            <Select id="crop" required value={form.crop_id} onChange={(e) => setForm({ ...form, crop_id: e.target.value, growth_stage_code: "" })}>
              <option value="">—</option>
              {(crops.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </Select>
          </FormField>
          <FormField label={t("field.stage")} htmlFor="stage" required>
            <Select id="stage" required value={form.growth_stage_code} onChange={(e) => setForm({ ...form, growth_stage_code: e.target.value })}>
              <option value="">—</option>
              {stages.map((s) => (
                <option key={s.code} value={s.code}>{t(s.label_key)}</option>
              ))}
            </Select>
          </FormField>
          <FormField label={t("field.soil")} htmlFor="soil" required>
            <Select id="soil" required value={form.soil_type_id} onChange={(e) => setForm({ ...form, soil_type_id: e.target.value })}>
              <option value="">—</option>
              {(soils.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>{s.name} ({t("soil.fieldCapacity", { pct: s.field_capacity_pct })})</option>
              ))}
            </Select>
          </FormField>
          <FormField label={t("field.method")} htmlFor="method">
            <Select id="method" value={form.irrigation_method} onChange={(e) => setForm({ ...form, irrigation_method: e.target.value as IrrigationMethod })}>
              {(["drip", "sprinkler", "flood", "furrow", "manual", "other"] as const).map((m) => (
                <option key={m} value={m}>{t(`method.${m}`)}</option>
              ))}
            </Select>
          </FormField>
          <FormField label={t("field.waterSource")} htmlFor="ws">
            <Input id="ws" value={form.water_source} onChange={(e) => setForm({ ...form, water_source: e.target.value })} />
          </FormField>
          <Button type="submit" loading={busy} className="w-full">{t("common.submit")}</Button>
        </form>
      </Card>
    </div>
  );
}

// ---------- /fields/[id] ----------

export function FieldDetailPage({ fieldId }: { fieldId: string }) {
  const { t } = useI18n();
  const detail = useApi(() => api.fieldDetail(fieldId), { deps: [fieldId] });
  const [showCharts, setShowCharts] = useState(false);
  const [readingOpen, setReadingOpen] = useState(false);
  const [readingVal, setReadingVal] = useState("");
  const [saving, setSaving] = useState(false);

  if (detail.status === "error") return <ErrorState error={detail.error} onRetry={detail.reload} />;
  if (detail.status === "loading")
    return (
      <div className="space-y-3" aria-busy="true">
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  const d = detail.data;
  if (!d) return null;
  const f = d.field;

  async function saveReading(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await api.addReading(fieldId, { soil_moisture_pct: Number(readingVal) });
      toast(t("toast.saved"));
      setReadingOpen(false);
      setReadingVal("");
      detail.reload();
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-extrabold text-slate-900">{f.name}</h1>
          <p className="text-xs text-slate-500">
            {f.crop.name} · {t(`crop.stage.${f.growth_stage_code}`)} · {fmtNumber(f.area, 2)} {f.area_unit === "ha" ? t("common.ha") : t("common.acre")} · {t(`method.${f.irrigation_method}`)}
          </p>
        </div>
        {f.demo ? <Badge className="bg-amber-100 text-amber-900 ring-amber-300">{t("common.demoLabel")}</Badge> : null}
      </div>

      <IrrigationStatusCard rec={d.recommendation} fieldId={f.id} />

      <div className="grid gap-3 sm:grid-cols-2">
        <SoilMoistureTile
          value={d.latest_reading?.value_pct}
          source={d.latest_reading?.source}
          ageHours={d.latest_reading ? (Date.now() - new Date(d.latest_reading.taken_at).getTime()) / 3_600_000 : null}
          target={f.soil_type.field_capacity_pct}
          wilting={f.soil_type.wilting_point_pct}
        />
        <WeatherTile weather={d.weather} />
      </div>
      <RainStrip weather={d.weather} />

      <div className="grid grid-cols-2 gap-2">
        <Link href={`/fields/${f.id}/record-irrigation`}>
          <Button className="w-full">{t("field.recordIrrigation")}</Button>
        </Link>
        <Button variant="secondary" onClick={() => setReadingOpen((v) => !v)} aria-expanded={readingOpen}>
          {t("field.addReading")}
        </Button>
      </div>
      {readingOpen ? (
        <Card className="p-4">
          <form onSubmit={saveReading} className="flex items-end gap-3">
            <FormField label={t("field.readingValue")} htmlFor="reading" required>
              <Input id="reading" type="number" min={0} max={100} step="0.1" required value={readingVal} onChange={(e) => setReadingVal(e.target.value)} className="max-w-[140px]" />
            </FormField>
            <Button type="submit" loading={saving}>{t("common.save")}</Button>
          </form>
        </Card>
      ) : null}

      {d.recommendation?.warnings?.length ? (
        <ul className="space-y-1">
          {d.recommendation.warnings.map((w, i) => (
            <li key={i} className="rounded-lg bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900 ring-1 ring-orange-200">
              ⚠️ {t(w.key, w.params ?? null)}
            </li>
          ))}
        </ul>
      ) : null}

      <section aria-label={t("field.history")} className="space-y-2">
        <h2 className="text-lg font-bold text-slate-900">{t("field.history")}</h2>
        {!showCharts ? (
          <Button variant="ghost" onClick={() => setShowCharts(true)}>
            📈 {t("field.history")}
          </Button>
        ) : (
          <Suspense fallback={<Skeleton className="h-44 w-full" />}>
            <ChartsLoader fieldId={f.id} />
          </Suspense>
        )}
      </section>

      {d.latest_reading ? (
        <p className="text-center text-xs text-slate-400">
          {t("field.lastReading", { value: fmtNumber(d.latest_reading.value_pct, 0), when: relativeAge(d.latest_reading.taken_at) ?? "" })}
        </p>
      ) : null}
    </div>
  );
}
