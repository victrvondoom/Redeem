const LOCALES: Record<string, string> = { en: "en-IN", hi: "hi-IN", hinglish: "en-IN", ta: "ta-IN", te: "te-IN" };

export const inr = (paise: number | null | undefined, lang = "en") =>
  paise == null ? "—" : new Intl.NumberFormat(LOCALES[lang] ?? "en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(paise / 100);

export const when = (iso: string, lang = "en") =>
  new Intl.DateTimeFormat(LOCALES[lang] ?? "en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" }).format(new Date(iso));

export const TERMINAL = ["VERIFIED", "PARTIALLY_VERIFIED", "FAILED", "CANCELLED", "SUPERSEDED"];
