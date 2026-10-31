# Prompt: cinematic, "console-grade" 3D UX for a web product

Reusable prompt for an AI coding agent. It is written from what was actually built in this repo (`apps/web/components/Cinematic.tsx`, `Showcase.tsx`, `app/page.tsx`, `app/app/live/page.tsx`), so every instruction maps to something verifiable. A browser cannot match a native game engine (Unreal/PS5); this prompt asks for the strongest result the web platform can deliver without a WebGL dependency, and says how to add WebGL if wanted.

```text
ROLE
You are a principal product designer + creative front-end engineer. Build a cinematic, premium, fully dynamic UI for <PRODUCT>. Nothing decorative may be fake data: every number, list, chart and animation must be driven by real state or an API, or be explicitly labelled "simulation".

ART DIRECTION (single-accent system)
- Graphite/near-black base (#05070C) and exactly ONE accent hue (plasma cyan #46E0FF). No rainbow palettes. Warning/error colours exist only for real warnings/errors.
- 3D "polished glass" cards: layered gradient fill, 1px inner highlight, soft deep shadow, accent glow on hover, backdrop blur, mouse-driven tilt (+-10deg) with a moving specular highlight.
- Type: Manrope (or Inter), tight tracking on display sizes, wide-tracked 11-12px caps for eyebrows. Generous whitespace, few words, one idea per screen.

CINEMATIC INTRO (plays once per tab session, skipped for prefers-reduced-motion)
1. Black screen. The left half of the wordmark ("RE") flies in from the left in 3D (perspective + rotateY 70deg -> 0), the right half ("DEEM") from the right, meeting on a glowing 1px accent seam.
2. Hold 300ms, the wordmark blurs out, two curtains slide apart (left/right) on an ease-out-expo curve.
3. Hero content rises in (translateY 26px -> 0, opacity 0 -> 1) staggered 120ms.
Never block interaction: overlays are pointer-events:none; content is in the DOM from first paint (SEO and tests see it).

HERO
- Canvas starfield/data-tunnel with pointer parallax, an animated perspective grid floor, and an exploded 3D stack of the product's stages (translateZ layers, cycling active layer, pointer-driven rotation).
- A live stats strip fed by an unauthenticated, aggregate-only endpoint (count-up animation, honest footer "live from this deployment; includes demo fixtures").

LIVE ENGINE (the proof screen)
- Run a real workflow on demand, then replay its append-only event log like a video: play/pause, scrubber, 0.5x-4x speed, task DAG nodes that light up when the event that proves them arrives, edges that glow, a streaming ledger, and a final verified outcome with a link to the receipt.
- Playback must be derived from stored events, not scripted.

MOTION RULES
- Only transform/opacity are animated. 60fps budget; canvas capped at ~170 particles; DPR capped at 2.
- Scroll reveals via IntersectionObserver, alternating left/right entrances with a slight rotateY.
- Respect prefers-reduced-motion everywhere (content must still be visible: no opacity:0 left behind).

QUALITY BAR
- WCAG AA contrast on the dark theme, visible focus rings in the accent, 44px touch targets, no horizontal overflow at 360px.
- Keyboard-operable playback controls, aria-live on outcome, role=img + label on SVG diagrams.
- Tests: real-browser E2E for the intro not blocking clicks, the live run, reduced-motion visibility, and overflow at 390/360.

PRIVACY (state it in the UI)
- Sensitive documents are encrypted at rest (AES-256-GCM, per-tenant HKDF key for file bytes) and never shown to other tenants. Say plainly what this does and does not protect (server holds the key; not end-to-end).

DELIVERABLES
Code, screenshots at 1440 and 390 widths, an animated capture of the intro and of the live run, and a README that embeds them. Report what is simulated vs real.

OPTIONAL: true WebGL
If you want real-time 3D beyond CSS: add three.js (pinned version) with one InstancedMesh particle field and one GLB hero object (<=1.5MB, Draco), render on demand, fall back to the CSS scene when WebGL is unavailable. Do not ship anything that hides content behind a loading screen.
```
