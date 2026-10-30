"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, setCsrf, type Me } from "./api";
import { useI18n } from "./i18n";

type A = { me: Me | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> };
const Auth = createContext<A>({ me: null, loading: true, refresh: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const { setLang } = useI18n();
  const refresh = useCallback(async () => {
    try {
      const m = await api<Me>("/auth/me");
      setCsrf(m.csrf_token);
      setMe(m);
      setLang(m.language);
    } catch (e) {
      if (!(e instanceof ApiError)) console.error(e);
      setMe(null);
    } finally { setLoading(false); }
  }, [setLang]);
  useEffect(() => { void refresh(); }, [refresh]);
  const logout = useCallback(async () => { await api("/auth/logout", { method: "POST" }); setMe(null); setCsrf(""); }, []);
  return <Auth.Provider value={{ me, loading, refresh, logout }}>{children}</Auth.Provider>;
}
export const useAuth = () => useContext(Auth);
