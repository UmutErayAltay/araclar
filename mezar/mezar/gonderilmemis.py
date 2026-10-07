"""Denetim 3 -- `gonderilmemis`: repoda uzakda olmayan commit var mi?

Sira: `@{upstream}..HEAD`; upstream yoksa `origin/main..HEAD`; o da yoksa
"remote izi yok" UYARISI dusulur.

Gonderilmemis commit varsa bu bir BULGUDUR ve karar `DIKKAT`'tir: repo
silinirse/kapatilirsa o isler kalici olarak kaybolur. Kirli calisma agaci da
ayni seye girer -- commit edilmemis degisiklik repo kapaninca gider.

Yalniz OKUMA komutlari: `rev-list`, `log`, `status`. Push/fetch HIC YERDE yok.
"""

from __future__ import annotations

from pathlib import Path

from . import kesif

#: Upstream yoksa denenecek varsayilan kollar (ilk isabet eden kullanilir).
VARSAYILAN_KOLLAR = ("origin/main", "origin/master")

#: Listede gosterilecek en fazla commit; toplam sayi ayrica yazilir.
GOSTERME_LIMITI = 10

#: `git status --porcelain` ciktisinda gosterilecek en fazla yol.
DURUM_LIMITI = 10

#: Uzakta olmayan commit bulgusunun onem duzeyi. Bu bulgunun digerlerinden
#: ayirt edilmasi bilincli: repo kapaninca is KALICI olarak kaybolur.
YUKSEK_ONEM = "YUKSEK"


def _referans(repo: Path) -> str | None:
    """Karsi lastirilecek referansi bulur; hicbiri yoksa `None`.

    Sirasi: `@{upstream}`, sonra `origin/main`, sonra `origin/master`.
    Upstream referansi sunucuda silinmis olabilir; bu durumda da sessizce
    devam ederiz, cunku `varsayilan` dallari zaten var.
    """
    ust = kesif.sorgu_yoksa(
        repo, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"]
    )
    if ust:
        ad = ust.strip().splitlines()[0].strip()
        if ad and ad != "@{upstream}":
            return ad
    for ad in VARSAYILAN_KOLLAR:
        if kesif.kisa_hash(repo, ad) is not None:
            return ad
    return None


def _konular(repo: Path, referans: str) -> list[str]:
    """Gonderilmemis commit'lerin konu satirlari (en yeni once, kisaltilmis)."""
    ham = kesif.sorgu(
        repo,
        ["log", "--format=%h %s", "--max-count", str(GOSTERME_LIMITI), f"{referans}..HEAD"],
    )
    return [satir.strip() for satir in ham.splitlines() if satir.strip()]


def _kirli(repo: Path) -> list[str]:
    ham = kesif.sorgu(repo, ["status", "--porcelain"])
    return [satir.rstrip() for satir in ham.splitlines() if satir.strip()]


def denetle(repo: Path) -> dict:
    """`gonderilmemis` denetimi.

    Donen sozluk: {"durum", "referans", "uzakta_yok", "konular", "kirli",
    "onem", "not"}. `uzakta_yok > 0` bir BULGUDUR ve onemi `YUKSEK`tur: repo
    kapanirsa o isler kalici olarak kaybolur. `durum == "remote-yok"` yalnizca
    UYARIDIR (reponun hicbir yere gonderilmemis olmasi mezar tasina engel
    degildir) ve `onem` de `None` kalir.
    """
    referans = _referans(repo)
    if referans is None:
        return {
            "durum": "remote-yok",
            "referans": None,
            "uzakta_yok": 0,
            "konular": [],
            "kirli": [],
            "onem": None,
            "not": "remote izi yok: ne upstream ne de origin/main bulundu; "
                   "gonderilmemis commit KONTROL EDILEMEDI",
        }

    sayi_ham = kesif.sorgu(repo, ["rev-list", "--count", f"{referans}..HEAD"]).strip()
    uzakta_yok = int(sayi_ham) if sayi_ham.isdigit() else 0
    return {
        "durum": "gonderilmemis-var" if uzakta_yok else "temiz",
        "referans": referans,
        "uzakta_yok": uzakta_yok,
        "konular": _konular(repo, referans) if uzakta_yok else [],
        "kirli": _kirli(repo),
        "onem": YUKSEK_ONEM if uzakta_yok else None,
        "not": None,
    }