"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Lang } from "./api";
import { HTML_LANG, MESSAGES } from "./messages";

type Ctx = { lang: Lang; setLang: (l: Lang) => void; t: (k: string) => string };
const I18n = createContext<Ctx>({ lang: "en", setLang: () => {}, t: (k) => k });
const KEY = "redeem_lang";

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY) as Lang | null;
      if (saved && saved in MESSAGES) setLangState(saved);
    } catch { /* storage unavailable: default language */ }
  }, []);
  useEffect(() => { document.documentElement.lang = HTML_LANG[lang]; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
  }, []);
  const t = useCallback((k: string) => MESSAGES[lang][k] ?? MESSAGES.en[k] ?? k, [lang]);
  const value = useMemo(() => ({ lang, setLang, t }), [lang, setLang, t]);
  return <I18n.Provider value={value}>{children}</I18n.Provider>;
}
export const useI18n = () => useContext(I18n);
