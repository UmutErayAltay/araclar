"""Tarama akisi: CLI ve web paneli ayni adimlari bu modulden calistirir.

Adimlar (cli._tara ile birebir ayni sira):
  kesif.repo_listesi -> tara.tara (repo repo) -> kesif.repo_meta_listesi
  -> onbellek (istege bagli) -> rapor.olustur -> rapor.kaydet

Tara ciktisina panelin ihtiyac duydugu alanlar (id, grup, risk, yeniden)
burada eklenir; tara.py'nin kendisi degismez.

Modul onbellek ve docker fonksiyonlarini MODUL uzerinden cagirir
(`onbellek_modulu.onbellek_tara()`), boylece testler yalnizca
`devtemizle.onbellek` uzerinden monkeypatch yapabilir.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from . import onbellek as onbellek_modulu
from . import rapor
from . import tara as tara_modulu
from .kesif import repo_listesi, repo_meta_listesi
from .turler import risk_durumu, tur_ara

#: Ilerleme geri cagrisi: (adim, i, n). Adimlar: kesif, repo, meta, onbellek, rapor.
Ilerleme = Callable[[str, int, int], None]

_DOCKER_BOS = {"var": False, "imaj": 0, "konteyner": 0, "volume": 0, "build_cache": 0}


def _bildir(ilerleme: Ilerleme | None, adim: str, i: int, n: int) -> None:
    if ilerleme is not None:
        ilerleme(adim, i, n)


def _zenginlestir(aday: dict) -> dict:
    """Tara cikisina id / grup / risk / yeniden alanlarini ekler (yerinde)."""
    aday["id"] = tara_modulu._id_olustur(aday["yol"], aday["tur"])
    tur = tur_ara(aday["tur"])
    if tur is not None:
        aday["grup"] = tur.grup
        aday["risk"] = risk_durumu(aday["tur"], aday["repo"], tur)
        aday["yeniden"] = tur.yeniden
    else:  # tara.py yalnizca kural tablosundaki adlari verir; savunma amacli
        aday.setdefault("grup", "genel")
        aday.setdefault("risk", "dikkat")
        aday.setdefault("yeniden", "")
    return aday


def tam_tarama(
    kokler: list[Path] | None,
    *,
    atlas_db: Path | None = None,
    derinlik: int = 3,
    ev: bool = False,
    onbellek: bool = True,
    ilerleme: Ilerleme | None = None,
) -> dict:
    """Tarar, raporu yazar ve rapor sozlugunu dondurur.

    Hata: kesif.KesifHatasi (repo yok / atlas bulunamadi) oldugu gibi yukselir.
    """
    baslangic = time.time()
    repolar = repo_listesi(kokler or None, atlas_db, derinlik=derinlik, ev=ev)
    _bildir(ilerleme, "kesif", 0, len(repolar))

    adaylar: list[dict] = []
    for i, repo in enumerate(repolar, start=1):
        adaylar.extend(tara_modulu.tara([repo]))
        _bildir(ilerleme, "repo", i, len(repolar))
    for aday in adaylar:
        _zenginlestir(aday)

    _bildir(ilerleme, "meta", 0, len(repolar))
    meta_listesi = repo_meta_listesi(repolar)

    _bildir(ilerleme, "onbellek", 0, 0)
    onbellekler = onbellek_modulu.onbellek_tara() if onbellek else []
    docker = onbellek_modulu.docker_boyutlari() if onbellek else dict(_DOCKER_BOS)

    repolar_dict = [
        {
            "yol": str(m.yol),
            "son_commit": m.son_commit,
            "kirli": m.kirli,
            "aday_boyut": sum(a.get("boyut", 0) for a in adaylar if a.get("repo") == str(m.yol)),
        }
        for m in meta_listesi
    ]

    _bildir(ilerleme, "rapor", 0, 0)
    veri = rapor.olustur(
        adaylar=adaylar,
        onbellekler=onbellekler,
        docker=docker,
        repolar=repolar_dict,
        simdi=time.time(),
        sure_sn=time.time() - baslangic,
    )
    rapor.kaydet(veri)
    return veri
