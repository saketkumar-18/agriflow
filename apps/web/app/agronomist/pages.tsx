"use client";

// /agronomist — assigned farms, field review, advisories, override.

import { useState } from "react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { demoFarmSummary } from "@/lib/fixtures";
import { Badge, Button, Card, CardHeader, CardSkeleton, DemoBanner, EmptyState, ErrorState, Field as FormField, Textarea, toast } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import type { Recommendation } from "@/lib/types";

export function AgronomistPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const farms = useApi(() => api.agronomistFarms(), {
    demoFallback: () => [{ ...demoFarmSummary.farm, needs_review_count: 1 }],
  });
  const [openFarm, setOpenFarm] = useState<number | null>(null);

  if (!user || (user.role !== "agronomist" && user.role !== "admin")) {
    return <EmptyState icon="🔒" title={t("agro.accessDenied")} />;
  }
  if (farms.status === "loading") return <div className="space-y-3" aria-busy="true"><CardSkeleton /><CardSkeleton /></div>;
  if (farms.status === "error") return <ErrorState error={farms.error} onRetry={farms.reload} />;
  const items = farms.data ?? [];

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("agro.title")}</h1>
      {farms.demo ? <DemoBanner /> : null}
      {items.length === 0 ? (
        <EmptyState icon="🧑‍🔬" title={t("agro.noFarms")} />
      ) : (
        <ul className="space-y-2">
          {items.map((f) => (
            <li key={f.id}>
              <Card className="p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-bold text-slate-900">{f.name}</p>
                    <p className="text-xs text-slate-500">{t("farm.fieldCount", { count: f.field_count })}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    {f.needs_review_count > 0 ? (
                      <Badge className="bg-amber-100 text-amber-900 ring-amber-300">⚠️ {t("agro.needsReview", { count: f.needs_review_count })}</Badge>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => setOpenFarm(openFarm === f.id ? null : f.id)}
                      aria-expanded={openFarm === f.id}
                      className="rounded-lg px-3 py-2 text-sm font-semibold text-emerald-800 ring-1 ring-emerald-300 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 min-h-[40px]"
                    >
                      {t("agro.reviewField")}
                    </button>
                  </div>
                </div>
                {openFarm === f.id ? <FarmReview farmId={f.id} /> : null}
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function FarmReview({ farmId }: { farmId: number }) {
  const { t } = useI18n();
  const summary = useApi(() => api.farmSummary(farmId), { deps: [farmId], demoFallback: () => demoFarmSummary });
  if (summary.status === "loading") return <CardSkeleton />;
  if (summary.status === "error") return <ErrorState error={summary.error} onRetry={summary.reload} />;
  const fields = summary.data?.fields ?? [];
  return (
    <ul className="mt-3 space-y-2 border-t border-slate-100 pt-3">
      {fields.map((f) => (
        <li key={f.id} className="flex items-center justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-800">{f.name}</p>
            <p className="text-xs text-slate-500">{f.crop_name}</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={f.status === "needs_irrigation" ? "bg-sky-100 text-sky-900 ring-sky-300" : "bg-slate-100 text-slate-700 ring-slate-300"}>
              {t(`status.${f.status}`)}
            </Badge>
            <Link href={`/agronomist/field/${f.id}`} className="shrink-0 rounded-lg px-3 py-2 text-sm font-semibold text-emerald-800 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
              →
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function AgronomistFieldPage({ fieldId }: { fieldId: string }) {
  const { t } = useI18n();
  const detail = useApi(() => api.fieldDetail(fieldId), { deps: [fieldId] });
  const advisories = useApi(() => api.advisories(fieldId), { deps: [fieldId] });
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function addAdvisory(e: React.FormEvent) {
    e.preventDefault();
    if (!note.trim()) return;
    setBusy(true);
    try {
      await api.addAdvisory(Number(fieldId), note.trim());
      toast(t("agro.advisorySaved"));
      setNote("");
      advisories.reload();
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setBusy(false);
    }
  }

  if (detail.status === "loading") return <div aria-busy="true"><CardSkeleton /></div>;
  if (detail.status === "error") return <ErrorState error={detail.error} onRetry={detail.reload} />;
  const d = detail.data;
  if (!d) return null;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">
        {t("agro.reviewField")}: {d.field.name}
      </h1>
      <Link href={`/recommendations/${fieldId}`} className="block">
        <RecommendationSummary rec={d.recommendation} />
      </Link>
      <Card>
        <CardHeader title={t("agro.addAdvisory")} />
        <form onSubmit={addAdvisory} className="space-y-3 px-4 pb-4">
          <FormField label={t("agro.advisoryNote")} htmlFor="note" required>
            <Textarea id="note" rows={3} required value={note} onChange={(e) => setNote(e.target.value)} />
          </FormField>
          <Button type="submit" loading={busy} className="w-full">{t("agro.addAdvisory")}</Button>
        </form>
      </Card>
      <Card>
        <CardHeader title={t("agro.advisories")} />
        {advisories.status === "loading" ? (
          <div className="px-4 pb-4"><CardSkeleton /></div>
        ) : advisories.status === "error" ? (
          <div className="px-4 pb-4"><ErrorState error={advisories.error} onRetry={advisories.reload} /></div>
        ) : (advisories.data?.length ?? 0) === 0 ? (
          <p className="px-4 pb-4 text-sm text-slate-500">{t("agro.noAdvisories")}</p>
        ) : (
          <ul className="space-y-2 px-4 pb-4">
            {advisories.data!.map((a) => (
              <li key={a.id} className="rounded-lg bg-slate-50 p-3 ring-1 ring-slate-200">
                <p className="text-sm text-slate-800">{a.note}</p>
                <p className="mt-1 text-xs text-slate-500">{typeof a.author === "string" ? a.author : a.author.full_name} · {fmtDateTime(a.created_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>
      <Link href={`/recommendations/${fieldId}`} className="block text-center text-sm font-semibold text-emerald-800 underline">
        {t("irrigation.fullExplanation")} →
      </Link>
    </div>
  );
}

function RecommendationSummary({ rec }: { rec: Recommendation | null }) {
  const { t } = useI18n();
  if (!rec) return <Card className="p-4 text-sm text-slate-500">{t("irrigation.noRecommendation")}</Card>;
  return (
    <Card className={`p-4 ${rec.irrigation_needed ? "border-2 border-sky-400" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="font-bold text-slate-900">
          {rec.irrigation_needed ? `💧 ${t("irrigation.recommended")}` : `✅ ${t("irrigation.notNeeded")}`}
        </p>
        <Badge>{t(`urgency.${rec.urgency}`)}</Badge>
      </div>
      <p className="mt-1 text-sm text-slate-600">
        {rec.irrigation_needed && rec.estimated_water_requirement
          ? `${t("irrigation.waterNeed")}: ${rec.estimated_water_requirement.value} ${rec.estimated_water_requirement.unit}`
          : ""}
      </p>
    </Card>
  );
}
