// Tiny i18n: dictionaries + t(key, params) + React context with persisted
// language (localStorage, and PUT /auth/me/preferences is handled by the
// language toggle component when logged in).

"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { STORAGE_KEYS, lsGet, lsSet } from "@/lib/storage";
import en from "@/lib/i18n/locales/en.json";
import hi from "@/lib/i18n/locales/hi.json";

export type Lang = "en" | "hi";

export type Dict = Record<string, string>;

const dictionaries: Record<Lang, Dict> = {
  en: en as Dict,
  hi: hi as Dict,
};

export type Params = Record<string, string | number | boolean | undefined | null>;

/** Translate with {param} interpolation. Missing keys render the raw key. */
export function translate(lang: Lang, key: string, params?: Params | null): string {
  const template = dictionaries[lang][key] ?? dictionaries.en[key] ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (m, name: string) => {
    const v = params[name];
    return v === undefined || v === null ? m : String(v);
  });
}

interface I18nContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: string, params?: Params | null) => string;
}

const I18nContext = createContext<I18nContextValue>({
  lang: "en",
  setLang: () => undefined,
  t: (key) => key,
});

function initialLang(): Lang {
  if (typeof window === "undefined") return "en";
  const saved = lsGet(STORAGE_KEYS.lang);
  if (saved === "en" || saved === "hi") return saved;
  return navigator.language?.startsWith("hi") ? "hi" : "en";
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");

  // Resolve after mount to keep SSR/prerender deterministic.
  useEffect(() => {
    setLangState(initialLang());
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = lang;
    }
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    lsSet(STORAGE_KEYS.lang, l);
    if (typeof document !== "undefined") document.documentElement.lang = l;
  }, []);

  const t = useCallback(
    (key: string, params?: Params | null) => translate(lang, key, params),
    [lang],
  );

  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}
