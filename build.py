#!/usr/bin/env python3
"""Build script for رویاچین (wish/wallet app).

Produces:
  workers.js   — a single-file, self-contained worker script (Cloudflare Workers /
                 Deno Deploy / Bun / Node). Serves the full app + offline service
                 worker + icons, all inline as a JS string.
  preview.html — a standalone HTML preview of the app for desktop browsers.
"""
import base64
import io
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(ROOT, "src")
SRC = os.path.join(SRC_DIR, "app.html")
OUT_JS = os.path.join(ROOT, "workers.js")
OUT_HTML = os.path.join(ROOT, "preview.html")

with io.open(SRC, encoding="utf-8") as fh:
    html = fh.read()

# ---------- 1) make the inline app fully self-contained ----------
# drop the CDN font link, embed Vazirmatn woff2 directly
app = html.replace(
    '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css">',
    "",
)

def _load_font(path):
    p = os.path.join(SRC_DIR, path)
    if not os.path.exists(p):
        print("! font missing:", p)
        return ""
    with open(p, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return b64

REG_B64 = _load_font(os.path.join("fonts", "vazir-regular.woff2"))
BOLD_B64 = _load_font(os.path.join("fonts", "vazir-bold.woff2"))
FONTFACE = (
    "@font-face{font-family:'Vazirmatn';src:url(data:font/woff2;base64,"
    + REG_B64
    + ") format('woff2');font-weight:100 500;font-style:normal;font-display:swap}"
    "@font-face{font-family:'Vazirmatn';src:url(data:font/woff2;base64,"
    + BOLD_B64
    + ") format('woff2');font-weight:600 900;font-style:normal;font-display:swap}"
)
app = app.replace("/*FONTFACE_PLACEHOLDER*/", FONTFACE)

# ---------- 2) generate the app icon (dream moon & stars — matches "رویاچین") ----------
try:
    from PIL import Image, ImageDraw
    import math

    S = 512
    img = Image.new("RGBA", (S, S), (8, 6, 26, 255))
    d = ImageDraw.Draw(img)

    # --- dreamy nebula glow background ---
    cx, cy = S/2, S/2
    for radius, col in ((300, (124, 92, 255, 40)), (215, (0, 229, 195, 28)),
                        (150, (255, 217, 61, 20))):
        d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                  fill=col)

    # --- gradient-ish night backdrop (rounded square) ---
    def draw_gradient(bbox, c1, c2):
        x0, y0, x1, y1 = bbox
        for y in range(int(y0), int(y1)):
            t = (y - y0) / max(1, (y1 - y0))
            col = (int(c1[0] + (c2[0]-c1[0])*t),
                   int(c1[1] + (c2[1]-c1[1])*t),
                   int(c1[2] + (c2[2]-c1[2])*t), 255)
            d.line([x0, y, x1, y], fill=col)
    draw_gradient((36, 36, 476, 476), (20, 16, 52), (12, 30, 66))

    # rounded mask to frame the gradient
    mask = Image.new("L", (S, S), 0)
    dm = ImageDraw.Draw(mask)
    dm.rounded_rectangle([36, 36, 476, 476], radius=72, fill=255)
    img.putalpha(mask)

    # --- stars (4-point sparkles) ---
    def star(cx0, cy0, r, col, width=6):
        n = 4
        pts = []
        for i in range(n * 2):
            ang = math.pi * i / n - math.pi / 2
            rad = r if i % 2 == 0 else r * 0.35
            pts.append((cx0 + rad * math.cos(ang), cy0 + rad * math.sin(ang)))
        d.polygon(pts, fill=col)
        d.line([cx0 - r, cy0, cx0 + r, cy0], fill=col, width=width)
        d.line([cx0, cy0 - r, cx0, cy0 + r], fill=col, width=width)

    stars = [(392, 128, 26), (132, 180, 18), (396, 320, 16), (200, 356, 14),
             (150, 96, 12), (430, 232, 12)]
    for sx, sy, sr in stars:
        star(sx, sy, sr, (255, 255, 255, 235))

    # --- glowing crescent moon (the "dream") ---
    moon_c = (256, 220)
    R = 132
    # outer glow rings
    for rr, alpha in ((R + 42, 30), (R + 26, 50)):
        d.ellipse([moon_c[0]-rr, moon_c[1]-rr, moon_c[0]+rr, moon_c[1]+rr],
                  fill=(255, 217, 61, alpha))
    # golden moon body
    d.ellipse([moon_c[0]-R, moon_c[1]-R, moon_c[0]+R, moon_c[1]+R],
              fill=(255, 217, 61, 255))
    # crescent cut (offset darker disc)
    d.ellipse([moon_c[0]-R+56, moon_c[1]-R-30, moon_c[0]+R+40, moon_c[1]+R-20],
              fill=(16, 22, 58, 255))
    # inner shading hint
    d.ellipse([moon_c[0]-R+30, moon_c[1]-R+30, moon_c[0]+R-44, moon_c[1]+R-44],
              outline=(214, 178, 40, 160), width=4)

    # --- a small "dream catcher" / wishing coin tied to the moon ---
    # tiny star inside the crescent opening
    star(216, 300, 22, (0, 229, 195, 255), width=5)
    # three dots as a falling-star trail
    for dx, rr in ((286, 8), (314, 5), (336, 3)):
        d.ellipse([286 + dx - rr, 350 - rr, 286 + dx + rr, 350 + rr],
                  fill=(0, 229, 195, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    ICON_512 = buf.getvalue()
    img192 = img.resize((192, 192), Image.LANCZOS)
    buf2 = io.BytesIO()
    img192.save(buf2, format="PNG")
    ICON_192 = buf2.getvalue()
except Exception as exc:  # pragma: no cover
    print("! icon generation failed:", exc)
    ICON_192 = ICON_512 = b""

ICON_192_B64 = base64.b64encode(ICON_192).decode("ascii")
ICON_512_B64 = base64.b64encode(ICON_512).decode("ascii")

# ---------- 3) build a lean offline service worker ----------
SW = """'use strict';
var C='kwp-v1';
self.addEventListener('install',function(e){ self.skipWaiting(); e.waitUntil(caches.open(C).then(function(c){ return c.addAll(['/']); })); });
self.addEventListener('activate',function(e){ e.waitUntil(caches.keys().then(function(ks){ return Promise.all(ks.filter(function(k){ return k!==C; }).map(function(k){ return caches.delete(k); })); })); });
self.addEventListener('fetch',function(e){
  if(e.request.method!=='GET') return;
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(function(r){
    var n=fetch(e.request).then(function(res){
      if(res && res.ok){ var cp=res.clone(); caches.open(C).then(function(c){ c.put(e.request,cp); }); }
      return res;
    }).catch(function(){ return r; });
    return r||n;
  }));
});
"""

# ---------- 4) assemble the worker script ----------
MANIFEST = json.dumps({
    "name": "رویاچین — آرزوها و مدیریت هزینه‌ها",
    "short_name": "رویاچین",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "dir": "rtl",
    "lang": "fa",
    "background_color": "#0a0a1a",
    "theme_color": "#0a0a1a",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
    ],
}, ensure_ascii=False)

HEADER = "// رویاچین — آرزوها و مدیریت هزینه‌ها (Persian RTL wish/wallet app)\n" \
         "// Single-file worker: Cloudflare Workers / Deno Deploy / Bun / Node\n" \
         "// Build date: " + __import__("datetime").date.today().isoformat() + "\n"
def b64const(data):
    """Emit a JS expression that turns base64 into a Uint8Array."""
    return 'Uint8Array.from(atob(' + repr(data) + '), function(c){ return c.charCodeAt(0); })'

WORKER_API = """
    // ---- cloud sync API (Cloudflare KV) ----
    if (p === '/api/state') {
      const room = (url.searchParams.get('room') || '').trim().toLowerCase();
      const corsH = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, PUT, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
      };
      if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsH });
      if (!room) return new Response(JSON.stringify({ error: 'room required' }), { status: 400, headers: corsH });
      const key = 'room:' + room;
      const m = request.method.toUpperCase();
      if (m === 'GET') {
        const val = (env && env.KWP_KV) ? await env.KWP_KV.get(key, 'json') : null;
        return new Response(JSON.stringify(val || { v: 1, items: {}, ts: 0 }), { headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, corsH) });
      }
      if (m === 'PUT') {
        let body = null;
        try { body = await request.json(); } catch (e) {}
        if (!body || typeof body !== 'object' || !body.items || typeof body.items !== 'object') {
          return new Response(JSON.stringify({ error: 'invalid payload' }), { status: 400, headers: corsH });
        }
        if (env && env.KWP_KV) { await env.KWP_KV.put(key, JSON.stringify(body)); }
        return new Response(JSON.stringify(body), { headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, corsH) });
      }
      if (m === 'DELETE') {
        if (env && env.KWP_KV) { await env.KWP_KV.delete(key); }
        return new Response(JSON.stringify({ ok: true }), { headers: Object.assign({ 'Content-Type': 'application/json; charset=utf-8' }, corsH) });
      }
      return new Response('Method Not Allowed', { status: 405, headers: corsH });
    }
"""

JS = HEADER + "export default {\n" \
     "  async fetch(request, env, ctx) {\n" \
     "    const url = new URL(request.url);\n" \
     "    const APP = " + repr(app) + ";\n" \
     "    const SW  = " + repr(SW) + ";\n" \
     "    const IC192 = " + b64const(ICON_192_B64) + ";\n" \
     "    const IC512 = " + b64const(ICON_512_B64) + ";\n" \
     "    const MANIFEST = " + repr(MANIFEST) + ";\n" \
     "    const headers = { 'Content-Type': 'text/html; charset=utf-8' };\n" \
     "    const p = url.pathname;\n" \
     + WORKER_API + \
     "    if (p === '/sw.js') return new Response(SW, { headers: { 'Content-Type': 'application/javascript; charset=utf-8' } });\n" \
     "    if (p === '/manifest.webmanifest') return new Response(MANIFEST, { headers: { 'Content-Type': 'application/manifest+json; charset=utf-8' } });\n" \
     "    if (p === '/icon-192.png') return new Response(IC192, { headers: { 'Content-Type': 'image/png' } });\n" \
     "    if (p === '/icon-512.png') return new Response(IC512, { headers: { 'Content-Type': 'image/png' } });\n" \
     "    return new Response(APP, { headers });\n" \
     "  },\n" \
     "};\n"

with io.open(OUT_JS, "w", encoding="utf-8") as fh:
    fh.write(JS)

# ---------- 5) standalone preview (all inline, no external resources) ----------
# replace the font <link> with an inline @font-face placeholder class that falls
# back to Tahoma, and strip the service-worker registration (no /sw.js locally)
preview = app.replace(
    "</head>",
    "<style>@font-face{font-family:'Vazirmatn';src:local('Vazirmatn');}</style>"
    "<script>window.__PREVIEW__=true;</script></head>",
).replace(
    "if('serviceWorker' in navigator){",
    "if(false){",
)
with io.open(OUT_HTML, "w", encoding="utf-8") as fh:
    fh.write(preview)

print("workers.js  :", os.path.getsize(OUT_JS), "bytes")
print("preview.html:", os.path.getsize(OUT_HTML), "bytes")
