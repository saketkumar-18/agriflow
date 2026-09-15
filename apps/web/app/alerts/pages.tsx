"use client";

// /notifications — list + mark read. /alerts — notification + settings.

import { useState } from "react";
import Link from "next/link";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { demoNotifications, demoFarmSummary } from "@/lib/fixtures";
import { Badge, Button, Card, CardSkeleton, Checkbox, DemoBanner, EmptyState, ErrorState, Select, toast } from "@/components/ui";
import { fmtDateTime } from "@/lib/format";
import type { AlertLevel } from "@/lib/types";

const TYPE_ICON: Record<string, string> = {
  irrigation_needed: "💧",
  rain_incoming: "🌧️",
  extreme_heat: "🔥",
  sensor_offline: "📡",
  low_confidence: "❔",
  advisory: "🧑‍🔬",
};

export function NotificationsPage() {
  const { t } = useI18n();
  const list = useApi(() => api.notifications(false, 1), { demoFallback: () => demoNotifications });
  const [readIds, setReadIds] = useState<Set<number>>(new Set());

  async function markAll() {
    try {
      await api.markAllNotificationsRead();
      toast(t("notif.allRead"), "info");
      list.reload();
    } catch {
      toast(t("errors.generic"), "error");
    }
  }

  async function markOne(id: number) {
    setReadIds((s) => new Set(s).add(id));
    try {
      await api.markNotificationRead(id);
    } catch {
      setReadIds((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
    }
  }

  if (list.status === "loading")
    return (
      <div className="space-y-3" aria-busy="true">
        <h1 className="text-xl font-extrabold text-slate-900">{t("notif.title")}</h1>
        <CardSkeleton />
        <CardSkeleton />
      </div>
    );
  if (list.status === "error") return <ErrorState error={list.error} onRetry={list.reload} />;
  const items = list.data?.items ?? [];
  const unread = items.filter((n) => !n.read_at && !readIds.has(n.id));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-extrabold text-slate-900">{t("notif.title")}</h1>
        {unread.length > 0 ? (
          <Button variant="secondary" onClick={markAll}>{t("notif.markAllRead")}</Button>
        ) : null}
      </div>
      {list.demo ? <DemoBanner /> : null}
      {items.length === 0 ? (
        <EmptyState icon="🔔" title={t("notif.empty")} hint={t("alerts.noAlertsHint")} />
      ) : (
        <ul className="space-y-2">
          {items.map((n) => {
            const isRead = !!n.read_at || readIds.has(n.id);
            return (
              <li key={n.id}>
                <Card className={`p-4 ${isRead ? "opacity-70" : "border-2 border-sky-300"}`}>
                  <div className="flex items-start gap-3">
                    <span aria-hidden="true" className="text-2xl">{TYPE_ICON[n.type] ?? "🔔"}</span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-slate-900">{t(n.title_key, n.params ?? null)}</p>
                      <p className="text-xs text-slate-500">{fmtDateTime(n.created_at)} · {t(`notif.type.${n.type}`)}</p>
                    </div>
                    {!isRead ? (
                      <button
                        type="button"
                        onClick={() => void markOne(n.id)}
                        className="shrink-0 rounded-lg px-2 py-1 text-xs font-bold text-emerald-800 ring-1 ring-emerald-300 hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 min-h-[36px]"
                      >
                        ✓ {t("notif.markRead")}
                      </button>
                    ) : null}
                  </div>
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function AlertsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [level, setLevel] = useState<AlertLevel>("medium");
  const [push, setPush] = useState(true);
  const [email, setEmail] = useState(false);
  const [busy, setBusy] = useState(false);
  const alerts = useApi(() => api.notifications(true, 1), { demoFallback: () => demoNotifications });
  const farmId = demoFarmSummary.farm.id; // settings link to the account; alerts show unread feed

  async function save() {
    setBusy(true);
    try {
      await api.savePreferences({ alert_level: level, channels: { push, email } });
      toast(t("alerts.saved"));
    } catch {
      toast(t("errors.generic"), "error");
    } finally {
      setBusy(false);
    }
  }
  void user;
  void farmId;

  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("nav.alerts")}</h1>
      <Card className="p-5 space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{t("alerts.settings")}</h2>
        <div>
          <label htmlFor="level" className="mb-1 block text-sm font-medium text-slate-800">{t("alerts.level")}</label>
          <Select id="level" value={level} onChange={(e) => setLevel(e.target.value as AlertLevel)}>
            {(["critical", "high", "medium", "low"] as const).map((l) => (
              <option key={l} value={l}>{t(`alerts.level.${l}`)}</option>
            ))}
          </Select>
        </div>
        <fieldset>
          <legend className="mb-1 text-sm font-medium text-slate-800">{t("alerts.channels")}</legend>
          <Checkbox label={t("alerts.channel.push")} checked={push} onChange={(e) => setPush(e.target.checked)} />
          <Checkbox label={t("alerts.channel.email")} checked={email} onChange={(e) => setEmail(e.target.checked)} />
        </fieldset>
        <Button className="w-full" onClick={save} loading={busy}>{t("common.save")}</Button>
      </Card>

      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{t("alerts.title")}</h2>
      {alerts.status === "loading" ? (
        <CardSkeleton />
      ) : alerts.status === "error" ? (
        <ErrorState error={alerts.error} onRetry={alerts.reload} />
      ) : (alerts.data?.items.length ?? 0) === 0 ? (
        <EmptyState icon="✅" title={t("alerts.noAlerts")} hint={t("alerts.noAlertsHint")} />
      ) : (
        <ul className="space-y-2">
          {alerts.data!.items.map((n) => (
            <li key={n.id}>
              <Card className="flex items-center gap-3 p-4">
                <span aria-hidden="true" className="text-2xl">{TYPE_ICON[n.type] ?? "🔔"}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-slate-900">{t(n.title_key, n.params ?? null)}</p>
                  <p className="text-xs text-slate-500">{fmtDateTime(n.created_at)}</p>
                </div>
                <Badge className={n.severity === "high" || n.severity === "critical" ? "bg-red-100 text-red-900 ring-red-300" : "bg-slate-100 text-slate-700 ring-slate-300"}>
                  {n.severity}
                </Badge>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <Link href="/notifications" className="block text-center text-sm font-semibold text-emerald-800 underline">
        {t("notif.title")} →
      </Link>
    </div>
  );
}

export function AccountPage() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("nav.account")}</h1>
      <Card className="p-5 space-y-2">
        <p className="text-lg font-bold text-slate-900">{user.full_name}</p>
        <p className="text-sm text-slate-600">{user.email}</p>
        <Badge className="bg-emerald-100 text-emerald-900 ring-emerald-300">{user.role}</Badge>
      </Card>
      <div className="grid gap-2">
        <Link href="/notifications"><Button variant="secondary" className="w-full">🔔 {t("notif.title")}</Button></Link>
        <Link href="/analytics"><Button variant="secondary" className="w-full">📊 {t("nav.analytics")}</Button></Link>
        {user.role === "agronomist" || user.role === "admin" ? (
          <Link href="/agronomist"><Button variant="secondary" className="w-full">🧑‍🔬 {t("nav.agronomist")}</Button></Link>
        ) : null}
        {user.role === "admin" ? (
          <Link href="/admin"><Button variant="secondary" className="w-full">🛠️ {t("nav.admin")}</Button></Link>
        ) : null}
        <Button variant="danger" onClick={logout}>{t("common.logout")}</Button>
      </div>
    </div>
  );
}
