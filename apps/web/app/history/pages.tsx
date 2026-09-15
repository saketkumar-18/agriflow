"use client";

// /history — irrigation events list.

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { demoIrrigationEvents } from "@/lib/fixtures";
import { Badge, Button, Card, CardSkeleton, DemoBanner, EmptyState, ErrorState } from "@/components/ui";
import { fmtDateTime, fmtNumber } from "@/lib/format";

export function HistoryPage() {
  const { t } = useI18n();
  const events = useApi(() => api.irrigationEvents({ page: 1 }), { demoFallback: () => demoIrrigationEvents });

  if (events.status === "error") return <ErrorState error={events.error} onRetry={events.reload} />;
  if (events.status === "loading")
    return (
      <div className="space-y-3" aria-busy="true">
        <h1 className="text-xl font-extrabold text-slate-900">{t("irrigation.events")}</h1>
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  const items = events.data?.items ?? [];

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("irrigation.events")}</h1>
      {events.demo ? <DemoBanner /> : null}
      {items.length === 0 ? (
        <EmptyState
          icon="💧"
          title={t("irrigation.noEvents")}
          hint={t("irrigation.noEventsHint")}
          action={
            <Link href="/fields">
              <Button variant="secondary">{t("field.recordIrrigation")}</Button>
            </Link>
          }
        />
      ) : (
        <ol className="space-y-2">
          {items.map((ev) => (
            <li key={ev.id}>
              <Card className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="font-bold text-slate-900">
                    💧 {ev.amount_mm != null ? `${fmtNumber(ev.amount_mm, 1)} ${t("common.mm")}` : ev.liters != null ? `${fmtNumber(ev.liters / 1000, 1)}k ${t("common.liters")}` : "—"}
                  </p>
                  <p className="text-xs text-slate-500">
                    {fmtDateTime(ev.irrigated_at)}
                    {ev.duration_minutes != null ? ` · ${t("irrigation.durationShort", { minutes: ev.duration_minutes })}` : ""}
                    {ev.source === "sync" ? " · ↻" : ""}
                  </p>
                  {ev.note ? <p className="mt-1 text-sm text-slate-600">{ev.note}</p> : null}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  <Badge>Field #{ev.field_id}</Badge>
                  {ev.demo ? <Badge className="bg-amber-100 text-amber-900 ring-amber-300">{t("common.demoLabel")}</Badge> : null}
                </div>
              </Card>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
