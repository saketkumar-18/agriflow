"use client";

// Farm management: list, new, detail.

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { api, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Field as FormField,
  Input,
  Select,
  toast,
} from "@/components/ui";
import { fmtNumber } from "@/lib/format";

// ---------- farms/new ----------

export function NewFarmPage() {
  const { t } = useI18n();
  const router = useRouter();
  const [form, setForm] = useState({ name: "", location_text: "", latitude: "", longitude: "", total_area: "", area_unit: "ha" as "ha" | "acre" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const farm = await api.createFarm({
        name: form.name.trim(),
        location_text: form.location_text.trim() || undefined,
        latitude: form.latitude ? Number(form.latitude) : undefined,
        longitude: form.longitude ? Number(form.longitude) : undefined,
        total_area: form.total_area ? Number(form.total_area) : undefined,
        area_unit: form.area_unit,
      });
      toast(t("toast.saved"));
      router.push(`/fields/new?farm=${farm.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.i18nKey : "errors.network");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold text-slate-900">{t("farm.newFarm")}</h1>
      <Card className="p-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error ? <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">{t(error)}</p> : null}
          <FormField label={t("farm.name")} htmlFor="name" required>
            <Input id="name" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </FormField>
          <FormField label={t("farm.location")} htmlFor="location_text">
            <Input id="location_text" value={form.location_text} onChange={(e) => setForm({ ...form, location_text: e.target.value })} />
          </FormField>
          <p className="text-xs text-slate-500">{t("farm.createHint")}</p>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`${t("farm.location")} — lat`} htmlFor="lat">
              <Input id="lat" inputMode="decimal" placeholder="26.14" value={form.latitude} onChange={(e) => setForm({ ...form, latitude: e.target.value })} />
            </FormField>
            <FormField label={`${t("farm.location")} — lon`} htmlFor="lon">
              <Input id="lon" inputMode="decimal" placeholder="91.72" value={form.longitude} onChange={(e) => setForm({ ...form, longitude: e.target.value })} />
            </FormField>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={t("farm.area")} htmlFor="area">
              <Input id="area" inputMode="decimal" value={form.total_area} onChange={(e) => setForm({ ...form, total_area: e.target.value })} />
            </FormField>
            <FormField label={t("farm.areaUnit")} htmlFor="unit">
              <Select id="unit" value={form.area_unit} onChange={(e) => setForm({ ...form, area_unit: e.target.value as "ha" | "acre" })}>
                <option value="ha">{t("common.ha")}</option>
                <option value="acre">{t("common.acre")}</option>
              </Select>
            </FormField>
          </div>
          <Button type="submit" loading={busy} className="w-full">{t("common.submit")}</Button>
        </form>
      </Card>
    </div>
  );
}

// ---------- farms/[id] ----------

export function FarmDetailPage({ farmId }: { farmId: string }) {
  const { t } = useI18n();
  const farm = useApi(() => api.getFarm(farmId), { deps: [farmId] });
  const summary = useApi(() => api.farmSummary(farmId), { deps: [farmId] });

  if (farm.status === "error") return <ErrorState error={farm.error} onRetry={farm.reload} />;
  if (farm.status === "loading") return <div className="space-y-3" aria-busy="true"><CardSkeleton /><CardSkeleton /></div>;
  const f = farm.data;
  if (!f) return null;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{f.name}</h1>
      <Card className="p-4">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-slate-500">{t("farm.location")}</dt>
            <dd className="font-semibold text-slate-900">{f.location_text ?? (f.latitude != null && f.longitude != null ? `${fmtNumber(f.latitude, 3)}, ${fmtNumber(f.longitude, 3)}` : "—")}</dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("farm.area")}</dt>
            <dd className="font-semibold text-slate-900">{f.total_area != null ? `${fmtNumber(f.total_area, 2)} ${f.area_unit === "ha" ? t("common.ha") : t("common.acre")}` : "—"}</dd>
          </div>
          <div>
            <dt className="text-slate-500">{t("farm.fieldCount", { count: f.field_count })}</dt>
            <dd className="font-semibold text-slate-900">{summary.data?.fields.length ?? f.field_count}</dd>
          </div>
        </dl>
      </Card>
      <h2 className="text-lg font-bold text-slate-900">{t("field.myFields")}</h2>
      {summary.status === "loading" ? (
        <CardSkeleton />
      ) : summary.status === "error" ? (
        <ErrorState error={summary.error} onRetry={summary.reload} />
      ) : (summary.data?.fields.length ?? 0) === 0 ? (
        <EmptyState icon="🌾" title={t("field.noFields")} hint={t("field.noFieldsHint")} action={<Link href={`/fields/new?farm=${f.id}`}><Button>{t("field.addField")}</Button></Link>} />
      ) : (
        <ul className="space-y-2">
          {summary.data!.fields.map((fld) => (
            <li key={fld.id}>
              <Link href={`/fields/${fld.id}`} className="block rounded-2xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
                <Card className="flex items-center justify-between p-4">
                  <div>
                    <p className="font-bold text-slate-900">{fld.name}</p>
                    <p className="text-xs text-slate-500">{fld.crop_name} · {fld.growth_stage}</p>
                  </div>
                  <Badge className={fld.status === "needs_irrigation" ? "bg-sky-100 text-sky-900 ring-sky-300" : fld.status === "ok" ? "bg-emerald-100 text-emerald-900 ring-emerald-300" : "bg-slate-100 text-slate-700 ring-slate-300"}>
                    {t(`status.${fld.status}`)}
                  </Badge>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Link href={`/analytics?farm=${f.id}`}><Button variant="secondary" className="w-full">{t("nav.analytics")}</Button></Link>
        <Link href={`/fields/new?farm=${f.id}`}><Button className="w-full">{t("field.addField")}</Button></Link>
      </div>
    </div>
  );
}
