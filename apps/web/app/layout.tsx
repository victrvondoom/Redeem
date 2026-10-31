import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { I18nProvider } from "@/lib/i18n";
import { AuthProvider } from "@/lib/auth";

export const metadata: Metadata = {
  title: "REDEEM — Speak your need. We take the lead.",
  description: "Voice-first agent platform that takes authorized action across services and independently verifies the outcome.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0a0909" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en-IN">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* Runtime webfonts with system fallbacks (Latin + Devanagari + Tamil + Telugu). */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&family=Noto+Sans+Devanagari:wght@400;600;700&family=Noto+Sans+Tamil:wght@400;600;700&family=Noto+Sans+Telugu:wght@400;600;700&display=swap" />
      </head>
      <body>
        <I18nProvider><AuthProvider>
          <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-xl focus:bg-surface focus:px-4 focus:py-3">Skip to content</a>
          {children}
        </AuthProvider></I18nProvider>
      </body>
    </html>
  );
}
