"""Bitis raporu: `<cikti>/OZET.md` tablosu + `--json` icin ayni bilgi.

Guvenlik: rapor yalnizca REPO YOLU, DURUM, SURE, RAPOR DOSYASI ve BOYUT
icerir -- alt surecin ham metni buraya tasinmaz, sadece dosyada kalir.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from .calistir import RepoSonucu

SURUM = 1
OZET_ADI = "OZET.md"
VARSAYILAN_KOK_ADI = "filo-ciktilari"


def zaman_damgasi(simdi: float | None = None) -> str:
    """Cikti klasoru adi: `YYYY-AA-GGTHH-MM-SSZ` (UTC, dosya adina uygun)."""
    return time.strftime(
        "%Y-%m-%dT%H-%M-%SZ", time.gmtime(time.time() if simdi is None else simdi)
    )


def varsayilan_cikti(simdi: float | None = None) -> Path:
    """Varsayilan cikti: `./filo-ciktilari/<zaman-damgasi>/`."""
    return Path.cwd() / VARSAYILAN_KOK_ADI / zaman_damgasi(simdi)


def govde(sonuclar: list[RepoSonucu], *, cikti: Path, kuru: bool = False) -> dict:
    """Rapor govdesi (yazmaz; `kaydet()` yazar)."""
    return {
        "surum": SURUM,
        "tarih": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cikti": str(cikti),
        "kuru": kuru,
        "ozet": {
            "toplam": len(sonuclar),
            "ok": sum(1 for s in sonuclar if s.durum == "ok"),
            "hata": sum(1 for s in sonuclar if s.durum == "hata"),
            "zaman-asimi": sum(1 for s in sonuclar if s.durum == "zaman-asimi"),
        },
        "sonuclar": [
            {
                "repo": s.repo,
                "ad": Path(s.repo).name,
                "durum": s.durum,
                "sure_sn": s.sure_sn,
                "rapor": s.rapor,
                "rapor_boyut": s.rapor_boyut,
                "cikis_kodu": s.cikis_kodu,
                "hata": s.hata,
            }
            for s in sonuclar
        ],
    }


def tablo(sonuclar: list[RepoSonucu]) -> str:
    """Insan-okur metin tablosu: repo, durum, sure, rapor dosyasi, boyut."""
    basliklar = ["repo", "durum", "sure(sn)", "rapor", "boyut"]
    satirlar = [
        [
            Path(s.repo).name,
            s.durum,
            f"{s.sure_sn:.2f}",
            s.rapor,
            f"{s.rapor_boyut} B",
        ]
        for s in sonuclar
    ]
    genislik = [
        max([len(basliklar[i])] + [len(s[i]) for s in satirlar]) for i in range(len(basliklar))
    ]

    def birlestir(hucre: list[str]) -> str:
        return "  ".join(hucre[i].ljust(genislik[i]) for i in range(len(hucre))).rstrip()

    return "\n".join([birlestir(basliklar), *(birlestir(s) for s in satirlar)])


def markdown(veri: dict) -> str:
    """OZET.md iceriği: baslik, ozet sayaclari, tablo, hata satirlari."""
    ozet = veri["ozet"]
    satirlar = [
        "# filo ozeti",
        "",
        f"- tarih: {veri['tarih']}",
        f"- cikti: {veri['cikti']}",
        f"- toplam: {ozet['toplam']}  ok: {ozet['ok']}  "
        f"hata: {ozet['hata']}  zaman-asimi: {ozet['zaman-asimi']}",
    ]
    if veri.get("kuru"):
        satirlar.append("- KURU CALISTIRMA: hicbir alt surec baslatilmadi.")
    satirlar += ["", tablo([_sonuca(s) for s in veri["sonuclar"]]), ""]
    hatali = [s for s in veri["sonuclar"] if s.get("hata")]
    if hatali:
        satirlar.append("## Hatalar")
        satirlar.append("")
        satirlar.extend(f"- `{s['ad']}`: {s['hata']}" for s in hatali)
        satirlar.append("")
    return "\n".join(satirlar)


def _sonuca(kayit: dict) -> RepoSonucu:
    """JSON govdesindeki kayittan RepoSonucu geri kurar (tablo icin)."""
    return RepoSonucu(
        repo=kayit["repo"], durum=kayit["durum"], sure_sn=kayit["sure_sn"],
        rapor=kayit["rapor"], rapor_boyut=kayit["rapor_boyut"],
        cikis_kodu=kayit.get("cikis_kodu"), hata=kayit.get("hata"),
    )


def kaydet(veri: dict, cikti: Path) -> Path:
    """OZET.md'yi yazar. MEVCUT DOSYA UZERINE YAZILMAZ."""
    cikti.mkdir(parents=True, exist_ok=True)
    hedef = cikti / OZET_ADI
    if hedef.exists():
        raise FileExistsError(f"cikti dosyasi zaten var, uzerine yazilmadi: {hedef}")
    hedef.write_text(markdown(veri), encoding="utf-8")
    return hedef