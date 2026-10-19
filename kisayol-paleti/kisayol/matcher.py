"""Saf mantık katmanı: config + keşif → birleşik palet, palet → sıralı alt küme.

Bu modül bilerek terminal UI'ından ve subprocess'ten habersizdir; `cli.py`
sadece buradaki fonksiyonları çağırır. Böylece fuzzy sıralama ve tekrar
önleme, terminal açmadan test edilebilir.

Not: interaktif seçici canlı sıralamayı questionary'ye bırakır (bkz.
cli._pick) — `filter_items` aynı alaka kuralını terminal açmadan
kullanılabilir hâle getiren saf karşılığıdır; `kp --list | kp` gibi
senaryolarda ve testlerde o yol kullanılır.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from kisayol.discovery import find_repos

DEFAULT_COMMAND = os.environ.get("SHELL") or os.environ.get("COMSPEC") or "/bin/sh"


class Scored(NamedTuple):
    item: dict
    score: int


def _cwd_key(value: Any) -> str:
    """cwd karşılaştırma anahtarı: `~` genişletilir, göreli yol mutlaklaştırılır.

    `~` genişletmenin kısayola indirgenip kırpılması şart: testlerde
    `~/repo` yazıp gerçekten var olan bir dizini hedeflerken HOME'u
    değiştirmeden de eşleşebilmeli.
    """
    if not isinstance(value, str) or not value.strip():
        return ""
    path = Path(os.path.expanduser(value))
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        return str(path.resolve())
    except OSError:
        return str(path)


def build_items(config: dict) -> list[dict]:
    """config'teki `items` ile keşfedilen repoları birleştirir.

    Tekrar önleme yalnızca keşfe karşı uygulanır: config'te bir repo için
    elle "kule testlerini çalıştır" gibi özel bir komut yazıldıysa, keşfin
    ürettiği generic "repoya gir" item'ı eklenmez. Config'in kendi içinde tekrar
    engellenmez — aynı repoda birden fazla komut çalıştırmak bu aracın ana
    kullanımıdır (sunucu / testler / dashboard).
    """
    items = [_normalize_item(raw) for raw in _config_items(config)]
    claimed = {_cwd_key(item["cwd"]) for item in items}
    claimed.discard("")

    for item in find_repos(_discover_roots(config)):
        key = _cwd_key(item["cwd"])
        if key in claimed:
            continue
        if key:
            claimed.add(key)
        items.append(item)

    return items


def filter_items(items: Iterable[dict], query: str) -> list[dict]:
    """Query'ye uyan item'ları alaka sırasına göre döndürür.

    Boş query tüm item'ları sırasını bozmadan döndürür. Eşleşme, query
    harflerinin hedef metinde sırayla geçmesi (basit subsequence fuzzy) ve
    alaka puanıdır:

      1. tam alt dizi              → en iyi
      2. kelime/etiket başlangıcı  → iyi
      3. sıralı harf geçişi         → kabul edilebilir
      4. eşleşme yok               → elenir

    Puan yüksek olan önce; eşitlikte alfabetik sıra.
    """
    query = (query or "").strip().lower()
    if not query:
        return list(items)

    scored: list[Scored] = []
    for item in items:
        score = score_item(item, query)
        if score > 0:
            scored.append(Scored(item, score))

    # Aynı alaka puanı, aynı uzunlukta iki etiket için: alfabetik sıra.
    scored.sort(key=lambda s: (-s.score, str(s.item.get("label", ""))))
    return [s.item for s in scored]


def score_item(item: dict, query: str) -> int:
    """Tek bir item'ın alaka puanı; eşleşme yoksa 0."""
    query = (query or "").strip().lower()
    if not query:
        return 1

    best = 0
    for weight, text in _surfaces(item):
        if not text:
            continue
        score = _score_text(text, query) * weight
        if score > best:
            best = score
    return best


def _surfaces(item: dict) -> list[tuple[int, str]]:
    """(ağırlık, arama metni) çiftleri — alan sırası öncelik sırasıdır."""
    label = str(item.get("label", "")).lower()
    tags = " ".join(str(t) for t in item.get("tags") or []).lower()
    command = str(item.get("command", "")).lower()
    return [(100, label), (50, tags), (10, command)]


def display_fields(item: dict) -> list[str]:
    """`--list`/seçicide gösterilecek alanlar, yazıldıkları hâliyle.

    Arama yüzeyinden farklı olarak burada metinler lower-case'e çevrilmez:
    ekranda görünecek olan budur, `$EDITOR` küçültülürse kullanıcı ne
    çalıştıracağını göremez.
    """
    return [
        str(item.get("label", "")),
        " ".join(str(t) for t in item.get("tags") or []),
        str(item.get("command", "")),
    ]


def _score_text(text: str, query: str) -> int:
    if query in text:
        # Tam eşleşmede en-boy oranı: uzun bir etikette kısa bir eşleşme, kısa
        # etiketteki aynı eşleşmeden daha yüksek puan almamalı.
        return 1000 + 1000 * len(query) // len(text)
    if any(word.startswith(query) for word in _split_words(text)):
        return 400
    if _is_subsequence(query, text):
        return 150
    return 0


def _split_words(text: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in text).split() if w]


def _is_subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


def _config_items(config: Any) -> list[dict]:
    if not isinstance(config, dict):
        return []
    items = config.get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _discover_roots(config: Any) -> list[str]:
    if not isinstance(config, dict):
        return []
    roots = config.get("discover_roots")
    if not isinstance(roots, list):
        return []
    return [str(r) for r in roots if isinstance(r, (str, os.PathLike)) and str(r).strip()]


def format_item(item: dict) -> str:
    """`--list` satırı. `display_fields` ile aynı alan önceliğini kullanır ki
    scriptler etiket üzerinden grep'leyebilsin, seçici de aynı metni göstersin."""
    return " · ".join(text for text in display_fields(item) if text)


def _normalize_item(raw: dict) -> dict:
    """Eksik alanları varsayılanlarla doldurur; aşırı uzun girdileri budar.

    Etiket `~` veya boşsa cwd'nin son bileşenine düşer — `discover_roots`
    ile aynı fallback, kullanıcının yazdığı item'lar da aynı kurallı görünsün.
    """
    cwd = raw.get("cwd", "")
    cwd = str(cwd).strip() if isinstance(cwd, (str, os.PathLike)) else ""

    label = raw.get("label")
    label = str(label).strip() if isinstance(label, str) else ""
    if not label or label in ("~", "."):
        label = Path(cwd).name or cwd

    command = raw.get("command")
    command = str(command).strip() if isinstance(command, (str, int, float)) else ""
    if not command:
        command = DEFAULT_COMMAND

    tags = raw.get("tags")
    tags = [str(t) for t in tags if str(t).strip()] if isinstance(tags, list) else []

    return {"label": label[:200], "cwd": cwd, "command": command, "tags": tags}
