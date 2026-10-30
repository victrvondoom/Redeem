import type { Config } from "tailwindcss";

const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"), ink: v("ink"), surface: v("surface"), soft: v("soft"), line: v("line"),
        indigo: { DEFAULT: v("indigo"), soft: v("indigo-soft") }, deep: v("deep"),
        teal: { DEFAULT: v("teal"), soft: v("teal-soft") }, amber: { DEFAULT: v("amber"), soft: v("amber-soft") },
        muted: v("muted"), danger: { DEFAULT: v("danger"), soft: v("danger-soft") },
      },
      fontFamily: {
        sans: ["Manrope", "Noto Sans Devanagari", "Noto Sans Tamil", "Noto Sans Telugu", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      borderRadius: { xl: "14px", "2xl": "20px" },
      boxShadow: { card: "0 1px 2px rgb(20 35 59 / 0.05), 0 4px 16px rgb(20 35 59 / 0.04)" },
    },
  },
  plugins: [],
} satisfies Config;
