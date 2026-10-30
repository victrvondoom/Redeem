import next from "eslint-config-next";

export default [
  ...next,
  { ignores: [".next/**", "node_modules/**", "tests/**", "playwright.config.ts", "postcss.config.mjs"] },
  // Data-on-mount effects (fetch → setState) are intentional in this client-rendered app; kept visible as warnings.
  { rules: { "react-hooks/set-state-in-effect": "warn" } },
];
