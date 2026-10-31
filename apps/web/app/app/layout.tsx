"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { Icon } from "@/components/Icons";
import { LangSwitcher, Logo } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";

type NavItem = [href: string, key: string, icon: string, badgeKey?: string];
const SECTIONS: { title: string; items: NavItem[] }[] = [
  { title: "Work", items: [["/app", "side.console", "home"], ["/app/cases", "side.cases", "cases", "cases"], ["/app/history", "side.history", "clock"], ["/app/workflows", "side.workflows", "flow"]] },
  { title: "Evidence & tools", items: [["/app/vault", "side.vault", "vault"], ["/app/knowledge", "side.knowledge", "book"], ["/app/files", "side.files", "folder"], ["/app/studio", "side.studio", "pdf"]] },
  { title: "Platform", items: [["/app/domains", "side.domains", "domain"], ["/app/connections", "side.connections", "plug"], ["/app/voice", "side.voice", "voice"]] },
  { title: "Trust", items: [["/app/quality", "side.quality", "flask"], ["/app/demo", "side.demo", "play"], ["/app/settings", "side.settings", "gear"]] },
];

export default function Shell({ children }: { children: ReactNode }) {
  const { me, loading, logout } = useAuth();
  const { t } = useI18n();
  const path = usePathname();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [badges, setBadges] = useState<Record<string, number>>({});
  useEffect(() => { if (!loading && !me) router.replace(`/login?next=${encodeURIComponent(path)}`); }, [loading, me, path, router]);
  useEffect(() => { setOpen(false); }, [path]);
  useEffect(() => {
    if (!me) return;
    const load = () => api<{ attention: unknown[]; counts: { cases_total: number } }>("/overview").then((o) => setBadges({ "/app": o.attention.length, cases: o.counts.cases_total })).catch(() => undefined);
    void load();
    const h = setInterval(load, 8000);
    return () => clearInterval(h);
  }, [me, path]);
  if (loading || !me) return <p className="p-8 text-muted" role="status">Loading…</p>;
  const active = (h: string) => (h === "/app" ? path === "/app" || path.startsWith("/app/missions") : path.startsWith(h));
  const nav = (
    <nav aria-label="App" className="flex flex-col gap-5 px-3 pb-6">
      {SECTIONS.map((s) => (
        <div key={s.title}><p className="mb-1 px-3 text-[11px] font-bold uppercase tracking-wider text-muted">{s.title}</p>
          {s.items.map(([href, k, icon, b]) => {
            const n = href === "/app" ? badges["/app"] : b ? badges[b] : undefined;
            return (
              <Link key={href} href={href} aria-current={active(href) ? "page" : undefined}
                className={`flex min-h-[40px] items-center gap-3 rounded-xl px-3 text-sm font-semibold ${active(href) ? "bg-indigo-soft text-indigo" : "text-muted hover:bg-soft hover:text-ink"}`}>
                <Icon name={icon} size={17} /><span className="flex-1">{t(k)}</span>
                {n ? <span className={`rounded-full px-2 py-0.5 text-[11px] ${href === "/app" ? "bg-amber-soft text-ink" : "bg-soft text-muted"}`}>{n}</span> : null}
              </Link>);
          })}
        </div>))}
      <button onClick={async () => { await logout(); router.push("/"); }} className="flex min-h-[40px] items-center gap-3 rounded-xl px-3 text-left text-sm font-semibold text-muted hover:bg-soft">{t("side.signout")}</button>
    </nav>
  );
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[264px_1fr]">
      <aside className="hidden border-r border-line bg-surface lg:sticky lg:top-0 lg:block lg:h-screen lg:overflow-y-auto">
        <div className="px-5 py-5"><Link href="/"><Logo /></Link><div className="mt-4"><LangSwitcher /></div></div>
        {nav}
      </aside>
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-surface/95 px-4 py-2 backdrop-blur lg:hidden">
        <Link href="/"><Logo /></Link>
        <div className="flex items-center gap-2"><LangSwitcher /><button className="btn-ghost px-3" aria-expanded={open} aria-controls="mobile-nav" onClick={() => setOpen(!open)}>{open ? "Close" : "Menu"}</button></div>
      </header>
      {open && <div id="mobile-nav" className="fixed inset-x-0 top-[57px] z-20 max-h-[calc(100vh-57px)] overflow-y-auto border-b border-line bg-surface pt-3 lg:hidden">{nav}</div>}
      <main id="main" className="min-w-0 px-4 py-6 sm:px-8 lg:py-10">{children}</main>
    </div>
  );
}
