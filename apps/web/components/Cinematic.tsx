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
        ctx.beginPath(); ctx.fillStyle = `rgba(120,255,170,${a * 0.8})`; 
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

/** Partner logo slot. Shows ONLY an official asset placed in /public/brand/<file>; if the file is absent it shows the partner's name as plain text (never a redrawn logo). */
function LogoPlate({ file, name }: { file: string; name: string }) {
  // The official Bolna mark is white-on-transparent, so it sits on a dark plate; Wispr Flow's is black, so it sits on a light one. The files are used unmodified.
  const dark = file.startsWith("bolna");
  const [ok, setOk] = useState(false);
  useEffect(() => { fetch("/brand/manifest.json").then((r) => (r.ok ? r.json() : { files: [] })).then((m: { files: string[] }) => setOk(m.files.includes(file))).catch(() => setOk(false)); }, [file]);
  return (
    <span className={`grid h-full w-full place-items-center rounded-[14%] p-[14%] ${dark ? "bg-[#111] text-white" : "bg-[#f3efe9] text-[#1a1614]"}`}>
      {ok ? // eslint-disable-next-line @next/next/no-img-element
        <img src={`/brand/${file}`} alt={`${name} logo`} onError={() => setOk(false)} className="max-h-full max-w-full object-contain" />
        : <span className="text-center text-[0.8rem] font-extrabold ">{name}</span>}
    </span>
  );
}

function Cube({ file, name }: { file: string; name: string }) {
  const face = "absolute inset-0 border border-white/10";
  return (
    <div className="cube-3d" style={{ ["--s" as string]: "clamp(120px,22vw,200px)" }}>
      <div className={`${face} cube-front`} style={{ transform: "translateZ(calc(var(--s) / 2))" }}><LogoPlate file={file} name={name} /></div>
      <div className={`${face} cube-side`} style={{ transform: "rotateY(90deg) translateZ(calc(var(--s) / 2))" }} />
      <div className={`${face} cube-side`} style={{ transform: "rotateY(-90deg) translateZ(calc(var(--s) / 2))" }} />
      <div className={`${face} cube-top`} style={{ transform: "rotateX(90deg) translateZ(calc(var(--s) / 2))" }} />
      <div className={`${face} cube-side`} style={{ transform: "rotateX(-90deg) translateZ(calc(var(--s) / 2))" }} />
      <div className={`${face} cube-side`} style={{ transform: "rotateY(180deg) translateZ(calc(var(--s) / 2))" }} />
    </div>
  );
}

/**
 * REDEEM identity reveal (~4.6s): a Bolna cube arrives from the left and a Wispr Flow cube from the right, they collide and
 * assemble into the REDEEM emblem, the wordmark rises, the orange tagline follows, then the camera pulls back into the app.
 * Skippable (button / Esc / Enter), replayable (window event "redeem:intro"), disabled for prefers-reduced-motion. Never blocks the page.
 */
export function Intro() {
  const [on, setOn] = useState(false);
  const [run, setRun] = useState(0);
  const end = useRef<ReturnType<typeof setTimeout>>(undefined);
  const finish = () => { clearTimeout(end.current); setOn(false); document.documentElement.setAttribute("data-go", "1"); };
  useEffect(() => {
    const play = () => { setRun((r) => r + 1); setOn(true); clearTimeout(end.current); end.current = setTimeout(finish, 4900); setTimeout(() => document.documentElement.setAttribute("data-go", "1"), 3900); };
    let seen = false; try { seen = sessionStorage.getItem("redeem-intro") === "1"; } catch { /* storage may be blocked */ }
    if (seen || window.matchMedia("(prefers-reduced-motion: reduce)").matches) document.documentElement.setAttribute("data-go", "1");
    else { try { sessionStorage.setItem("redeem-intro", "1"); } catch { /* ignore */ } play(); }
    const onEvt = () => play();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") finish(); };
    window.addEventListener("redeem:intro", onEvt); window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("redeem:intro", onEvt); window.removeEventListener("keydown", onKey); clearTimeout(end.current); };
  }, []);
  if (!on) return null;
  return (
    <div key={run} className="intro-stage" role="presentation" data-testid="intro">
      <div className="intro-vignette" aria-hidden="true" />
      <div className="intro-world" aria-hidden="true">
        <div className="intro-box intro-box-l"><Cube file="bolna.svg" name="Bolna" /></div>
        <div className="intro-box intro-box-r"><Cube file="wispr-flow.svg" name="Wispr Flow" /></div>
        <div className="intro-ring" />
        <div className="intro-emblem"><span>R</span></div>
      </div>
      <div className="intro-title">
        <p className="intro-name pixel" aria-label="REDEEM">{"REDEEM".split("").map((c, i) => <span key={i} style={{ animationDelay: `${2.15 + i * 0.07}s` }}>{c}</span>)}</p>
        <p className="intro-tag">Speak Your Need. We Take the Lead.</p>
      </div>
      <button className="intro-skip" onClick={finish}>Skip intro <kbd>Esc</kbd></button>
    </div>
  );
}
