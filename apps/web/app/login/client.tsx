"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Field, Input, Card } from "@/components/ui";

function errorKey(e: unknown): string {
  if (e instanceof ApiError) {
    switch (e.code) {
      case "auth.invalid_credentials":
      case "invalid_credentials":
        return "errors.invalid_credentials";
      default:
        return e.i18nKey;
    }
  }
  return "errors.network";
}

export function LoginPage() {
  const { t } = useI18n();
  const { login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      const next = params.get("next");
      router.replace(next && next.startsWith("/") ? next : "/");
    } catch (err) {
      setError(errorKey(err));
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 text-center">
        <p className="text-5xl" aria-hidden="true">🌱</p>
        <h1 className="mt-2 text-2xl font-extrabold text-emerald-900">{t("auth.loginTitle")}</h1>
        <p className="text-sm text-slate-600">{t("common.tagline")}</p>
      </div>
      <Card className="p-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {error ? (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-800 ring-1 ring-red-200">
              {t(error)}
            </p>
          ) : null}
          <Field label={t("common.email")} htmlFor="email" required>
            <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field label={t("common.password")} htmlFor="password" required>
            <Input id="password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </Field>
          <Button type="submit" loading={busy} className="w-full">
            {t("auth.loginCta")}
          </Button>
        </form>
      </Card>
      <p className="mt-4 text-center text-sm text-slate-600">
        {t("auth.noAccount")}{" "}
        <Link href="/register" className="font-semibold text-emerald-800 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded">
          {t("common.register")}
        </Link>
      </p>
    </main>
  );
}
