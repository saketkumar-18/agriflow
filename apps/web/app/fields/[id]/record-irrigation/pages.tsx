"use client";

// /fields/[id]/record-irrigation — offline-queued irrigation form.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { api, writeWithQueue, ApiError } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { Button, Card, ErrorState, Field as FormField, Input, Textarea, toast } from "@/components/ui";
import { toLocalInputValue } from "@/lib/format";
import type { IrrigationEvent } from "@/lib/types";

export function RecordIrrigationPage({ fieldId }: { fieldId: string }) {
  const { t } = useI18n();
  const router = useRouter();
  const field = useApi(() => api.getField(fieldId), { deps: [fieldId] });
  const rec = useApi(() => api.recommendation(fieldId), { deps: [fieldId] });

  const [amountMm, setAmountMm] = useState("");
  const [liters, setLiters] = useState("");
  const [duration, setDuration] = useState("");
  const [note, setNote] = useState("");
  const [when, setWhen] = useState(() => toLocalInputValue(new Date()));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!amountMm && !liters) {
      setError("irrigation.oneOfAmount");
      return;
    }
    setError(null);
    setBusy(true);
    const idem =
      typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : String(Date.now());
    const body = {
      field_id: Number(fieldId),
      recommendation_id: rec.data?.id ?? null,
      irrigated_at: new Date(when).toISOString(),
      duration_minutes: duration ? Number(duration) : null,
      amount_mm: amountMm ? Number(amountMm) : null,
      liters: liters ? Number(liters) : null,
      note: note.trim() || null,
      idempotency_key: idem,
    };
    try {
      const res = await writeWithQueue<IrrigationEvent>("irrigation_event", "/irrigation-events", body, idem);
      if (res.queued) {
        toast(t("irrigation.queued"), "info");
      } else {
        toast(t("irrigation.saved"));
      }
      router.push("/history");
    } catch (err) {
      setError(err instanceof ApiError ? err.i18nKey : "errors.generic");
      setBusy(false);
    }
  }

  if (field.status === "error") return <ErrorState error={field.error} onRetry={field.reload} />;
  if (field.status === "loading") return <Card className="p-4 animate-pulse"><div className="h-6 w-1/2 bg-slate-200 rounded" /></Card>;
  const f = field.data;
  if (!f) return null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-extrabold text-slate-900">
        {t("irrigation.recordTitle")} — {f.name}
      </h1>
      <Card className="p-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error ? <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-800">{t(error)}</p> : null}
          <FormField label={t("irrigation.when")} htmlFor="when" required>
            <Input id="when" type="datetime-local" required value={when} onChange={(e) => setWhen(e.target.value)} />
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label={`${t("irrigation.amountMm")} (${t("common.optional")})`} htmlFor="mm">
              <Input id="mm" type="number" min="0" step="0.1" inputMode="decimal" value={amountMm} onChange={(e) => setAmountMm(e.target.value)} />
            </FormField>
            <FormField label={`${t("irrigation.amountLiters")} (${t("common.optional")})`} htmlFor="liters">
              <Input id="liters" type="number" min="0" step="1" inputMode="numeric" value={liters} onChange={(e) => setLiters(e.target.value)} />
            </FormField>
          </div>
          <p className="text-xs text-slate-500">{t("irrigation.oneOfAmount")}</p>
          {rec.data?.estimated_water_requirement && !amountMm ? (
            <button
              type="button"
              onClick={() => setAmountMm(String(rec.data!.estimated_water_requirement!.value))}
              className="text-sm font-semibold text-emerald-800 underline rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
            >
              💧 {t("irrigation.waterNeed")}: {rec.data.estimated_water_requirement.value} {rec.data.estimated_water_requirement.unit}
            </button>
          ) : null}
          <FormField label={t("irrigation.duration")} htmlFor="dur">
            <Input id="dur" type="number" min="0" step="1" inputMode="numeric" value={duration} onChange={(e) => setDuration(e.target.value)} />
          </FormField>
          <FormField label={`${t("irrigation.note")} (${t("common.optional")})`} htmlFor="note">
            <Textarea id="note" rows={3} value={note} onChange={(e) => setNote(e.target.value)} />
          </FormField>
          <Button type="submit" loading={busy} className="w-full">
            {t("irrigation.submit")}
          </Button>
        </form>
      </Card>
    </div>
  );
}
