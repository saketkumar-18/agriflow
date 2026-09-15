"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useI18n } from "@/lib/i18n";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Field, Input, Card } from "@/components/ui";

export function RegisterPage() {
  const { t, lang } = useI18n();
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", phone: "", password: "", confirm: "" });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (!form.full_name.trim()) errs.full_name = "common.required";
    if (!form.email.trim()) errs.email = "common.required";
    if (form.password.length < 8) errs.password = "errors.short_password";
    if (form.password !== form.confirm) errs.confirm = "errors.validation";
    setFieldErrors(errs);
    return Object.keys(errs).length === 0;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setServerError(null);
    if (!validate()) return;
    setBusy(true);
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || undefined,
        language: lang,
      });
      router.replace("/farms/new");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 422) setServerError("errors.validation");
        else if (err.code.includes("email") || err.status === 409) setServerError("errors.email_taken");
        else setServerError(err.i18nKey);
      } else {
        setServerError("errors.network");
      }
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-md flex-col justify-center px-4 py-10">
      <div className="mb-6 text-center">
        <p className="text-5xl" aria-hidden="true">🌱</p>
        <h1 className="mt-2 text-2xl font-extrabold text-emerald-900">{t("auth.registerTitle")}</h1>
      </div>
      <Card className="p-5">
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          {serverError ? (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-800 ring-1 ring-red-200">
              {t(serverError)}
            </p>
          ) : null}
          <Field label={t("common.fullName")} htmlFor="full_name" required error={fieldErrors.full_name ? t(fieldErrors.full_name) : undefined}>
            <Input id="full_name" autoComplete="name" required value={form.full_name} onChange={set("full_name")} aria-invalid={!!fieldErrors.full_name} />
          </Field>
          <Field label={t("common.email")} htmlFor="email" required error={fieldErrors.email ? t(fieldErrors.email) : undefined}>
            <Input id="email" type="email" autoComplete="email" required value={form.email} onChange={set("email")} aria-invalid={!!fieldErrors.email} />
          </Field>
          <Field label={`${t("common.phone")} (${t("common.optional")})`} htmlFor="phone">
            <Input id="phone" type="tel" autoComplete="tel" value={form.phone} onChange={set("phone")} />
          </Field>
          <Field label={t("common.password")} htmlFor="password" required hint={t("auth.passwordHint")} error={fieldErrors.password ? t(fieldErrors.password) : undefined}>
            <Input id="password" type="password" autoComplete="new-password" required value={form.password} onChange={set("password")} aria-invalid={!!fieldErrors.password} />
          </Field>
          <Field label={t("common.confirmPassword")} htmlFor="confirm" required error={fieldErrors.confirm ? t(fieldErrors.confirm) : undefined}>
            <Input id="confirm" type="password" autoComplete="new-password" required value={form.confirm} onChange={set("confirm")} aria-invalid={!!fieldErrors.confirm} />
          </Field>
          <Button type="submit" loading={busy} className="w-full">
            {t("auth.registerCta")}
          </Button>
        </form>
      </Card>
      <p className="mt-4 text-center text-sm text-slate-600">
        {t("auth.haveAccount")}{" "}
        <Link href="/login" className="font-semibold text-emerald-800 underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded">
          {t("common.login")}
        </Link>
      </p>
    </main>
  );
}
