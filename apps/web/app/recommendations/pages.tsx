"use client";

// /recommendations/[fieldId] — full explanation + feedback + refresh.

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { api, writeWithQueue } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { ConfidenceMeter, StatusVisual, textOrKey } from "@/components/irrigation-status";
import { Badge, Button, Card, CardHeader, CardSkeleton, DemoBanner, ErrorState, Skeleton, Textarea, toast } from "@/components/ui";
import { fmtDateTime, fmtNumber, urgencyStyle } from "@/lib/format";
import { useAuth } from "@/lib/auth";
import type { Recommendation } from "@/lib/types";

export function RecommendationPage({ fieldId }: { fieldId: string }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const rec = useApi(() => api.recommendation(fieldId), { deps: [fieldId] });
  const [refreshing, setRefreshing] = useState(false);
  const [feedback, setFeedback] = useState<boolean | null>(null);
  const [comment, setComment] = useState("");
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideErr, setOverrideErr] = useState<string | null>(null);

  async function refresh() {
    setRefreshing(true);
    try {
      await api.refreshRecommendation(fieldId);
      rec.reload();
      toast(t("irrigation.recRefreshed"), "info");
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setRefreshing(false);
    }
  }

  async function sendFeedback(useful: boolean) {
    if (!rec.data) return;
    const idem = crypto.randomUUID?.() ?? String(Date.now());
    const res = await writeWithQueue("feedback", "/feedback", { recommendation_id: rec.data.id, useful, comment: comment.trim() || undefined }, idem);
    setFeedback(useful);
    toast(res.queued ? t("feedback.queued") : t("rec.feedbackThanks"));
  }

  async function override(action: "defer" | "approve" | "cancel") {
    if (!rec.data) return;
    if (!overrideReason.trim()) {
      setOverrideErr("agro.overrideReasonMissing");
      return;
    }
    setOverrideErr(null);
    try {
      await api.overrideRecommendation(rec.data.id, { action, reason: overrideReason.trim() });
      toast(t("agro.overrideSaved"));
      setOverrideOpen(false);
      rec.reload();
    } catch {
      toast(t("errors.forbidden"), "error");
    }
  }

  if (rec.status === "loading")
    return (
      <div className="space-y-3" aria-busy="true">
        <Skeleton className="h-28 w-full" />
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  if (rec.status === "error") return <ErrorState error={rec.error} onRetry={rec.reload} />;
  const r = rec.data;
  if (!r) return <ErrorState error={new Error("empty")} onRetry={rec.reload} />;

  const canOverride = user && (user.role === "agronomist" || user.role === "admin");
  const digest = r.inputs_digest;

  return (
    <div className="space-y-3">
      {r.demo ? <DemoBanner /> : null}
      <h1 className="sr-only">{t("irrigation.question")}</h1>
      <StatusCard r={r} />
      <Button variant="secondary" className="w-full" onClick={refresh} loading={refreshing} disabled={refreshing}>
        🔄 {refreshing ? t("irrigation.refreshing") : t("irrigation.refresh")}
      </Button>

      {r.reasons.length > 0 ? (
        <Card>
          <CardHeader title={t("irrigation.reasons")} />
          <ul className="space-y-2 px-4 pb-4">
            {r.reasons.map((x, i) => (
              <li key={i} className="flex items-start gap-2 text-[15px] text-slate-800">
                <span aria-hidden="true" className="mt-0.5">•</span> <span>{textOrKey(x, t)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {r.warnings.length > 0 ? (
        <ul className="space-y-1">
          {r.warnings.map((w, i) => (
            <li key={i} className="rounded-lg bg-orange-50 px-3 py-2 text-sm font-medium text-orange-900 ring-1 ring-orange-200">
              ⚠️ {textOrKey(w, t)}
            </li>
          ))}
        </ul>
      ) : null}

      <Card>
        <CardHeader title={t("rec.confidenceFactors")} />
        <div className="px-4 pb-4">
          <ConfidenceMeter score={r.confidence.score} level={r.confidence.level} />
          <ul className="mt-3 space-y-1">
            {r.confidence.factors.map((f) => (
              <li key={f.key} className="flex items-center gap-2 text-sm text-slate-700">
                <span aria-hidden="true">{f.ok ? "✅" : "❌"}</span>
                <span>{t(f.key)}</span>
                <span className="sr-only">{f.ok ? t("common.yes") : t("common.no")}</span>
              </li>
            ))}
          </ul>
        </div>
      </Card>

      <Card>
        <CardHeader title={t("rec.inputsSummary")} />
        <ul className="space-y-1 px-4 pb-4 text-sm text-slate-700">
          {digest.moisture ? <li>{t("rec.inputMoisture", { value: fmtNumber(digest.moisture.value, 0), source: t(`soil.source${digest.moisture.source === "sensor" ? "Sensor" : "Manual"}`), age: digest.moisture.age_hours != null ? t("common.hoursAgo", { hours: Math.round(digest.moisture.age_hours) }) : "—" })}</li> : null}
          {digest.rain_next_24h_mm != null ? <li>{t("rec.inputRain24", { mm: fmtNumber(digest.rain_next_24h_mm, 1) })}</li> : null}
          {digest.et0_mm != null ? <li>{t("rec.inputEt0", { mm: fmtNumber(digest.et0_mm, 1) })}</li> : null}
          {digest.crop ? <li>{t("rec.inputCrop", { crop: digest.crop })}</li> : null}
          {digest.soil ? <li>{t("rec.inputSoil", { soil: digest.soil })}</li> : null}
        </ul>
      </Card>

      {r.override ? (
        <Card className="border-2 border-violet-300 bg-violet-50 p-4">
          <p className="text-sm font-bold text-violet-900">🧑‍🔬 {t("rec.overridden", { action: t(`agro.override.${r.override.action}`) })}</p>
          <p className="text-sm text-violet-800">{t("rec.overrideReason", { reason: r.override.reason })}</p>
        </Card>
      ) : null}

      {canOverride ? (
        <div className="space-y-2">
          <Button variant="secondary" className="w-full" onClick={() => setOverrideOpen((v) => !v)} aria-expanded={overrideOpen}>
            🧑‍🔬 {t("agro.override")}
          </Button>
          {overrideOpen ? (
            <Card className="space-y-3 p-4">
              <Badge>{t("agro.overrideReasonLabel")}</Badge>
              {overrideErr ? <p role="alert" className="text-sm font-semibold text-red-700">{t(overrideErr)}</p> : null}
              <Textarea aria-label={t("agro.overrideReasonLabel")} rows={2} value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} />
              <div className="grid grid-cols-3 gap-2">
                <Button variant="secondary" onClick={() => override("approve")}>{t("agro.override.approve")}</Button>
                <Button variant="secondary" onClick={() => override("defer")}>{t("agro.override.defer")}</Button>
                <Button variant="danger" onClick={() => override("cancel")}>{t("agro.override.cancel")}</Button>
              </div>
            </Card>
          ) : null}
        </div>
      ) : null}

      <Card>
        <CardHeader title={t("rec.feedbackQuestion")} />
        <div className="space-y-3 px-4 pb-4">
          <div className="grid grid-cols-2 gap-2">
            <Button variant={feedback === true ? "primary" : "secondary"} onClick={() => void sendFeedback(true)}>
              👍 {t("feedback.useful")}
            </Button>
            <Button variant={feedback === false ? "primary" : "secondary"} onClick={() => void sendFeedback(false)}>
              👎 {t("feedback.notUseful")}
            </Button>
          </div>
          <Textarea aria-label={t("feedback.comment")} rows={2} placeholder={t("feedback.comment")} value={comment} onChange={(e) => setComment(e.target.value)} />
        </div>
      </Card>

      <div className="space-y-1 text-center text-xs text-slate-500">
        <p>{t("rec.computedAt", { when: fmtDateTime(r.computed_at) })} · {t("rec.expiresAt", { when: fmtDateTime(r.expires_at) })}</p>
        <p className="font-medium text-slate-600">{t(r.disclaimer_key)}</p>
        <p>{t("rec.engine", { version: r.engine_version })}</p>
      </div>
    </div>
  );
}

function StatusCard({ r }: { r: Recommendation }) {
  const { t } = useI18n();
  const v = StatusVisual({ rec: r });
  const u = urgencyStyle(r.urgency);
  return (
    <Card className={`border-2 p-5 ${v.tone}`}>
      <p className="mb-1 text-sm font-semibold text-slate-600">{t("irrigation.question")}</p>
      <div className="flex items-center gap-4">
        <span aria-hidden="true" className="text-5xl">{v.icon}</span>
        <div>
          <p className="text-2xl font-extrabold leading-tight">{t(v.labelKey)}</p>
          <div className="mt-1 flex flex-wrap gap-2">
            <Badge className={u.badge}>
              <span aria-hidden="true">{u.icon}</span> {t("irrigation.urgency")}: {t(`urgency.${r.urgency}`)}
            </Badge>
            {r.irrigation_needed && r.estimated_water_requirement ? (
              <Badge>{t("irrigation.waterNeed")}: {fmtNumber(r.estimated_water_requirement.value)} {r.estimated_water_requirement.unit}{r.estimated_liters != null ? ` (${fmtNumber(r.estimated_liters / 1000, 0)}k L)` : ""}</Badge>
            ) : null}
          </div>
          {r.recommended_time ? <p className="mt-1 text-sm font-semibold">🕘 {t("irrigation.recommendedTime", { time: textOrKey(r.recommended_time, t) })}</p> : null}
        </div>
      </div>
      <div className="mt-3">
        <ConfidenceMeter score={r.confidence.score} level={r.confidence.level} />
      </div>
    </Card>
  );
}
