"""Portfolyo stili (Cihaz Rafı). Saf CSS; JS ve dış kaynak yok, yalnız aynı kökenli /fonts/.

Kaynak: tasarım comp'u. Elle düzenlenir; sızıntı denetimi çıktıyı yine tarar.
"""

CSS = """/* Cihaz Rafı: portfolyo stili. Saf CSS, JS yok, dış kaynak yok (yalnız aynı kökenli /fonts/).
   Açık tema: fırçalı alüminyum paneller. Koyu tema: siyah eloksal. Tek vurgu kehribar = eylem. */

@font-face { font-family: "Barlow"; font-weight: 400; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-400-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: "Barlow"; font-weight: 400; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-400-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow"; font-weight: 600; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-600-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: "Barlow"; font-weight: 600; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-600-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-700-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: "Barlow"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-700-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow Condensed"; font-weight: 600; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-condensed-600-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: "Barlow Condensed"; font-weight: 600; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-condensed-600-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }
@font-face { font-family: "Barlow Condensed"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-condensed-700-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }
@font-face { font-family: "Barlow Condensed"; font-weight: 700; font-style: normal; font-display: swap;
  src: url("/fonts/barlow-condensed-700-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }

:root {
  color-scheme: light dark;
  --frame: #b3afa4;        /* raf çerçevesi (paneller arası) */
  --panel: #dedbd2;        /* fırçalı alüminyum */
  --panel-hi: #ebe8e0;
  --panel-lo: #cdc9bf;
  --ear: #c4c0b5;
  --edge: #8d897e;
  --ink: #1b1c1e;         /* serigraf mürekkebi */
  --ink-soft: #46463f;     /* ikincil metin, panel üstünde ≥7:1 */
  --rule: #a9a599;
  --well: #1e2022;         /* ölçer penceresi (iki temada da koyu) */
  --well-ink: #d8d4c8;
  --amber: #e8a317;        /* yalnız eylem */
  --amber-ink: #1b1c1e;
  --led-off: #6d6a60;
  --led-on: #2f9a6a;       /* yalnız "aktif / çevrimdışı çalışır" */
  --focus: #1b1c1e;
  --meter: var(--well-ink);
  --grain: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='320'%20height='320'%3E%3Cfilter%20id='b'%20x='0'%20y='0'%20width='100%'%20height='100%'%3E%3CfeTurbulence%20type='fractalNoise'%20baseFrequency='0.003%200.9'%20numOctaves='2'%20seed='7'%20stitchTiles='stitch'/%3E%3CfeColorMatrix%20values='0%200%200%200%200%200%200%200%200%200%200%200%200%200%200%200%200%200%200.17%200'/%3E%3C/filter%3E%3Crect%20width='320'%20height='320'%20filter='url(%23b)'/%3E%3C/svg%3E");
  --font-display: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", system-ui, sans-serif;
  --font-body: "Barlow", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --gutter: clamp(14px, 3vw, 28px);
  --ear-w: clamp(14px, 2.4vw, 30px);
  --max: 1180px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --frame: #08090a;
    --panel: #1f2022;
    --panel-hi: #2a2b2e;
    --panel-lo: #19191b;
    --ear: #151517;
    --edge: #3a3b3f;
    --ink: #ece9e0;
    --ink-soft: #b4b0a4;
    --rule: #3a3b3f;
    --well: #0e0f10;
    --led-off: #4a4a46;
    --led-on: #4fd08f;
    --focus: #f3b73a;
    --grain: url("data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20width='320'%20height='320'%3E%3Cfilter%20id='b'%20x='0'%20y='0'%20width='100%'%20height='100%'%3E%3CfeTurbulence%20type='fractalNoise'%20baseFrequency='0.003%200.9'%20numOctaves='2'%20seed='11'%20stitchTiles='stitch'/%3E%3CfeColorMatrix%20values='0%200%200%200%201%200%200%200%200%201%200%200%200%200%201%200%200%200%200.11%200'/%3E%3C/filter%3E%3Crect%20width='320'%20height='320'%20filter='url(%23b)'/%3E%3C/svg%3E");
  }
}

* { box-sizing: border-box; }
html { font-size: 17px; scroll-behavior: smooth; scroll-padding-top: 76px; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  background: var(--frame);
  color: var(--ink);
  font: 400 1rem/1.55 var(--font-body);
  font-variant-numeric: tabular-nums;
  min-height: 100vh;
  accent-color: var(--amber);
  caret-color: var(--amber);
  scrollbar-color: var(--edge) var(--frame);
}
::selection { background: var(--amber); color: var(--amber-ink); }
a { color: inherit; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; border-radius: 3px; }
.skip { position: absolute; left: 8px; top: -60px; background: var(--amber); color: var(--amber-ink); padding: 10px 16px; border-radius: 6px; z-index: 20; font-weight: 600; text-decoration: none; }
.skip:focus { top: 8px; }
.sr-only { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }

/* ---- raf ve ünite ---- */
.raf { width: 100%; max-width: var(--max); margin: 0 auto; padding: 8px var(--gutter) 40px; display: grid; gap: 8px; }
.unit {
  position: relative;
  display: grid;
  grid-template-columns: var(--ear-w) minmax(0, 1fr) var(--ear-w);
  background: var(--panel);
  border: 1px solid var(--edge);
  border-radius: 3px;
  box-shadow: 0 2px 3px rgba(0,0,0,.18), inset 0 1px 0 var(--panel-hi);
}
.unit > .yuz {
  background:
    var(--grain) 0 0 / 320px 320px,
    linear-gradient(180deg, var(--panel-hi), var(--panel) 7%, var(--panel) 93%, var(--panel-lo));
  padding: clamp(18px, 2.6vw, 34px);
  min-width: 0;
}
.kulak { background: var(--ear); position: relative; border-right: 1px solid var(--edge); }
.kulak:last-child { border-right: 0; border-left: 1px solid var(--edge); }
.kulak::before, .kulak::after {
  content: ""; position: absolute; left: 50%; width: 9px; height: 9px; margin-left: -4.5px; border-radius: 50%;
  background: radial-gradient(circle at 50% 40%, var(--well) 0 55%, transparent 58%);
  box-shadow: inset 0 1px 1px rgba(0,0,0,.5), 0 1px 0 var(--panel-hi);
  background-color: var(--panel-lo);
  top: 14px;
}
.kulak::after { top: auto; bottom: 14px; }
@media (max-width: 560px) { .kulak::before, .kulak::after { width: 6px; height: 6px; margin-left: -3px; } }

/* ---- yapışkan şerit ---- */
.serit { position: sticky; top: 0; z-index: 10; background: var(--frame); padding-top: 8px; }
.serit .yuz { padding: 8px clamp(12px, 2vw, 22px); display: flex; align-items: center; gap: 8px 22px; flex-wrap: wrap; }
.marka { font: 700 1.35rem/1 var(--font-display); letter-spacing: .06em; text-transform: uppercase; text-decoration: none; padding: 6px 2px; }
.menu { display: flex; flex-wrap: wrap; gap: 2px 4px; margin: 0 auto 0 0; padding: 0; list-style: none; }
.menu a { display: inline-block; padding: 8px 10px; font: 600 .78rem/1 var(--font-body); letter-spacing: .12em; text-transform: uppercase; text-decoration: none; border-radius: 3px; color: var(--ink-soft); }
.menu a:hover { color: var(--ink); background: rgba(0,0,0,.07); }
@media (max-width: 700px) {
  .serit { position: static; }
  .serit .yuz { padding: 8px 12px; gap: 4px 12px; }
  .serit .marka { margin-right: auto; }
  .menu { order: 3; width: 100%; flex-wrap: nowrap; overflow-x: auto; margin: 0; padding-bottom: 2px; }
  .menu a { white-space: nowrap; }
}
.dil { display: inline-flex; border: 1px solid var(--edge); border-radius: 4px; overflow: hidden; }
.dil a { padding: 7px 11px; font: 600 .78rem/1 var(--font-body); letter-spacing: .1em; text-decoration: none; color: var(--ink-soft); }
.dil a[aria-current="true"] { background: var(--ink); color: var(--panel); }
.dil a:not([aria-current]):hover { background: rgba(0,0,0,.07); color: var(--ink); }

/* ---- tuşlar (anahtar gibi) ---- */
.tus {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 11px 18px; border-radius: 5px; border: 1px solid var(--edge);
  font: 600 .84rem/1 var(--font-body); letter-spacing: .1em; text-transform: uppercase; text-decoration: none;
  background: linear-gradient(180deg, var(--panel-hi), var(--panel-lo));
  color: var(--ink);
  box-shadow: 0 2px 1px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.25);
  transition: transform .12s ease-out, box-shadow .12s ease-out;
}
.tus:hover { transform: translateY(-1px); box-shadow: 0 3px 2px rgba(0,0,0,.24), inset 0 1px 0 rgba(255,255,255,.3); }
.tus:active { transform: translateY(1px); box-shadow: 0 0 1px rgba(0,0,0,.3), inset 0 1px 2px rgba(0,0,0,.25); }
.tus--eylem { background: linear-gradient(180deg, #f2b93a, var(--amber)); border-color: #a9710b; color: var(--amber-ink); }
.tus--posta { text-transform: none; letter-spacing: .02em; font-size: .95rem; }
.tus--kucuk { padding: 8px 12px; font-size: .74rem; }
.tus svg { width: 16px; height: 16px; flex: none; }

/* ---- LED ---- */
.ledler { display: flex; flex-wrap: wrap; gap: 8px 22px; margin: 0; padding: 0; list-style: none; }
.led { display: inline-flex; align-items: center; gap: 9px; font: 600 .74rem/1 var(--font-body); letter-spacing: .13em; text-transform: uppercase; color: var(--ink-soft); }
.led::before {
  content: ""; width: 11px; height: 11px; border-radius: 50%; flex: none;
  background: var(--led-off); box-shadow: inset 0 1px 2px rgba(0,0,0,.5), 0 1px 0 var(--panel-hi);
}
.led--acik::before { background: var(--led-on); box-shadow: inset 0 -1px 2px rgba(0,0,0,.35), inset 0 1px 1px rgba(255,255,255,.4), 0 1px 7px color-mix(in srgb, var(--led-on) 70%, transparent); }
.led--eylem::before { background: var(--amber); box-shadow: inset 0 -1px 2px rgba(0,0,0,.3), inset 0 1px 1px rgba(255,255,255,.45), 0 1px 7px color-mix(in srgb, var(--amber) 75%, transparent); }

/* ---- hero ---- */
.hero .yuz { display: grid; gap: 28px 40px; grid-template-columns: minmax(0, 1fr); align-items: end; }
@media (min-width: 900px) { .hero .yuz { grid-template-columns: minmax(0, 1.5fr) minmax(280px, 1fr); padding-block: clamp(34px, 5vw, 64px); } }
.hero h1 { margin: 0; font: 700 clamp(3.4rem, 10.5vw, 6rem)/.9 var(--font-display); letter-spacing: .005em; text-transform: uppercase; text-wrap: balance; }
.hero .unvan { margin: 16px 0 0; font: 600 1.15rem/1.3 var(--font-body); letter-spacing: .03em; color: var(--ink-soft); }
.hero .pitch { margin: 18px 0 0; max-width: 56ch; font-size: 1.12rem; line-height: 1.55; text-wrap: pretty; }
.kontrol { display: grid; gap: 22px; justify-items: start; }
.tuslar { display: flex; flex-wrap: wrap; gap: 10px; }
.olcer-toplam { width: 100%; max-width: 420px; }
.olcer-toplam p { margin: 8px 0 0; font-size: .85rem; color: var(--ink-soft); }
.konum { margin: -8px 0 0; font: 600 .78rem/1 var(--font-body); letter-spacing: .13em; text-transform: uppercase; color: var(--ink-soft); }
.cv-not { margin: 0; font-size: .85rem; color: var(--ink-soft); }
.cv-not a { text-underline-offset: 3px; }

/* ---- bölüm rayı (başlık) ---- */
.ray { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin: 0 0 clamp(14px, 2vw, 22px); padding-bottom: 10px; border-bottom: 2px solid var(--ink); }
.ray h2 { margin: 0; font: 700 clamp(1.7rem, 3.4vw, 2.3rem)/1 var(--font-display); letter-spacing: .04em; text-transform: uppercase; }
.ray p { margin: 0; font-size: .85rem; color: var(--ink-soft); }
.raf > .ray p { color: var(--ink); }
.raf > .ray { margin: 26px 2px 2px; }
.raf > .iki { margin: 0; }
h3.alt { margin: 28px 0 10px; font: 600 .82rem/1 var(--font-body); letter-spacing: .16em; text-transform: uppercase; color: var(--ink-soft); }
h3.alt:first-of-type { margin-top: 0; }

/* ---- öne çıkan ünite ---- */
.one .yuz { display: grid; gap: 22px 36px; grid-template-columns: minmax(0, 1fr); }
@media (min-width: 860px) { .one .yuz { grid-template-columns: minmax(0, 1.35fr) minmax(250px, 1fr); align-items: stretch; } }
.pr-ad { margin: 0 0 8px; font: 700 clamp(1.8rem, 3.6vw, 2.5rem)/1 var(--font-display); letter-spacing: .02em; text-transform: uppercase; }
.pr-ad a { text-decoration: none; border-bottom: 2px solid transparent; }
.pr-ad a:hover { border-color: var(--amber); }
.ray--raf + .one .pr-ad { font-size: clamp(2.3rem, 5vw, 3.4rem); }
.pr-durum { margin: 0 0 14px; }
.pr-aciklama { margin: 0 0 14px; max-width: 62ch; text-wrap: pretty; }
.yigin { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 14px; padding: 0; list-style: none; }
.yigin li { padding: 5px 9px; border: 1px solid var(--edge); border-radius: 3px; font: 600 .72rem/1 var(--font-body); letter-spacing: .1em; text-transform: uppercase; color: var(--ink-soft); }
.baglar { display: flex; flex-wrap: wrap; gap: 8px; }

/* ---- ölçer (12 haftalık commit) ---- */
.olcer { display: grid; gap: 10px; align-content: start; }
.olcer-pencere { background: var(--well); border: 1px solid #000; border-radius: 4px; padding: 12px 12px 8px; box-shadow: inset 0 2px 6px rgba(0,0,0,.6), 0 1px 0 var(--panel-hi); }
.olcer-pencere .etkinlik-svg { display: block; width: 100%; height: 76px; color: var(--meter); }
.olcer-pencere .izgara { fill: none; stroke: var(--well-ink); stroke-opacity: .16; stroke-width: .4; vector-effect: non-scaling-stroke; }
.olcer-eksen { display: flex; justify-content: space-between; margin-top: 6px; font: 600 .75rem/1 var(--font-body); letter-spacing: .1em; text-transform: uppercase; color: var(--well-ink); opacity: .8; }
.olcer-rakam { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.olcer-rakam b { font: 700 2.2rem/1 var(--font-display); letter-spacing: .02em; }
.olcer-rakam span { font-size: .85rem; color: var(--ink-soft); }
.olcer-tarih { margin: 0; font-size: .85rem; color: var(--ink-soft); }

/* ---- 1U satır üniteleri ---- */
.satirlar { display: grid; gap: 0; border-top: 1px solid var(--rule); }
.satir { display: grid; gap: 8px 22px; padding: 16px 0; border-bottom: 1px solid var(--rule); grid-template-columns: minmax(0, 1fr); }
@media (min-width: 900px) { .satir { grid-template-columns: 210px minmax(0, 1fr) 170px 120px; align-items: center; } }
.satir h4 { margin: 0; font: 700 1.45rem/1.05 var(--font-display); letter-spacing: .03em; text-transform: uppercase; overflow-wrap: anywhere; }
.satir h4 a { text-decoration: none; border-bottom: 2px solid transparent; }
.satir h4 a:hover { border-color: var(--amber); }
.satir p { margin: 0; font-size: .95rem; text-wrap: pretty; }
.satir .yigin { margin: 8px 0 0; }
.satir .olcer-pencere { padding: 8px 8px 6px; }
.satir .olcer-pencere .etkinlik-svg { height: 38px; }
.satir .sayi { text-align: left; font-size: .85rem; color: var(--ink-soft); }
@media (min-width: 900px) { .satir .sayi { text-align: right; } }
.satir .sayi b { display: inline; margin-right: 6px; font: 700 1.5rem/1 var(--font-display); color: var(--ink); }
.satir .sayi span { display: block; margin-top: 2px; }

/* ---- deneyim / eğitim / yetenek ---- */
.iki { display: grid; gap: 8px; }
@media (min-width: 900px) { .iki { grid-template-columns: 1.4fr 1fr; } }
.kayit { margin: 0 0 18px; }
.kayit:last-child { margin-bottom: 0; }
.kayit h3 { margin: 0; font: 700 1.5rem/1.1 var(--font-display); letter-spacing: .03em; text-transform: uppercase; }
.kayit .kurum { margin: 2px 0 0; color: var(--ink-soft); }
.kayit time, .kayit .tarih { display: block; margin: 6px 0 8px; font: 600 .78rem/1 var(--font-body); letter-spacing: .12em; text-transform: uppercase; color: var(--ink-soft); }
.kayit .ek { display: block; margin: 0 0 8px; font-size: .9rem; color: var(--ink-soft); }
.kayit p { margin: 0; max-width: 62ch; text-wrap: pretty; }
.yetenek { display: grid; gap: 0; border-top: 1px solid var(--rule); }
.yetenek div { display: grid; gap: 4px 20px; padding: 12px 0; border-bottom: 1px solid var(--rule); }
@media (min-width: 700px) { .yetenek div { grid-template-columns: 190px minmax(0, 1fr); } }
.yetenek dt { font: 600 .8rem/1.4 var(--font-body); letter-spacing: .13em; text-transform: uppercase; color: var(--ink-soft); }
.yetenek dd { margin: 0; }

/* ---- yazılar ---- */
.yazi-listesi { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--rule); }
.yazi-listesi li { padding: 14px 0; border-bottom: 1px solid var(--rule); }
.yazi-baslik { font: 700 1.35rem/1.15 var(--font-display); letter-spacing: .03em; text-transform: uppercase; text-decoration: none; border-bottom: 2px solid transparent; }
.yazi-baslik:hover { border-color: var(--amber); }
.yazi-listesi time { margin-left: 12px; font-size: .85rem; color: var(--ink-soft); }
.yazi-listesi .aciklama { margin: 6px 0 0; color: var(--ink-soft); max-width: 66ch; }
.feed { margin-left: 10px; font: 600 .72rem/1 var(--font-body); letter-spacing: .12em; }

/* ---- iletişim ve alt bilgi ---- */
.iletisim .yuz { display: grid; gap: 22px 40px; }
@media (min-width: 900px) { .iletisim .yuz { grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr); align-items: end; } }
.iletisim h2 { margin: 0 0 10px; font: 700 clamp(2.6rem, 6.5vw, 4.4rem)/.95 var(--font-display); letter-spacing: .01em; text-transform: uppercase; text-wrap: balance; }
.iletisim p { margin: 0; max-width: 52ch; }
.alt-not { margin: 6px 0 0; padding: 10px var(--gutter) 0; text-align: center; font-size: .85rem; color: var(--ink); }
.alt-not a { text-underline-offset: 3px; }
.tus--kucuk.alt { margin-left: 8px; }

/* ---- yazı sayfası ---- */
.yazi .yuz { max-width: 100%; }
.yazi article { max-width: 70ch; margin: 0 auto; overflow-wrap: anywhere; }
.yazi h1 { margin: 0 0 6px; font: 700 clamp(2.1rem, 5vw, 3.2rem)/1 var(--font-display); letter-spacing: .01em; text-transform: uppercase; text-wrap: balance; }
.yazi h2 { margin: 30px 0 10px; font: 700 1.7rem/1.1 var(--font-display); letter-spacing: .03em; text-transform: uppercase; }
.yazi h3 { margin: 22px 0 8px; font: 700 1.25rem/1.2 var(--font-display); letter-spacing: .04em; text-transform: uppercase; }
.yazi .yazi-meta { margin: 0 0 22px; color: var(--ink-soft); font-size: .88rem; }
.yazi a { text-underline-offset: 3px; text-decoration-thickness: 1px; }
.yazi code { font: 500 .88em ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; background: rgba(0,0,0,.08); padding: 1px 5px; border-radius: 3px; }
.yazi pre { overflow-x: auto; background: var(--well); color: var(--well-ink); border-radius: 4px; padding: 14px; border: 1px solid #000; }
.yazi pre code { background: none; padding: 0; color: inherit; }
.yazi blockquote { margin: 16px 0; padding: 0 16px; border-left: 1px solid var(--ink); color: var(--ink-soft); }
.yazi-gezinme { display: flex; justify-content: space-between; gap: 16px; margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--rule); }
.yazi-gezinme a { max-width: 48%; text-underline-offset: 3px; }
.yazi-gezinme .sonraki { margin-left: auto; text-align: right; }
.geri { display: inline-block; text-underline-offset: 3px; }

/* ---- hareket: tek yazılı an. LED'ler sırayla yanar; ölçer çubukları görünürken yükselir ---- */
@keyframes led-yan { from { opacity: .25; } to { opacity: 1; } }
@keyframes cubuk-yuksel { from { transform: scaleY(0); } to { transform: scaleY(1); } }
.led--acik, .led--eylem { animation: led-yan .5s cubic-bezier(.16, 1, .3, 1) both; }
.ledler li:nth-child(2) { animation-delay: .14s; }
.ledler li:nth-child(3) { animation-delay: .28s; }
.etkinlik-svg rect { transform-box: fill-box; transform-origin: 50% 100%; }
@supports (animation-timeline: view()) {
  .etkinlik-svg rect { animation: cubuk-yuksel linear both; animation-timeline: view(); animation-range: entry 0% entry 70%; }
}
@media (prefers-reduced-motion: reduce) {
  html { scroll-behavior: auto; }
  * { animation: none !important; transition: none !important; }
}

/* ---- yazdırma ---- */
@media print {
  :root { --frame: #fff; --panel: #fff; --panel-hi: #fff; --panel-lo: #fff; --ear: #fff; --edge: #999; --ink: #000; --ink-soft: #222; --rule: #bbb; }
  body { background: #fff; }
  .serit, .kulak, .hero .tuslar, .baglar, .feed, .yazi-gezinme { display: none; }
  .iletisim .tus { border: 0; box-shadow: none; background: none; padding: 2px 0; text-transform: none; }
  .iletisim .tus[href^="https"]::after { content: " " attr(href); font-size: .8em; }
  .unit { grid-template-columns: 1fr; box-shadow: none; break-inside: avoid; }
  .unit > .yuz { background: #fff; }
  .yazi a[href^="https"]::after { content: " (" attr(href) ")"; font-size: .8em; }
}
"""
