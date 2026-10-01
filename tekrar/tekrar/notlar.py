"""Vault knowledge/concepts altındaki notları okur ve Not dataclass'ına dönüştürür.

Yalnızca vault/knowledge/concepts/*.md (özyinelemeli DEĞİL) taranır.
Frontmatter visibility: private olanlar atlanır. 200KB+ dosyalar atlanır.
Okunamayan dosyalar sessizce atlanır.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Not:
    """Vault'taki bir notun işlenmiş hali."""

    yol: str  # vault'a göre göreli, '/' ayraçlı: "knowledge/concepts/x.md"
    baslik: str
    metin: str  # frontmatter'sız gövde
    sha256: str  # DOSYANIN TÜM BAYTLARININ sha256 hex'i


_VISIBILITY_PRIVATE_RE = re.compile(r"^\s*visibility\s*:\s*[\"']?private[\"']?\s*$", re.IGNORECASE | re.MULTILINE)
_TITLE_RE = re.compile(r"^\s*title\s*:\s*[\"']?([^\"'\n]+)[\"']?\s*$", re.IGNORECASE | re.MULTILINE)
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_FRONTMATTER_END_RE = re.compile(r"^---\s*$", re.MULTILINE)

MAX_SIZE = 200_000


def _parse_frontmatter_and_body(raw: bytes) -> tuple[dict[str, str], str]:
    """Ham baytlardan frontmatter (varsa) ve gövdeyi ayıklar.

    Basit satır ayrıştırma: --- ile başlayıp --- ile biten ilk blok.
    YAML kütüphanesi KULLANILMAZ.
    """
    text = raw.decode("utf-8", errors="replace")
    # CRLF -> LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if not text.startswith("---"):
        return {}, text

    # İkinci ---'yi bul
    lines = text.splitlines()
    end_idx = -1
    for i, line in enumerate(lines[1:], start=1):
        if _FRONTMATTER_END_RE.match(line):
            end_idx = i
            break

    if end_idx == -1:
        # Kapanan --- yoksa frontmatter sayılmaz
        return {}, text

    frontmatter_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:])

    # Basit key: value ayrıştırma
    fm: dict[str, str] = {}
    for line in frontmatter_text.splitlines():
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        fm[key.strip().lower()] = val.strip()

    return fm, body


def _extract_title(fm: dict[str, str], body: str, filename: str) -> str:
    """Başlığı çıkar: frontmatter title > ilk # başlığı > dosya adı (uzantısız)."""
    if "title" in fm:
        title = fm["title"].strip()
        # Tırnakları soy
        if (title.startswith('"') and title.endswith('"')) or \
           (title.startswith("'") and title.endswith("'")):
            title = title[1:-1]
        return title

    # İlk # başlığı
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()

    # Dosya adı (uzantısız)
    return Path(filename).stem


def notlari_oku(vault: Path) -> list[Not]:
    """Vault'taki knowledge/concepts/*.md dosyalarını okur ve Not listesini döndürür.

    Sıralama: dosya adına göre (lexicographic).
    """
    concepts_dir = vault / "knowledge" / "concepts"
    if not concepts_dir.is_dir():
        return []

    notlar: list[Not] = []

    for md_file in sorted(concepts_dir.glob("*.md")):
        if not md_file.is_file():
            continue

        try:
            raw = md_file.read_bytes()
        except OSError:
            continue

        # Boyut kontrolü (ham baytlar)
        if len(raw) > MAX_SIZE:
            continue

        sha256 = hashlib.sha256(raw).hexdigest()

        fm, body = _parse_frontmatter_and_body(raw)

        # visibility: private kontrolü
        vis = fm.get("visibility", "").strip().strip("\"'").strip().lower()
        if vis == "private":
            continue

        # Gövde boş/yalnız boşluk mu?
        if not body.strip():
            continue

        baslik = _extract_title(fm, body, md_file.name)

        # Göreli yol: vault'tan itibaren '/' ile
        try:
            rel_path = md_file.relative_to(vault).as_posix()
        except ValueError:
            # vault dışındaysa (olmamalı) dosya adını kullan
            rel_path = f"knowledge/concepts/{md_file.name}"

        notlar.append(Not(
            yol=rel_path,
            baslik=baslik,
            metin=body,
            sha256=sha256,
        ))

    return notlar