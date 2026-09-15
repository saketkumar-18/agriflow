// The #1 question: "Does my field need irrigation?" — big status card.

"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import type { I18nText, Recommendation } from "@/lib/types";
import { Badge, Card } from "@/components/ui";
import { urgencyStyle, fmtNumber } from "@/lib/format";

export function StatusVisual({ rec }: { rec: Recommendation | null }) {
  if (rec == null) return { icon: "⏸️", labelKey: "irrigation.review", tone: "bg-slate-100 text-slate-900 border-slate-300" };
  if (rec.override?.action === "cancel")
    return { icon: "⏸️", labelKey: "irrigation.review", tone: "bg-slate-100 text-slate-900 border-slate-300" };
  if (rec.irrigation_needed) {
    if (rec.urgency === "LOW")
      return { icon: "⏸️", labelKey: "irrigation.review", tone: "bg-amber-50 text-amber-950 border-amber-300" };
    return { icon: "💧", labelKey: "irrigation.recommended", tone: "bg-sky-100 text-sky-950 border-sky-400" };
  }
  return { icon: "✅", labelKey: "irrigation.notNeeded", tone: "bg-emerald-50 text-emerald-950 border-emerald-400" };
}

export function textOrKey(item: I18nText | null, t: (k: string, p?: I18nText["params"] | null) => string): string {
  if (!item) return "—";
  // t() renders the raw key when a translation is missing — never crashes.
  return t(item.key, item.params ?? null);
}

export function IrrigationStatusCard({
  rec,
  fieldName,
  fieldId,
  compact = false,
}: {
  rec: Recommendation | null;
  fieldName?: string;
  fieldId: number | string;
  compact?: boolean;
}) {
  const { t } = useI18n();
  const v = StatusVisual({ rec });
  const u = urgencyStyle(rec?.urgency);

  return (
    <Card className={`overflow-hidden border-2 ${v.tone}`}>
      <div className={compact ? "p-4" : "p-5"}>
        {!compact ? (
          <p className="mb-1 text-sm font-semibold text-slate-600">{t("irrigation.question")}</p>
        ) : null}
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className={compact ? "text-3xl" : "text-5xl"}>
            {v.icon}
          </span>
          <div className="min-w-0 flex-1">
            {fieldName ? (
              <p className="truncate text-xs font-semibold uppercase tracking-wide text-slate-500">{fieldName}</p>
            ) : null}
            <p className={`font-bold leading-tight ${compact ? "text-lg" : "text-2xl md:text-3xl"}`}>{t(v.labelKey)}</p>
            {rec ? (
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <Badge className={u.badge}>
                  <span aria-hidden="true">{u.icon}</span> {t("irrigation.urgency")}: {t(`urgency.${rec.urgency}`)}
                </Badge>
                {rec.irrigation_needed && rec.estimated_water_requirement ? (
                  <Badge>{fmtNumber(rec.estimated_water_requirement.value)} {rec.estimated_water_requirement.unit === "mm" ? t("common.mm") : rec.estimated_water_requirement.unit}</Badge>
                ) : null}
                {rec.demo ? <Badge className="bg-amber-100 text-amber-900 ring-amber-300">{t("common.demoLabel")}</Badge> : null}
              </div>
            ) : null}
          </div>
        </div>
        {rec && !compact ? (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <ConfidenceMeter score={rec.confidence.score} level={rec.confidence.level} />
            <Link
              href={`/recommendations/${rec.field_id ?? fieldId}`}
              className="min-h-[44px] inline-flex items-center rounded-xl bg-white/70 px-3 text-sm font-semibold text-slate-900 underline-offset-2 ring-1 ring-slate-300 hover:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700"
            >
              {t("irrigation.fullExplanation")} →
            </Link>
          </div>
        ) : null}
        {rec && compact ? (
          <Link
            href={`/recommendations/${rec.field_id ?? fieldId}`}
            className="mt-2 inline-block text-sm font-semibold underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-700 rounded"
          >
            {t("irrigation.fullExplanation")} →
          </Link>
        ) : null}
      </div>
    </Card>
  );
}

export function ConfidenceMeter({ score, level }: { score: number; level: string }) {
  const { t } = useI18n();
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const tone = level === "HIGH" ? "bg-emerald-600" : level === "MEDIUM" ? "bg-amber-500" : "bg-red-600";
  return (
    <div className="min-w-[140px] flex-1">
      <div className="mb-1 flex items-center justify-between text-xs font-semibold text-slate-700">
        <span>{t("irrigation.confidence")}</span>
        <span>
          {t(`urgency.${level === "HIGH" ? "HIGH" : level === "MEDIUM" ? "MEDIUM" : "LOW"}`)} · {pct}%
        </span>
      </div>
      <div
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={t("irrigation.confidence")}
        className="h-2.5 w-full overflow-hidden rounded-full bg-white/70 ring-1 ring-slate-300"
      >
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
