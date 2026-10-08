Build the local web panel of `devtemizle` (developer junk finder/cleaner), Wave B of PLAN.md §6.
Read the context: PLAN.md (product plan, Turkish), /TASARIM.md rules (Turkish; BINDING: colors, layout, security), the reference
panel `liman` (Flask app + templates + CSS + JS — copy its token names, class patterns, CSP/Host checks, KULE_FRAME_ORIGIN function),
and the existing devtemizle modules (their API is fixed; do not modify them except where listed below).

All user-visible UI text in TURKISH (proper Turkish characters ç ğ ı ö ş ü). Code identifiers Turkish like the codebase, comments ASCII.

## Files

### devtemizle/is_akisi.py (new) — scan orchestration shared by CLI and web
```python
def tam_tarama(kokler: list[Path] | None, *, atlas_db: Path | None = None, derinlik: int = 3, ev: bool = False,
               onbellek: bool = True, ilerleme: Callable[[str, int, int], None] | None = None) -> dict
    # same steps as cli._tara: kesif.repo_listesi -> tara.tara (call per repo so ilerleme("repo", i, n) can be reported)
    # -> kesif.repo_meta_listesi -> onbellek.onbellek_tara()/docker_boyutlari() if onbellek -> rapor.olustur(...) -> rapor.kaydet(); returns the report dict.
```
### devtemizle/cli.py — `_tara` must call `is_akisi.tam_tarama` (keep identical output/flags/exit codes); `_web` must call `from .web import calistir` and `calistir(port=args.port, ac=args.ac, kokler=[Path(r) for r in args.root] or None, ev=args.ev)` with the existing ImportError handling (message "Flask kurulu degil ... pip install -e .[web]", exit 2). Add `--root` (append) and `--ev` to the `web` subparser. Keep every existing flag.

### devtemizle/web/__init__.py — `from .sunucu import calistir, uygulama_olustur`
### devtemizle/web/sunucu.py — Flask app factory `uygulama_olustur(kokler=None, ev=False, atlas_db=None) -> Flask` and `calistir(port=8796, ac=False, **kw)` (binds 127.0.0.1 only; `ac` opens browser with webbrowser after start via threading.Timer).
Security (copy liman/atlas patterns):
- before_request: Host must be 127.0.0.1[:port] or localhost[:port] else 403.
- after_request: CSP `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'` with frame-ancestors replaced by KULE_FRAME_ORIGIN when it matches ^http://(127\.0\.0\.1|localhost):\d{1,5}$ ; also X-Content-Type-Options nosniff, Referrer-Policy no-referrer.
- CSRF token `secrets.token_urlsafe(32)` generated per app, embedded in page as `<meta name="csrf" content=...>`; every POST requires header X-CSRF equal (hmac.compare_digest) AND Origin header equal to request.host_url origin or KULE_FRAME_ORIGIN; else 403 JSON {"hata": "..."}.
Routes:
- GET `/` — render page (template gets csrf and nothing else; data comes via JS from the API).
- GET `/api/rapor` — {"rapor": last report or null, "ozet": rapor.ozet_kartlari(r), "dagilim": rapor.dagilim_cubugu(r), "temizlenen_toplam": int} ; candidate entries are returned WITHOUT nothing removed (paths are fine, it's local).
- GET `/api/durum` — {"is": "bos"|"tarama"|"silme", "adim": str, "i": int, "n": int, "hata": str|null, "son_sonuc": dict|null}
- POST `/api/tara` JSON {"onbellek": bool} — start background thread running is_akisi.tam_tarama with the server-configured kokler/ev/atlas_db (client cannot pass paths). 409 if a job runs. Returns 202.
- POST `/api/sil` JSON {"idler": [..], "dikkat_dahil": bool} — 409 if a job runs; ids must be strings matching ^[0-9a-f]{8,40}$ (else 400); background thread calls sil.sil_idler(idler, uygula=True, dikkat_dahil=...) ; cache entries are cleaned by id too (sil_idler resolves both). After deletion re-run nothing; just store son_sonuc. Returns 202.
- A single module-level-free state object per app (lock-protected dict) — no globals shared across app instances (tests create many apps).

### devtemizle/web/sablonlar/temel.html, devtemizle/web/sablonlar/ana.html — Jinja; NO inline script/style; `<html lang="tr">`; favicon data URI like liman.
Page layout (PLAN.md §6): top bar (h1 "devtemizle", subtitle "Geliştirici çöpünü bul, güvenle temizle", right: button `#tara-dugme` "Tara" + checkbox "Genel önbellekleri de tara"), progress row `<progress id="ilerleme">` + `#ilerleme-metin` (hidden when idle),
4 summary cards `#kart-geri`, `#kart-dikkat`, `#kart-repo`, `#kart-temizlenen` (label, big number, small sub text),
distribution bar `#dagilim` (SVG built by JS, segments by group with class names `seg-js seg-python seg-rust seg-jvm seg-genel seg-onbellek`, legend with text labels + sizes),
filter bar (select group, number min age days, checkbox "Yalnız güvenli", search input, button "30 günden eski güvenlileri seç"),
repos section `#repolar` (one `<details>` per repo: summary row = repo name (basename, full path in title), last commit relative, "değişiklik var" badge if kirli, candidate count, total size; inside a table of candidates with checkbox (data-id), tür, boyut, yaş, risk badge text "güvenli"/"dikkat", small "geri getirme: <code>npm install</code>"); atlandi entries are shown greyed with reason, no checkbox,
caches section `#onbellekler` (table: checkbox, ad, yol shortened, boyut, risk, yöntem text),
docker box `#docker` (sizes + copyable `docker system prune` command in <code>, note "Panel bu komutu çalıştırmaz"),
sticky bottom bar `#secim-cubugu` (hidden when nothing selected): "N öğe seçildi · X GB" + button `#onizle` "Önizle"; clicking shows panel `#onay` listing selected items and a danger button `#sil-onay` with text "N öğeyi sil (X GB)" plus "Vazgeç"; never use confirm()/alert(),
status line `#durum` role="status", empty state text when no report: "Henüz tarama yok. Başlamak için Tara'ya bas.".
Dikkat items are NOT preselected by quick-select; selecting a dikkat item sets dikkat_dahil=true in the delete request.

### devtemizle/web/static/stil.css — reuse liman tokens exactly (light + dark via prefers-color-scheme AND :root[data-theme]), radius ≤ 8px, system font, tables scroll inside `.tablo-sarayici`, no horizontal page overflow at 390px, risk badges have text, focus-visible ring, sticky bar at bottom, progress styled simply. Group colors (Okabe-Ito): js #E69F00, python #0072B2 (dark #56B4E9), rust #D55E00, jvm #CC79A7, genel #009E73, onbellek #999999 (dark #BBBBBB).
### devtemizle/web/static/panel.js — vanilla JS, no framework, `'use strict'`, fetch with X-CSRF header from the meta tag; poll /api/durum every 700 ms while a job runs, then reload /api/rapor; human sizes (B, KB, MB, GB with one decimal, Turkish decimal comma e.g. "1,4 GB"); relative ages ("bugün", "3 gün önce", "2 ay önce"); build DOM with createElement/textContent ONLY (never innerHTML with data); keyboard accessible.

### devtemizle/pyproject.toml — packages ["devtemizle", "devtemizle.web"], package-data for web templates/static (`[tool.setuptools.package-data] "devtemizle.web" = ["sablonlar/*.html", "static/*"]`). Keep everything else.
### devtemizle/requirements.txt (new): `pytest` and `Flask>=3.0`.

### tests/test_web.py (Flask test client; DEVTEMIZLE_DIR -> tmp_path via monkeypatch; build a fake repo tree in tmp_path with package.json + node_modules/x.js and a .git dir; app = uygulama_olustur(kokler=[tmp_root])):
Host 403; CSP header present and default frame-ancestors 'none'; KULE_FRAME_ORIGIN valid -> used, invalid -> ignored; GET / contains csrf meta and no inline <script> body; POST without CSRF -> 403; wrong Origin -> 403;
/api/tara 202 then (join the worker: expose `app.config["DEVTEMIZLE_IS"]` thread or poll /api/durum until is=="bos" with a timeout) report has the node_modules candidate; second /api/tara while running -> 409 (use a monkeypatched slow tam_tarama via threading.Event);
/api/sil with invalid id -> 400; with the real candidate id -> node_modules removed from disk and son_sonuc lists it; a symlink candidate is never deleted; /api/sil with an id not in the report -> nothing deleted, atlanan contains it.
Tests must not touch the real home directory, must not run pip/npm/docker (monkeypatch onbellek.onbellek_tara / docker_boyutlari to return [] / {"var": False,...} or pass onbellek false).
Existing tests must keep passing.
