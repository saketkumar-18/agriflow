// App shell: providers, top bar, offline/queue badges, bottom tab nav.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { subscribeQueue, installQueueFlusher, queueLength, flushQueue } from "@/lib/queue";
import { ToastRegion, OfflineBanner, toast, Badge } from "@/components/ui";
import type { User } from "@/lib/types";

export function LanguageToggle({ user }: { user: User | null }) {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="flex items-center gap-1 rounded-full bg-slate-100 p-1" role="group" aria-label={t("common.language")}>
      {(["en", "hi"] as const).map((l) => (
        <button
          key={l}
          type="button"
          aria-pressed={lang === l}
          onClick={() => {
            setLang(l);
            toast(t("toast.langChanged"));
            // Contract's preferences payload has no `language` field, so we
            // send it alongside best-effort (servers ignore unknown fields).
            if (user) void syncLanguage(user, l);
          }}
          className={`min-h-[36px] rounded-full px-3 text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
            lang === l ? "bg-white text-emerald-800 shadow" : "text-slate-600"
          }`}
        >
          {l === "en" ? "EN" : "हि"}
        </button>
      ))}
    </div>
  );
}

// language isn't part of the preferences endpoint payload; keep helper
// minimal so a failed PUT never blocks the toggle. Existing alert prefs
// from the cached user are preserved; the PUT is best-effort.
async function syncLanguage(user: User, lang: "en" | "hi"): Promise<void> {
  try {
    await apiFetch<unknown>("/auth/me/preferences", {
      method: "PUT",
      body: {
        language: lang,
        alert_level: "medium",
        channels: { push: true, email: false },
      },
    });
  } catch {
    /* best-effort; language still persisted in localStorage per user */
  }
  void user;
}

function QueueBadge() {
  const { t } = useI18n();
  const [count, setCount] = useState(queueLength());
  useEffect(() => {
    setCount(queueLength());
    const unsub = subscribeQueue(() => setCount(queueLength()));
    const un = installQueueFlusher();
    const onFlushed = () => {
      setCount(queueLength());
      toast(t("toast.synced"), "info");
    };
    window.addEventListener("agriflow:queue-flushed", onFlushed);
    return () => {
      unsub();
      un();
      window.removeEventListener("agriflow:queue-flushed", onFlushed);
    };
  }, [t]);
  if (count === 0) return null;
  return (
    <button
      type="button"
      onClick={() => void flushQueue().then(() => setCount(queueLength()))}
      className="focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded-full"
      title={t("common.pendingBadge", { count })}
    >
      <Badge className="bg-amber-100 text-amber-900 ring-amber-300">
        ⏳ {t("common.pending")} {count}
      </Badge>
    </button>
  );
}

interface Tab {
  href: string;
  labelKey: string;
  icon: string;
  match: (p: string) => boolean;
}

const TABS: Tab[] = [
  { href: "/", labelKey: "nav.dashboard", icon: "🏠", match: (p) => p === "/" || p.startsWith("/farms") },
  { href: "/fields", labelKey: "nav.fields", icon: "🌾", match: (p) => p.startsWith("/fields") || p.startsWith("/recommendations") },
  { href: "/history", labelKey: "nav.history", icon: "📜", match: (p) => p === "/history" || p.startsWith("/analytics") },
  { href: "/alerts", labelKey: "nav.alerts", icon: "🔔", match: (p) => p.startsWith("/alerts") || p.startsWith("/notifications") },
  { href: "/account", labelKey: "nav.account", icon: "👤", match: (p) => p.startsWith("/account") || p.startsWith("/admin") || p.startsWith("/agronomist") },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { t } = useI18n();
  const { user } = useAuth();
  const pathname = usePathname();

  return (
    <div className="min-h-dvh bg-slate-50">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-lg focus:bg-white focus:px-4 focus:py-2 focus:shadow"
      >
        {t("nav.skipToContent")}
      </a>
      <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-2 px-4 py-3">
          <Link href="/" className="flex items-center gap-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600">
            <span aria-hidden="true" className="text-2xl">🌱</span>
            <span className="text-lg font-extrabold tracking-tight text-emerald-900">{t("common.appName")}</span>
          </Link>
          <div className="flex items-center gap-2">
            <QueueBadge />
            <LanguageToggle user={user} />
          </div>
        </div>
      </header>
      <main id="main" className="mx-auto max-w-3xl px-4 pb-28 pt-4 md:pb-10">
        <div className="mb-3 space-y-2">
          <OfflineBanner />
          {children}
        </div>
      </main>
      <nav
        aria-label={t("nav.bottomNav")}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:static md:border-t"
      >
        <ul className="mx-auto grid max-w-3xl grid-cols-5">
          {TABS.map((tab) => {
            const active = tab.match(pathname);
            return (
              <li key={tab.href}>
                <Link
                  href={tab.href}
                  aria-current={active ? "page" : undefined}
                  className={`flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-emerald-600 ${
                    active ? "text-emerald-800" : "text-slate-500 hover:text-slate-800"
                  }`}
                >
                  <span aria-hidden="true" className="text-xl">
                    {tab.icon}
                  </span>
                  {t(tab.labelKey)}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
      <ToastRegion />
    </div>
  );
}
