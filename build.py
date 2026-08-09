#!/usr/bin/env python3
"""Build script for کیف‌پول من (Wallet app).

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

# ---------- 2) generate the app icon (neon wallet on dark background) ----------
try:
    from PIL import Image, ImageDraw

    S = 512
    img = Image.new("RGBA", (S, S), (10, 10, 26, 255))
    d = ImageDraw.Draw(img)

    # soft glow behind the wallet
    for radius, col in ((210, (124, 92, 255, 26)), (150, (0, 229, 195, 16))):
        d.rounded_rectangle(
            [S/2 - radius, S/2 - radius, S/2 + radius, S/2 + radius],
            radius=radius,
            fill=col,
        )

    # wallet body
    w_left, w_top, w_right, w_bottom = 96, 136, 416, 376
    d.rounded_rectangle([w_left, w_top, w_right, w_bottom], radius=36,
                        fill=(24, 24, 58, 255), outline=(124, 92, 255, 255), width=6)

    # card slot band
    d.rounded_rectangle([w_left + 26, w_top + 32, w_right - 26, w_top + 96],
                        radius=20, fill=(10, 10, 26, 255),
                        outline=(0, 229, 195, 230), width=4)

    # coin
    cx, cy, cr = S/2, 256, 64
    d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 217, 61, 255))
    d.ellipse([cx - cr + 10, cy - cr + 10, cx + cr - 10, cy + cr - 10],
              outline=(168, 132, 20, 255), width=6)
    d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], outline=(168, 132, 20, 200), width=5)

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
    "name": "کیف‌پول من — مدیریت هزینه‌ها",
    "short_name": "کیف‌پول من",
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

HEADER = "// کیف‌پول من — مدیریت هزینه‌ها و آرزوها (Persian RTL wallet app)\n" \
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
