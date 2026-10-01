"""Git deposundan istatistiksel veri toplar.

Gerçek `git` komutlarını `subprocess` ile çalıştırır, hata durumunda
sessizce `None` döndürür (raise etmez).
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class RepoVerisi:
    """Repo istatistik verisi."""

    commit_sayisi: int
    ilk_commit: str | None      # ISO tarih (YYYY-MM-DD)
    son_commit: str | None
    haftalik: tuple[int, ...] | None   # son 12 hafta, EN ESKİ başta; None = veri yok (grafik çizilmez)
    diller: tuple[tuple[str, int], ...]   # (dil adı, sayı), en çok 5; sayı birimi `dil_birimi`
    readme_ozeti: str | None
    dil_birimi: str = "dosya"  # "dosya" (yerel klon) | "yuzde" (GitHub API)


# Uzantı → dil eşleşmesi
_UZANTI_DIL: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".kt": "Kotlin",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".cpp": "C++",
    ".cc": "C++",
    ".h": "C++",
    ".hpp": "C++",
    ".c": "C",
    ".html": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
    ".ipynb": "Jupyter Notebook",
    ".hcl": "HCL",
    ".tf": "HCL",
}


def _git_komut(klon: Path, *args: str, timeout: int = 20) -> str | None:
    """Git komutunu çalıştırır, stdout döndürür. Hata/timeout/kod!=0 ise None."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(klon), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None
    return completed.stdout


def _git_rc(klon: Path, *args: str, timeout: int = 20) -> int | None:
    """Git komutunun çıkış kodunu döndürür; çalıştırılamadıysa None."""
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        return subprocess.run(
            ["git", "-C", str(klon), *args],
            capture_output=True,
            timeout=timeout,
            env=env,
        ).returncode
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _tarih_parse(iso_str: str) -> date | None:
    """ISO tarih stringini (YYYY-MM-DD) date'e çevirir."""
    try:
        return date.fromisoformat(iso_str.strip())
    except ValueError:
        return None


def repo_verisi(klon: Path, bugun: date, *, readme: bool = False) -> RepoVerisi | None:
    """Depodan istatistiksel veri toplar. Hata durumunda None döner."""
    # Dizin ve .git kontrolü
    if not klon.is_dir() or not (klon / ".git").exists():
        return None

    # Gerçekten bir git deposu mu? (bozuk .git klasörü -> None)
    if _git_komut(klon, "rev-parse", "--git-dir") is None:
        return None

    # Boş repo: HEAD henüz yok. `rev-parse --verify -q` bu durumda 1 döner;
    # başka bir hata kodu (örn. 128: bozuk repo) boş repo DEĞİL, okunamayan repodur.
    head_rc = _git_rc(klon, "rev-parse", "--verify", "-q", "HEAD")
    if head_rc is None or head_rc not in (0, 1):
        return None
    if head_rc == 1:
        return RepoVerisi(
            commit_sayisi=0,
            ilk_commit=None,
            son_commit=None,
            haftalik=(0,) * 12,
            diller=(),
            readme_ozeti=None,
        )

    sayi_out = _git_komut(klon, "rev-list", "--count", "HEAD")
    if sayi_out is None:
        return None
    try:
        commit_sayisi = int(sayi_out.strip())
    except ValueError:
        return None

    # Tüm commit tarihleri (git log sırası yeniden eskiye; ilk/son min/max ile alınır)
    log_out = _git_komut(klon, "log", "--format=%cs", "--date=short")
    if log_out is None:
        return None

    tarihler: list[date] = []
    for satir in log_out.splitlines():
        dt = _tarih_parse(satir)
        if dt is not None:
            tarihler.append(dt)

    if not tarihler:
        return RepoVerisi(
            commit_sayisi=commit_sayisi,
            ilk_commit=None,
            son_commit=None,
            haftalik=(0,) * 12,
            diller=(),
            readme_ozeti=None,
        )

    # İlk ve son commit tarihleri (ISO format)
    ilk_commit = min(tarihler).isoformat()
    son_commit = max(tarihler).isoformat()

    # Haftalık pencereler (son 12 hafta, EN ESKİ başta)
    # bugun dahil hafta = son eleman
    haftalik_sayilar: list[int] = []
    for i in range(11, -1, -1):  # 11 (en eski) -> 0 (bu hafta)
        pencere_bas = bugun - timedelta(days=(i + 1) * 7 - 1)  # hafta başlangıcı
        pencere_son = bugun - timedelta(days=i * 7)            # hafta sonu (dahil)
        sayac = 0
        for dt in tarihler:
            if pencere_bas <= dt <= pencere_son:
                sayac += 1
        haftalik_sayilar.append(sayac)
    haftalik = tuple(haftalik_sayilar)

    # Diller: git ls-files ile dosyaları al, uzantıdan dil belirle
    ls_out = _git_komut(klon, "ls-files")
    if ls_out is None:
        diller = ()
    else:
        dil_sayilari: dict[str, int] = {}
        for satir in ls_out.splitlines():
            satir = satir.strip()
            if not satir:
                continue
            # uzantıyı al
            _, _, uzanti = satir.rpartition(".")
            if uzanti:
                uzanti = "." + uzanti.lower()
                if uzanti in _UZANTI_DIL:
                    dil = _UZANTI_DIL[uzanti]
                    dil_sayilari[dil] = dil_sayilari.get(dil, 0) + 1
        # Sırala: çoktan aza, eşitlikte ada göre
        diller_sirali = sorted(
            dil_sayilari.items(),
            key=lambda x: (-x[1], x[0])
        )[:5]
        diller = tuple(diller_sirali)

    # README özeti
    readme_ozeti = None
    if readme:
        readme_yol = klon / "README.md"
        if readme_yol.is_file() and not readme_yol.is_symlink():
            try:
                boyut = readme_yol.stat().st_size
                if boyut < 200 * 1024:  # 200 KB
                    icerik = readme_yol.read_text(encoding="utf-8", errors="replace")
                    readme_ozeti = _readme_ozetle(icerik)
            except OSError:
                pass

    return RepoVerisi(
        commit_sayisi=commit_sayisi,
        ilk_commit=ilk_commit,
        son_commit=son_commit,
        haftalik=haftalik,
        diller=diller,
        readme_ozeti=readme_ozeti,
    )


MIN_OZET = 40


def _readme_ozetle(icerik: str) -> str | None:
    """README'nin ilk anlamlı paragrafını döndürür (en çok 240 karakter, sonu `…`).

    Başlık, rozet/görsel, HTML satırı ve kod blokları paragraf SINIRI sayılır ve
    içeriğe girmez. Anlamlı paragraf yoksa None.
    """
    paragraf: list[str] = []
    kod_bloku_ici = False

    def bitir() -> str | None:
        metin = " ".join(paragraf)
        metin = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", metin)  # [metin](url) -> metin
        metin = re.sub(r"[*_`]+", "", metin)  # vurgu/kod işaretleri
        metin = re.sub(r"\s+", " ", metin).strip()
        # Çok kısa paragraflar (dil seçici, "Türkçe" gibi) özet sayılmaz
        return metin if len(metin) >= MIN_OZET else None

    for satir in icerik.splitlines():
        k = satir.strip().lstrip(">").strip()  # alıntı işareti

        if k.startswith("```") or k.startswith("~~~"):
            kod_bloku_ici = not kod_bloku_ici
            sonuc = bitir()
            if sonuc:
                return _kes(sonuc)
            paragraf.clear()
            continue
        if kod_bloku_ici:
            continue

        sinir = (
            not k
            or k.startswith("#")
            or (k.startswith("![") and "](" in k)
            or ("<" in k and ">" in k and re.search(r"<\w+[^>]*>", k) is not None)
        )
        if sinir:
            sonuc = bitir()
            if sonuc:
                return _kes(sonuc)
            paragraf.clear()
            continue
        paragraf.append(k)

    sonuc = bitir()
    return _kes(sonuc) if sonuc else None


def _kes(metin: str, en_cok: int = 240) -> str:
    """`en_cok` karakteri aşan metni kesip sonuna `…` koyar (toplam en_cok)."""
    if len(metin) <= en_cok:
        return metin
    return metin[: en_cok - 1].rstrip() + "…"
