"""Alt surec kurulumu ve paralel toplu calistirma.

Baglayici guvenlik kurallari (kod bunlari zorlar, istisna bir yol yoktur):

  * `--dangerously-skip-permissions` ve `bypassPermissions` ASLA kurulamaz.
  * commit / push / checkout ASLA calistirilmayan komutlardir; gorev metni
    alt surece oldugu gibi aktarilir, filtrelenmez degil -- kurulumda eklenmez.
  * Varsayilan arac listesi SALT OKUNURdur: `Read,Glob,Grep`.

Zaman asimi olursa surec GRUBU (SIGTERM -> SIGKILL) oldurulur; boylece uyuyan
bir alt surec ana sureci asili birakmaz.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

#: Varsayilan model; COR_MODEL ortam degiskeni varsa o gecerlidir.
VARSAYILAN_MODEL = os.environ.get("COR_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

#: Varsayilan cor komutu.
VARSAYILAN_COR = "cor"

#: SALT OKUNUR varsayilan: hicbir sey yazamaz, hicbir komut calistiramaz.
SALT_OKUNUR_ARACLAR = "Read,Glob,Grep"

#: `--duzenle` ile acilan genis arac listesi.
DUZENLE_ARACLAR = "Read,Write,Edit,Bash,Glob,Grep"

IZIN_KIPI = "acceptEdits"
#: YASAK dizeler: kurulan argv'de bulunmamalari sozlesmedir (test bunu dogrular).
YASAKLI_DIZELER = ("--dangerously-skip-permissions", "bypassPermissions")

SIGKILL_BEKLE = 5.0
ZAMAN_ASIMI_KODU = 124
COR_YOK_KODU = 127

#: Paralellik ust siniri: ucretsiz modellerin kotasini korumak icin.
AZAMI_PARALEL = 8


class CalistirmaHatasi(RuntimeError):
    """Gecersiz deger / calistirilamayan komut (CLI cikis kodu 2)."""


@dataclass
class RepoSonucu:
    """Tek bir repo'nun sonucu."""

    repo: str
    durum: str  # "ok" | "hata" | "zaman-asimi"
    sure_sn: float
    rapor: str
    rapor_boyut: int
    cikis_kodu: int | None
    hata: str | None = None


def arac_listesi(duzenle: bool) -> str:
    """Kullanilacak izinli arac listesi (virgulle, Claude Code sozlesmesi)."""
    return DUZENLE_ARACLAR if duzenle else SALT_OKUNUR_ARACLAR


def paralel_denetle(paralel: int) -> int:
    """Paralellik sinirini denetler; gecersizse `CalistirmaHatasi` (cikis 2).

    `--kuru` da bu denetimi gecmek ZORUNDADIR: kuru calistirma plani gosterir,
    ama gecersiz bir degeri sessizce kabul etmez.
    """
    if not isinstance(paralel, int) or not 1 <= paralel <= AZAMI_PARALEL:
        raise CalistirmaHatasi(
            f"--paralel 1..{AZAMI_PARALEL} arasinda olmali (ucretsiz model kotasini "
            f"korumak icin); verilen: {paralel}"
        )
    return paralel


def argv_olustur(cor: str, model: str, araclar: str) -> list[str]:
    """Tek bir repo icin calistirilacak komut satiri.

    `shell=False` icin LISTE doner; kabuk yorumlamasi yoktur. Dizi olustuktan
    sonra yasakli dizeler taranir: bir sef bir sef kelime bulunursa hata verir
    (sessizce gecmez -- sozlesmenin ihlali hata sayilir).
    """
    argv = [
        cor,
        "claude",
        "-p",
        "--model",
        model,
        "--permission-mode",
        IZIN_KIPI,
        "--allowedTools",
        araclar,
    ]
    ihlal = [d for d in YASAKLI_DIZELER if any(d in parca for parca in argv)]
    if ihlal:
        raise CalistirmaHatasi(
            f"guvenlik ihlali: kurulan argv'de yasakli dizeler var: {', '.join(ihlal)}"
        )
    return argv


def _surec_grubunu_oldur(surec: subprocess.Popen) -> None:
    """Surec GRUBU: once SIGTERM, 5 sn sonra SIGKILL (cocuk surec birakmaz)."""
    if os.name == "nt":  # pragma: no cover -- bu container POSIX
        subprocess.run(  # noqa: S603
            ["taskkill", "/T", "/F", "/PID", str(surec.pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(surec.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        surec.wait(timeout=SIGKILL_BEKLE)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(os.getpgid(surec.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return


def _tek_repo(
    repo: Path, argv: list[str], gorev: str, rapor_yolu: Path, zaman_asimi: float
) -> RepoSonucu:
    """Bir repo'da alt sureci calistirir, ciktisini rapor dosyasina yazar.

    Girdi metni `gorev` olarak STDIN'e gider; STDOUT+STDERR rapora harmanlanir.
    Hata bu isi BIRDIRMEZ: sonuc `durum` alaninda bildirilir, digerleri devam eder.
    """
    baslangic = time.monotonic()
    zaman_asimi_mi = False
    try:
        with rapor_yolu.open("wb") as cikti:
            try:
                surec = subprocess.Popen(  # noqa: S603 -- argv listesidir, shell yok
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=cikti,
                    stderr=subprocess.STDOUT,
                    cwd=str(repo),
                    start_new_session=True,
                )
            except FileNotFoundError:
                return RepoSonucu(
                    repo=str(repo), durum="hata", sure_sn=round(time.monotonic() - baslangic, 2),
                    rapor=str(rapor_yolu), rapor_boyut=0, cikis_kodu=COR_YOK_KODU,
                    hata=f"cor bulunamadi: {argv[0]}",
                )
            except OSError as exc:
                return RepoSonucu(
                    repo=str(repo), durum="hata", sure_sn=round(time.monotonic() - baslangic, 2),
                    rapor=str(rapor_yolu), rapor_boyut=0, cikis_kodu=COR_YOK_KODU,
                    hata=f"calistirilamadi: {exc}",
                )
            try:
                surec.communicate(input=gorev.encode("utf-8"), timeout=zaman_asimi)
            except subprocess.TimeoutExpired:
                zaman_asimi_mi = True
                _surec_grubunu_oldur(surec)
                try:
                    surec.communicate(timeout=SIGKILL_BEKLE)
                except subprocess.TimeoutExpired:  # pragma: no cover -- SIGKILL sonrasi
                    pass
    except OSError as exc:
        return RepoSonucu(
            repo=str(repo), durum="hata", sure_sn=round(time.monotonic() - baslangic, 2),
            rapor=str(rapor_yolu), rapor_boyut=0, cikis_kodu=None, hata=str(exc),
        )

    sure_sn = round(time.monotonic() - baslangic, 2)
    boyut = rapor_yolu.stat().st_size if rapor_yolu.is_file() else 0
    # Zaman asiminda surec SIGTERM/SIGKILL ile olduruldugu icin returncode -15
    # gelir; durum KODDAN degil BAYRAKTAN okunur.
    kod = ZAMAN_ASIMI_KODU if zaman_asimi_mi else surec.returncode
    if zaman_asimi_mi:
        durum, hata = "zaman-asimi", f"{zaman_asimi:.0f} saniyede zaman asimi; surec olduruldu"
    elif kod == 0:
        durum, hata = "ok", None
    else:
        durum, hata = "hata", f"alt surec cikis kodu {kod}"
    return RepoSonucu(
        repo=str(repo), durum=durum, sure_sn=sure_sn, rapor=str(rapor_yolu),
        rapor_boyut=boyut, cikis_kodu=kod, hata=hata,
    )


def calistir(
    repolar: list[Path],
    gorev: str,
    rapor_hedefleri: dict[str, Path],
    *,
    cor: str = VARSAYILAN_COR,
    model: str = VARSAYILAN_MODEL,
    araclar: str = SALT_OKUNUR_ARACLAR,
    paralel: int = 4,
    zaman_asimi: float = 900.0,
) -> list[RepoSonucu]:
    """Repolari paralel calistirir, `rapor_hedefleri[repo] = rapor_yolu` haritasiyle.

    `rapor_hedefleri` anahtarlari `str(repo)` olmalidir (CLI hazirlar). Sonuclar
    GIRIS SIRASI korunarak doner -- paralellik ciktinin sirasini bozmaz.
    """
    paralel_denetle(paralel)
    argv = argv_olustur(cor, model, araclar)
    sonuclar: list[RepoSonucu | None] = [None] * len(repolar)
    with ThreadPoolExecutor(max_workers=paralel) as havuz:
        gelecekler = {
            havuz.submit(
                _tek_repo, repo, argv, gorev, rapor_hedefleri[str(repo)], zaman_asimi
            ): indeks
            for indeks, repo in enumerate(repolar)
        }
        for gelecek, indeks in gelecekler.items():
            try:
                sonuclar[indeks] = gelecek.result()
            except Exception as exc:  # pragma: no cover -- _tek_repo nadiren firlatir
                repo = repolar[indeks]
                sonuclar[indeks] = RepoSonucu(
                    repo=str(repo), durum="hata", sure_sn=0.0,
                    rapor=str(rapor_hedefleri[str(repo)]), rapor_boyut=0,
                    cikis_kodu=None, hata=f"beklenmeyen hata: {exc}",
                )
    return [s for s in sonuclar if s is not None]