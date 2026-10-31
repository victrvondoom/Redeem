"use client";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { LangSwitcher, Logo } from "./ui";

export function SiteNav() {
  const { t } = useI18n();
  const { me } = useAuth();
  const links = [["#product", "nav.product"], ["#how", "nav.how"], ["#solutions", "nav.solutions"], ["#security", "nav.security"],
    ["#business", "nav.business"], ["#developers", "nav.developers"]] as const;
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-2 sm:px-6">
        <Link href="/" aria-label="REDEEM home"><Logo /></Link>
        <nav aria-label="Primary" className="hidden items-center gap-5 lg:flex">
          {links.map(([href, k]) => <a key={k} href={href} className="text-sm font-semibold text-muted hover:text-ink">{t(k)}</a>)}
        </nav>
        <div className="flex items-center gap-2">
          <LangSwitcher className="hidden sm:inline-flex" />
          {me ? <Link href="/app" className="btn-primary">Open console</Link> : (<>
            <Link href="/login" className="btn-ghost hidden sm:inline-flex">{t("nav.signin")}</Link>
            <Link href="/register" className="btn-primary">{t("nav.start")}</Link></>)}
        </div>
      </div>
      <details className="border-t border-line px-4 py-2 lg:hidden">
        <summary className="flex min-h-[44px] cursor-pointer items-center text-sm font-semibold">Menu</summary>
        <div className="flex flex-col gap-1 pb-2">
          {links.map(([href, k]) => <a key={k} href={href} className="flex min-h-[44px] items-center text-sm">{t(k)}</a>)}
          <div className="flex items-center gap-2 pt-1"><LangSwitcher className="sm:hidden" />{!me && <Link href="/login" className="btn-ghost sm:hidden">{t("nav.signin")}</Link>}</div>
        </div>
      </details>
    </header>
  );
}
