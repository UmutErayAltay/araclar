# atlas — Repo Health Atlas

Scans every git repository under a root directory, writes each one's health to
SQLite, shows it as CLI tables, and renders it in a **read-only web panel**.

Waves **A** (core scanner + DB), **B** (secret & history scan), **C** (TODO debt
+ web panel) and **D** (README staleness + per-repo "what to do next") are
implemented. The Turkish README is the complete reference; this file is a short,
synchronised overview.

## Install

Requires Python 3.11+ and `git`. The only runtime dependency is **Flask** (web
panel); all scanning code is standard library only.

```bash
python3 -m atlas tara --root /home/user   # no pip install needed
pip install -e .                          # optional
```

## Commands

| Command | What it does |
|---|---|
| `atlas tara` | Scan roots; write `repos` (dirty / unpushed / branch / last commit) |
| `atlas liste` | List repos as a table (`--sadece-yarim` filters) |
| `atlas sizinti` | Secret scan: working tree (`ls-files`) + history (`git log -p`) |
| `atlas bulgular` | List stored findings (`--siddet`, `--tur`, `--repo`) |
| `atlas borc` | TODO/FIXME debt in git-tracked text files |
| `atlas readme` | **README staleness score, sorted descending** |
| `atlas ozet` | **Per-repo "what to do next" — does not use the network** |
| `atlas guncelle` | All of the above in one command (still no network) |
| `atlas web` | Read-only panel on `127.0.0.1` |

**DB path:** `--db`, else `$ATLAS_DB`, else `~/.atlas/atlas.db`.
**Roots:** `--root`, else `roots` in `~/.atlas/config.toml`, else `~`.

## `unpushed`: the `?` case

`unpushed` only reads **local** refs. atlas never runs `git fetch`. When a remote
is configured but no `refs/remotes/*` ref exists locally, the honest answer is
"unknown", so atlas shows `?` rather than inventing a number — the real value may
be 0. Run `git fetch` in the repo to resolve it.

## README staleness (Wave D) — `atlas readme`

Answers "did the code move but the README didn't?" **with a number**.

- **README**: first match of `README.md` → `README.rst` → `README.txt` → `README`.
  None → level `yok`.
- **readme_commit**: last commit that touched the README. Never committed →
  `NULL`, level `yok`.
- **Behavior commit**: between `readme_commit..HEAD`, non-merge, whose message
  does **not** start with `docs`/`chore`/`style`/`test`/`ci` (an optional
  `(scope)` is allowed) **and** touches at least one **code file**.
- **Code file**: extension in `.py .js .jsx .ts .tsx .go .rs .java .kt .c .cc
  .cpp .h .hpp .cs .rb .php .sh .sql .html .css .vue .svelte`, **not** under
  `tests/ test/ docs/ examples/ .github/`, and **not** named README/CHANGELOG/LICENSE.
- **screenshot_age_days**: for **local** image references in the README
  (`![..](path)` and `<img src="path">`; `http(s)` and `data:` excluded), the day
  gap between the newest existing tracked image's last commit and the last
  behavior commit. `NULL` if the README has no local image. Paths escaping the
  repo with `..` are **rejected**. Images referenced but absent are counted
  separately as `eksik_gorsel`.

> A commit-message **keyword is not required**: real repos here use Turkish
> messages like `Dalga C: …`, so requiring `fix|feat` would miss all of them.
> Only prefixes that create *false positives* are excluded.

```
score = behavior commits + (screenshot age // 10)   ← bonus only if behavior ≥ 1
```

| Level | Condition |
|---|---|
| `taze` (fresh) | score < 3 |
| `eskiyor` (aging) | 3 ≤ score < 8 |
| `bayat` (stale) | score ≥ 8 |
| `yok` (none) | no README, or never committed |

Thresholds 3 and 8 are fixed in the module docstring and pinned by tests.
Scanning looks at most the last **2000 commits**; beyond that the level is
`sinir` and the score is shown as a **lower bound** (8) — a marker, not a guess.
Empty repos, no HEAD and bare clones raise **no error**: the level is `NULL`
and `neden` explains why.

## "What to do next" (Wave D) — `atlas ozet`

**Does not use the network by default.** The default summary is a
**deterministic rule-based** list of at most 3 lines with a fixed, tested
priority order. Nothing to do → `Acil iş yok.`

Two invented claims are explicitly prevented:

- If `unpushed` is `NULL` (unknown), it **never** claims there are unpushed
  commits — it says the remote-tracking information is missing.
- If **no remote** is configured, `unpushed` is the **total commit count** by
  contract, which does *not* mean "pending push". Neither the local summary nor
  the data sent to cor labels that number as unpushed.

### Privacy model

cor is contacted **only** with an explicit `--cor` flag, and the set of data
sent is **fixed and narrow**:

| Sent | Never sent |
|---|---|
| Repo name | File **contents** |
| Branch name | File **paths** |
| Dirty count | Snippets (not even masked) |
| Unpushed count or `"unknown"` | **TODO text** |
| Days since last commit | Finding file/line |
| Stale level + score | Commit **hashes** |
| Finding **counts** (type × severity) | |
| TODO **count** | |
| Up to 10 commit **subjects** (masked) | |

Commit subjects first pass through atlas's existing masker (keys, paths and
e-mails masked); a subject that trips the secret filter is **dropped entirely**.

**Prompt injection:** commit subjects are *untrusted data*. The prompt is a
fixed Turkish instruction plus a delimited `<<<VERI` … `VERI>>>` data block; the
instruction states that no sentence in the data block is an instruction, and
delimiter sequences inside the data are neutralised so they cannot escape. Model
output is treated as plain text: at most 3 lines / 600 characters, terminal
control characters stripped, and the result passes through the masker **again**.

`--kuru` prints which field types and how many characters would go out, **without
showing any content**. If `--cor` fails (cor down, unreachable, empty reply), a
clear warning goes to stderr, the **local** summary is stored, and the **exit
code is 3** — so it never looks like success.

The web panel **never** contacts cor. `atlas guncelle` generates local
summaries only; it has no `--cor` flag, so it cannot reach the network.

## Web panel

| Page | Content |
|---|---|
| `/` | Summary cards (repos, dirty, push pending/unknown, findings, TODOs, **stale READMEs**) |
| `/yarim-is` | Dirty · unpushed (**known**) · push state **unknown** |
| `/sizinti` | Findings with `?siddet=` `?tur=` `?repo=` filters |
| `/borc` | TODO density per repo + all records |
| `/bayat-readme` | README staleness sorted by score; level badge carries **colour and text** |
| `/repo/<id>` | Repo card + README row + **"what to do next"** + findings + TODOs |

The panel never touches repos and never triggers a scan — it only reads the DB.
The database is opened `mode=ro`; every route is GET-only; the host header is
validated against `127.0.0.1`/`localhost` (DNS-rebinding protection); a strict
CSP is sent with every response; and every snippet/TODO/summary is masked again
on the way out.

## Known limits

- **Not verified on Windows.** The new code uses `pathlib` and normalises `\`
  separators, but no real Windows machine has been scanned.
- `atlas ozet` summarises the repos recorded in the DB, so run `atlas tara`
  (or `atlas guncelle`) first.
- The 2000-commit window; beyond it the level becomes `sinir`.
- `screenshot_age_days` only counts **tracked** images.
- `--cor` output is a suggestion; atlas performs **no** automatic fix or push.
- Flask's development server, local single-user use.
- The density chart shows a raw count, not TODOs per 1000 lines.

## Screenshots

All images are generated from **fictional** data
(`python3 scripts/ekran_goruntusu.py`); no real repo name, path, key or e-mail
appears in any of them. See the Turkish README for the gallery.
