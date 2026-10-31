"use client";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** GPU-cheap parallax starfield / data-tunnel on a canvas. Honors prefers-reduced-motion (renders one still frame). */
export function Starfield({ className = "" }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const cv = ref.current; if (!cv) return;
    const ctx = cv.getContext("2d"); if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let w = 0, h = 0, raf = 0, mx = 0, my = 0;
    const N = 170;
    const stars = Array.from({ length: N }, () => ({ x: Math.random() * 2 - 1, y: Math.random() * 2 - 1, z: Math.random() }));
    const resize = () => { const r = cv.getBoundingClientRect(); const dpr = Math.min(2, window.devicePixelRatio || 1); w = cv.width = r.width * dpr; h = cv.height = r.height * dpr; };
    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (const s of stars) {
        if (!reduce) { s.z -= 0.0022; if (s.z <= 0.02) { s.z = 1; s.x = Math.random() * 2 - 1; s.y = Math.random() * 2 - 1; } }
        const k = 1 / s.z;
        const x = w / 2 + (s.x + mx * 0.06) * k * w * 0.12, y = h / 2 + (s.y + my * 0.06) * k * h * 0.12;
        if (x < 0 || x > w || y < 0 || y > h) continue;
        const a = Math.min(1, (1 - s.z) * 1.4), r = Math.max(0.4, (1 - s.z) * 2.4);
        ctx.beginPath(); ctx.fillStyle = `rgba(110,232,255,${a * 0.85})`; ctx.shadowColor = "rgba(70,224,255,.9)"; ctx.shadowBlur = r * 4;
        ctx.arc(x, y, r, 0, 6.283); ctx.fill();
      }
      if (!reduce) raf = requestAnimationFrame(draw);
    };
    const move = (e: PointerEvent) => { mx = e.clientX / window.innerWidth - 0.5; my = e.clientY / window.innerHeight - 0.5; };
    resize(); draw();
    window.addEventListener("resize", resize); window.addEventListener("pointermove", move);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); window.removeEventListener("pointermove", move); };
  }, []);
  return <canvas ref={ref} aria-hidden="true" className={`pointer-events-none absolute inset-0 h-full w-full ${className}`} />;
}

/** Mouse-driven 3D tilt with a moving specular highlight. */
export function Tilt({ children, className = "", max = 10, style }: { children: ReactNode; className?: string; max?: number; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  const on = (e: React.PointerEvent) => {
    const el = ref.current; if (!el || e.pointerType === "touch") return;
    const r = el.getBoundingClientRect(); const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    el.style.transform = `perspective(900px) rotateX(${((0.5 - py) * max).toFixed(2)}deg) rotateY(${((px - 0.5) * max).toFixed(2)}deg) translateZ(0)`;
    el.style.setProperty("--mx", `${(px * 100).toFixed(0)}%`); el.style.setProperty("--my", `${(py * 100).toFixed(0)}%`);
  };
  const off = () => { const el = ref.current; if (el) el.style.transform = ""; };
  return (
    <div ref={ref} onPointerMove={on} onPointerLeave={off} style={{ transition: "transform .25s ease-out", transformStyle: "preserve-3d", ...style }} className={`relative ${className}`}>
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-0 transition-opacity duration-300 [div:hover>&]:opacity-100" style={{ background: "radial-gradient(260px circle at var(--mx,50%) var(--my,50%), rgb(var(--accent) / 0.16), transparent 60%)" }} />
      {children}
    </div>
  );
}

/** Scroll-reveal: slides in from the left/right/bottom when it enters the viewport. */
export function Reveal({ children, from = "up", delay = 0, className = "" }: { children: ReactNode; from?: "up" | "left" | "right"; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { threshold: 0.12 });
    io.observe(el); return () => io.disconnect();
  }, []);
  return <div ref={ref} style={{ transitionDelay: `${delay}ms` }} className={`reveal ${from === "left" ? "from-left" : from === "right" ? "from-right" : ""} ${seen ? "in" : ""} ${className}`}>{children}</div>;
}

export function CountUp({ to, ms = 1400 }: { to: number; ms?: number }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) { setV(to); return; }
    let raf = 0; const t0 = performance.now();
    const step = (t: number) => { const p = Math.min(1, (t - t0) / ms); setV(Math.round(to * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step); return () => cancelAnimationFrame(raf);
  }, [to, ms]);
  return <>{v.toLocaleString("en-IN")}</>;
}

/** Cinematic opening: two wipes slide away while "RE" arrives from the left and "DEEM" from the right. Plays once per tab session. */
export function Intro() {
  const [gone, setGone] = useState(true);
  useEffect(() => {
    const go = () => document.documentElement.setAttribute("data-go", "1");
    let seen = false; try { seen = sessionStorage.getItem("redeem-intro") === "1"; } catch { /* storage may be blocked */ }
    if (seen || window.matchMedia("(prefers-reduced-motion: reduce)").matches) { go(); return; }
    setGone(false);
    try { sessionStorage.setItem("redeem-intro", "1"); } catch { /* ignore */ }
    const a = setTimeout(go, 2600), b = setTimeout(() => setGone(true), 3600);
    return () => { clearTimeout(a); clearTimeout(b); };
  }, []);
  if (gone) return null;
  const word = "font-extrabold leading-none tracking-tighter text-[clamp(3.5rem,13vw,10rem)]";
  return (
    <div aria-hidden="true">
      <div className="intro-wipe-l" /><div className="intro-wipe-r" />
      <div className="intro-word-l"><span className={`${word} glow-text`}>RE</span></div>
      <div className="intro-word-r"><span className={`${word} text-ink`} style={{ textShadow: "0 0 40px rgb(var(--accent)/.5)" }}>DEEM</span></div>
    </div>
  );
}
