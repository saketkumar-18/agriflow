"use client";

// /admin — stats + users table + audit log (role-gated).

import { useState } from "react";
import { useI18n } from "@/lib/i18n";
import { api } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { useAuth } from "@/lib/auth";
import { demoAdminStats } from "@/lib/fixtures";
import { Button, Card, CardSkeleton, DemoBanner, EmptyState, ErrorState, Select, toast } from "@/components/ui";
import { fmtDateTime, fmtNumber } from "@/lib/format";
import type { Role, User } from "@/lib/types";

export function AdminPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const [tab, setTab] = useState<"stats" | "users" | "audit">("stats");

  if (!user || user.role !== "admin") {
    return <EmptyState icon="🔒" title={t("admin.accessDenied")} />;
  }
  return (
    <div className="space-y-3">
      <h1 className="text-xl font-extrabold text-slate-900">{t("admin.title")}</h1>
      <div role="tablist" aria-label={t("admin.title")} className="grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1">
        {(["stats", "users", "audit"] as const).map((tabKey) => (
          <button
            key={tabKey}
            role="tab"
            aria-selected={tab === tabKey}
            onClick={() => setTab(tabKey)}
            className={`min-h-[44px] rounded-lg text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
              tab === tabKey ? "bg-white text-emerald-900 shadow" : "text-slate-600"
            }`}
          >
            {tabKey === "stats" ? t("admin.stats") : tabKey === "users" ? t("admin.users") : t("admin.auditLog")}
          </button>
        ))}
      </div>
      {tab === "stats" ? <StatsTab /> : tab === "users" ? <UsersTab /> : <AuditTab />}
    </div>
  );
}

function StatsTab() {
  const { t } = useI18n();
  const stats = useApi(() => api.adminStats(), { demoFallback: () => demoAdminStats });
  if (stats.status === "loading") return <div className="grid grid-cols-2 gap-2" aria-busy="true"><CardSkeleton /><CardSkeleton /></div>;
  if (stats.status === "error") return <ErrorState error={stats.error} onRetry={stats.reload} />;
  const s = stats.data!;
  const rows: [string, string][] = [
    [t("admin.totalUsers"), String(s.total_users)],
    [t("admin.totalFarms"), String(s.total_farms)],
    [t("admin.activeFarms"), String(s.active_farms)],
    [t("admin.totalFields"), String(s.total_fields)],
    [t("admin.recsToday"), String(s.recommendations_today)],
    [t("admin.events30d"), String(s.irrigation_events_30d)],
    [t("admin.sensorUptime"), s.sensor_uptime_pct != null ? `${fmtNumber(s.sensor_uptime_pct, 1)}%` : "—"],
    [t("admin.weatherHealth"), s.weather_provider_health],
  ];
  return (
    <>
      {stats.demo ? <DemoBanner /> : null}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {rows.map(([label, value]) => (
          <Card key={label} className="p-4 text-center">
            <p className="text-xl font-extrabold text-emerald-900">{value}</p>
            <p className="mt-1 text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
          </Card>
        ))}
      </div>
    </>
  );
}

function UsersTab() {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const users = useApi(() => api.adminUsers({ page }), { deps: [page] });

  async function patch(u: User, input: { role?: Role; is_active?: boolean }) {
    try {
      await api.adminPatchUser(u.id, input);
      toast(t("toast.saved"));
      users.reload();
    } catch {
      toast(t("errors.generic"), "error");
    }
  }

  if (users.status === "loading") return <div aria-busy="true"><CardSkeleton /></div>;
  if (users.status === "error") return <ErrorState error={users.error} onRetry={users.reload} />;
  const items = users.data?.items ?? [];
  if (items.length === 0) return <EmptyState icon="👥" title={t("admin.noUsers")} />;

  return (
    <>
      <Card className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <caption className="sr-only">{t("admin.users")}</caption>
          <thead>
            <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
              <th scope="col" className="px-3 py-2">{t("common.fullName")}</th>
              <th scope="col" className="px-3 py-2">{t("common.email")}</th>
              <th scope="col" className="px-3 py-2">{t("admin.role")}</th>
              <th scope="col" className="px-3 py-2">{t("admin.active")}</th>
              <th scope="col" className="px-3 py-2">{t("admin.lastSeen")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((u) => (
              <tr key={u.id} className="border-b border-slate-100 last:border-0">
                <th scope="row" className="px-3 py-2.5 font-semibold text-slate-900">
                  {u.full_name}{u.demo ? " 🧪" : ""}
                </th>
                <td className="px-3 py-2.5 text-slate-600">{u.email}</td>
                <td className="px-3 py-2.5">
                  <Select
                    aria-label={`${t("admin.role")}: ${u.full_name}`}
                    value={u.role}
                    onChange={(e) => patch(u, { role: e.target.value as Role })}
                    className="min-h-[40px] w-auto py-1 text-sm"
                  >
                    {(["farmer", "agronomist", "admin"] as const).map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </Select>
                </td>
                <td className="px-3 py-2.5">
                  <button
                    type="button"
                    aria-pressed={u.is_active}
                    onClick={() => patch(u, { is_active: !u.is_active })}
                    className={`min-h-[36px] rounded-full px-3 text-xs font-bold ring-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
                      u.is_active ? "bg-emerald-100 text-emerald-900 ring-emerald-300" : "bg-slate-100 text-slate-600 ring-slate-300"
                    }`}
                  >
                    {u.is_active ? "✓" : "✕"}
                  </button>
                </td>
                <td className="px-3 py-2.5 text-slate-500">{fmtDateTime(u.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <Pager page={users.data?.page ?? 1} total={users.data?.total ?? 0} pageSize={users.data?.page_size ?? 20} onPage={setPage} />
    </>
  );
}

function AuditTab() {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const audit = useApi(() => api.adminAudit(page), { deps: [page] });
  if (audit.status === "loading") return <div aria-busy="true"><CardSkeleton /></div>;
  if (audit.status === "error") return <ErrorState error={audit.error} onRetry={audit.reload} />;
  const items = audit.data?.items ?? [];
  if (items.length === 0) return <EmptyState icon="📋" title={t("admin.noAudit")} />;
  return (
    <>
      <ul className="space-y-2">
        {items.map((a) => (
          <li key={a.id}>
            <Card className="p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-900">{a.action}</p>
                <p className="text-xs text-slate-500">{fmtDateTime(a.created_at)}</p>
              </div>
              <p className="text-xs text-slate-600">
                {a.resource_type}
                {a.resource_id != null ? ` #${a.resource_id}` : ""}
                {a.user_id != null ? ` · user #${a.user_id}` : ""}
              </p>
            </Card>
          </li>
        ))}
      </ul>
      <Pager page={audit.data?.page ?? 1} total={audit.data?.total ?? 0} pageSize={audit.data?.page_size ?? 20} onPage={setPage} />
    </>
  );
}

function Pager({ page, total, pageSize, onPage }: { page: number; total: number; pageSize: number; onPage: (p: number) => void }) {
  const { t } = useI18n();
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-3">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>←</Button>
      <span className="text-sm text-slate-600">{page} {t("common.of")} {pages}</span>
      <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>→</Button>
    </div>
  );
}

