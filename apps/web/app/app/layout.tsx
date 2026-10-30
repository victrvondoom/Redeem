"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { LangSwitcher, Logo } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

const NAV = [["/app", "side.console"], ["/app/voice", "side.voice"], ["/app/domains", "side.domains"], ["/app/connections", "side.connections"],
  ["/app/vault", "side.vault"], ["/app/history", "side.history"], ["/app/quality", "side.quality"], ["/app/settings", "side.settings"]] as const;

export default function Shell({ children }: { children: ReactNode }) {
  const { me, loading, logout } = useAuth();
  const { t } = useI18n();
  const path = usePathname();
  const router = useRouter();
  useEffect(() => { if (!loading && !me) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [loading, me, path, router]);
  if (loading || !me) return <p className="p-8 text-muted" role="status">Loading…</p>;
  const active = (h: string) => (h === "/app" ? path === "/app" || path.startsWith("/app/missions") : path.startsWith(h));
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="border-b border-line bg-surface lg:sticky lg:top-0 lg:h-screen lg:border-b-0 lg:border-r">
        <div className="flex items-center justify-between px-4 py-3 lg:block lg:px-5 lg:py-5">
          <Link href="/"><Logo /></Link>
          <div className="lg:mt-4"><LangSwitcher /></div>
        </div>
        <nav aria-label="App" className="flex gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible">
          {NAV.map(([href, k]) => (
            <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
              className={`flex min-h-[44px] shrink-0 items-center rounded-xl px-3 text-sm font-semibold ${active(href) ? "bg-indigo-soft text-indigo" : "text-muted hover:bg-soft"}`}>{t(k)}</Link>))}
          <button onClick={async () => { await logout(); router.push("/"); }} className="flex min-h-[44px] shrink-0 items-center rounded-xl px-3 text-left text-sm font-semibold text-muted hover:bg-soft">{t("side.signout")}</button>
        </nav>
      </aside>
      <main id="main" className="min-w-0 px-4 py-6 sm:px-8 lg:py-10">{children}</main>
    </div>
  );
}
