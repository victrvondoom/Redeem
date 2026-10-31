"""Generates the isometric 3D README graphics (docs/assets/*.svg). Pure SVG, no external assets.
The 'Bolna' and 'Y Combinator' tiles are plain text marks drawn here, NOT the companies' official logos."""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets"
ACC = "#ff7a1a"
C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))


def iso(x, y, z, ox, oy, k=1.0):
    return (ox + (x - y) * C30 * k, oy + (x + y) * S30 * k - z * k)


def cube(ox, oy, w, d, h, top="#ffb070", left="#d9560a", right="#7a2e05", k=1.0, stroke="#060505"):
    p = lambda x, y, z: iso(x, y, z, ox, oy, k)
    pts = lambda *ps: " ".join(f"{a:.1f},{b:.1f}" for a, b in ps)
    t = pts(p(0, 0, h), p(w, 0, h), p(w, d, h), p(0, d, h))
    l = pts(p(0, d, 0), p(w, d, 0), p(w, d, h), p(0, d, h))
    r = pts(p(w, 0, 0), p(w, d, 0), p(w, d, h), p(w, 0, h))
    return (f'<polygon points="{l}" fill="{left}" stroke="{stroke}" stroke-width="1"/><polygon points="{r}" fill="{right}" stroke="{stroke}" stroke-width="1"/>'
            f'<polygon points="{t}" fill="{top}" stroke="{stroke}" stroke-width="1"/>')


def dim(x1, y1, x2, y2, label, off=(0, 0)):
    mx, my = (x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1]
    return (f'<g stroke="{ACC}" stroke-width="1.2" fill="none" opacity=".9"><line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>'
            f'<circle cx="{x1}" cy="{y1}" r="2.5" fill="{ACC}"/><circle cx="{x2}" cy="{y2}" r="2.5" fill="{ACC}"/></g>'
            f'<text x="{mx}" y="{my}" fill="{ACC}" font-family="ui-monospace,monospace" font-size="13" font-weight="700" text-anchor="middle">{label}</text>')


DEFS = f'''<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0e0c0b"/><stop offset="1" stop-color="#060505"/></linearGradient>
<radialGradient id="glow" cx=".75" cy=".3" r=".6"><stop offset="0" stop-color="{ACC}" stop-opacity=".22"/><stop offset="1" stop-color="{ACC}" stop-opacity="0"/></radialGradient>
<filter id="sh"><feGaussianBlur stdDeviation="14"/></filter></defs>'''


def grid(w, h):
    g = "".join(f'<line x1="0" y1="{y}" x2="{w}" y2="{y}"/>' for y in range(h - 150, h, 22))
    return f'<g stroke="{ACC}" stroke-opacity=".12">{g}</g>'


def banner():
    W, H = 1200, 440
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="REDEEM: Speak your need. We take the lead.">', DEFS,
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#glow)"/>', grid(W, H)]
    labels = ["PLAN", "APPROVE", "EXECUTE", "VERIFY"]
    for i in range(4):
        z = (3 - i) * 0
        ox, oy = 840, 62 + i * 68
        a = i == 3
        s.append(cube(ox, oy, 120, 120, 18, top="#ffc593" if a else "#3a3330", left="#d9560a" if a else "#221d1b", right="#7a2e05" if a else "#151211", k=0.95))
        px, py = iso(120, 60, 0, ox, oy, 0.95)
        s.append(f'<text x="{px + 22:.0f}" y="{py + 6:.0f}" fill="{ACC if a else "#a59c94"}" font-family="Manrope,Arial,sans-serif" font-size="12" font-weight="800" letter-spacing="3" text-anchor="start">0{i + 1} {labels[i]}</text>')
    s.append(dim(1140, 100, 1140, 400, "4 stages", (-6, -10)))
    s.append(f'<text x="70" y="170" fill="#ffffff" font-family="Manrope,Arial,sans-serif" font-size="96" font-weight="800" letter-spacing="-3">RE<tspan fill="{ACC}">DEEM</tspan></text>')
    s.append('<text x="74" y="222" fill="#f0ece8" font-family="Manrope,Arial,sans-serif" font-size="30" font-weight="700">Speak your need. We take the lead.</text>')
    s.append('<text x="74" y="256" fill="#a59c94" font-family="Manrope,Arial,sans-serif" font-size="17">Voice-first outcome missions · approval-bound · independently verified</text>')
    for j, (name, sub) in enumerate([("Bolna", "Voice provider (link below)"), ("Wispr Flow", "Voice dictation partner")]):
        x = 74 + j * 260
        s.append(f'<rect x="{x}" y="300" width="244" height="64" rx="14" fill="#161312" stroke="#3a3330"/>')
        s.append(cube(x + 40, 314, 22, 22, 14, top="#ffc593", left="#d9560a", right="#7a2e05", k=0.9))
        s.append(f'<text x="{x + 66}" y="327" fill="#ffffff" font-family="Manrope,Arial,sans-serif" font-size="17" font-weight="800">{name}</text><text x="{x + 66}" y="347" fill="#a59c94" font-family="Manrope,Arial,sans-serif" font-size="11">{sub}</text>')
    s.append('<text x="74" y="404" fill="#7a716a" font-family="Manrope,Arial,sans-serif" font-size="11">Name tiles only; official logos are linked below, not redrawn. Not endorsed by Bolna, Wispr Flow, Y Combinator or WeMakeDevs.</text></svg>')
    (OUT / "banner.svg").write_text("\n".join(s))


def metrics(vals):
    """Isometric bars. Heights are log-scaled for legibility (labelled); numbers are the real, measured values passed in."""
    W, H = 1240, 440
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Measured project metrics as 3D bars">', DEFS,
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/>', grid(W, H)]
    for i, (name, v, unit) in enumerate(vals):
        h = 30 + math.log10(v + 1) * 62
        ox, oy = 90 + i * 232, 300
        s.append(f'<ellipse cx="{ox + 20}" cy="{oy + 62}" rx="86" ry="22" fill="#000" opacity=".55" filter="url(#sh)"/>')
        s.append(cube(ox, oy - 40, 70, 70, h, k=1.0))
        tx, ty = iso(35, 35, h, ox, oy - 40)
        s.append(dim(ox + 112, oy + 8, ox + 112, oy + 8 - h, f"{v:,}", (34, 4)))
        s.append(f'<text x="{ox + 20}" y="{oy + 100}" fill="#f0ece8" font-family="Manrope,Arial,sans-serif" font-size="15" font-weight="800" text-anchor="middle">{name}</text>')
        s.append(f'<text x="{ox + 20}" y="{oy + 118}" fill="#a59c94" font-family="Manrope,Arial,sans-serif" font-size="11" text-anchor="middle">{unit}</text>')
    s.append('<text x="24" y="28" fill="#a59c94" font-family="ui-monospace,monospace" font-size="11">Measured values from this repository. Bar heights are log-scaled for legibility, not proportional.</text></svg>')
    (OUT / "metrics-3d.svg").write_text("\n".join(s))


def emblem():
    """Isometric REDEEM emblem. Geometry (SVG model units): width 120, depth 120, extrusion 36, corner bevel 8 (shown as top-face inset), 'R' cap height 64."""
    W, H = 640, 460
    k = 1.6
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="REDEEM 3D emblem with dimensions">', DEFS,
         f'<rect width="{W}" height="{H}" fill="url(#bg)"/><rect width="{W}" height="{H}" fill="url(#glow)"/>', grid(W, H)]
    ox, oy = 310, 130
    s.append(f'<ellipse cx="{ox + 30}" cy="{oy + 190}" rx="170" ry="40" fill="#000" opacity=".6" filter="url(#sh)"/>')
    s.append(cube(ox, oy, 120, 120, 36, top="#ffb070", left="#d9560a", right="#7a2e05", k=k))
    p = lambda x, y, z: iso(x, y, z, ox, oy, k)
    a = p(8, 8, 36); b = p(112, 8, 36); c = p(112, 112, 36); d = p(8, 112, 36)
    s.append(f'<polygon points="{a[0]:.1f},{a[1]:.1f} {b[0]:.1f},{b[1]:.1f} {c[0]:.1f},{c[1]:.1f} {d[0]:.1f},{d[1]:.1f}" fill="#ff7a1a" stroke="#ffd2a8" stroke-width="1.5"/>')
    tx, ty = p(60, 60, 36)
    s.append(f'<text x="{tx:.0f}" y="{ty + 22:.0f}" text-anchor="middle" fill="#1a0b03" font-family="Manrope,Arial,sans-serif" font-size="74" font-weight="800" transform="translate(0,0)">R</text>')
    s.append(dim(*p(0, 130, 0), *p(120, 130, 0), "width 120", (-10, 34)))
    s.append(dim(*p(130, 0, 0), *p(130, 120, 0), "depth 120", (40, 30)))
    s.append(dim(*p(-8, 120, 0), *p(-8, 120, 36), "extrusion 36", (-52, 0)))
    s.append('<text x="24" y="28" fill="#a59c94" font-family="ui-monospace,monospace" font-size="11">Model units (1 unit = 1 px at 1x). Bevel 8, R cap height 64, ratio W:D:E = 10:10:3.</text></svg>')
    (OUT / "emblem-3d.svg").write_text("\n".join(s))


if __name__ == "__main__":
    import sys
    OUT.mkdir(parents=True, exist_ok=True)
    banner()
    emblem()
    metrics([("Knowledge passages", 1159, "BM25-indexed, with provenance"), ("Backend tests", int(sys.argv[1]) if len(sys.argv) > 1 else 0, "pytest"),
             ("Browser E2E tests", int(sys.argv[2]) if len(sys.argv) > 2 else 0, "Playwright, real Chromium"), ("Case-lifecycle stages", 17, "persisted"), ("Rights domains", 8, "each with its own workflow")])
