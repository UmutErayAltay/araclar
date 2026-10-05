"""Surec baslatma / durdurma.

Baglayici guvenlik kurallari (kod bunlari zorlar):
 - YALNIZCA kendi pid dosyamizdaki sureci durdururuz; keyfi port/surec ASLA.
 - Linux'ta oldurmeden once `/proc/<pid>/cmdline` tanimdaki `baslat[0]` ile
   eslesmeli; pid yeniden kullanilmissa dokunulmaz.
 - Port dolu ama bizim pid dosyamiz yoksa (`port-dolu-bilinmeyen`) dokunulmaz.
 - `--kuru` hicbir sey baslatmaz/oldurmez.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

from . import durum as durum_modul
from .durum import PORT_DOLU_BILINMEYEN, log_yolu, pid_oku, pid_yolu, port_dinleniyor, saglik_yok
from .tanim import Servis

#: SIGTERM sonrasi beklenecek saniye. SERVIS_DURDUR_BEKLE_SN ile kisaltilabilir
#: (testler 1 sn verir; kullanicinin gercek servisi beklemek zorundadir, bu
#: yuzden varsayilan 10 sn kalir -- cok kisa bir bekleme, yavas kapanan bir
#: servisi gereksiz yere "--zorla" ile oldurmeye yol acar).
VARSAYILAN_DURDUR_BEKLE_SN = 10.0

#: SIGKILL sonrasi beklenecek saniye (sinyal aninda; sadece tuval bosalmasini bekleriz).
ZORLA_BEKLE_SN = 3.0

#: Kendi oldurdugumuz surecin dinleme yuvasinin bosalmasini bekleyecegi en fazla sure.
PORT_BOSALMA_SN = 3.0

BEKLE_ADIM_SN = 0.2
LOG_SON_SATIR = 5

CALISTI = "calisti"
ATLANDI = "atlandi"
ZATEN_CALISIYOR = "zaten-calisiyor"
BASARISIZ = "basarisiz"
DURDU_SONUC = "durdu"
DURMADI = "durmadi"
ZATEN_DURDU = "zaten-durdu"
KURU = "kuru"

#: pid yeniden kullanimi korumasi: /proc/<pid>/cmdline tanimdaki argv[0] ile uymali.
UYUSMUYOR = "pid-cmdline-uyusmuyor"


def _argv0_duruyor(argv: list[str]) -> str:
    return os.path.basename(argv[0])


def durdurme_bekle_sn() -> float:
    """SIGTERM sonrasi beklenecek saniye (SERVIS_DURDUR_BEKLE_SN ile ayarlanir)."""
    ham = os.environ.get("SERVIS_DURDUR_BEKLE_SN")
    if not ham:
        return VARSAYILAN_DURDUR_BEKLE_SN
    try:
        deger = float(ham)
    except ValueError:
        return VARSAYILAN_DURDUR_BEKLE_SN
    return deger if deger >= 0 else VARSAYILAN_DURDUR_BEKLE_SN


def cmdline_oku(pid: int) -> list[str] | None:
    """/proc/<pid>/cmdline -> argv listesi. Okunamazsa None (Linux disi ya da yetki yok)."""
    # /proc yoksa (macOS/Windows) dogrulama yapilamaz; Linux'ta bu yol kullanilmaz.
    try:
        ham = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return None
    parcalar = [p.decode("utf-8", "replace") for p in ham.split(b"\0") if p]
    return parcalar or None


def cmdline_uyusuyor(pid: int, argv0: str) -> bool:
    """pid gercekten bizim komutumuz mu? Linux'ta /proc ile dogrulanir.

    /proc erisilemiyorsa (Linux disi) dogrulama yapilamaz; bu durumda True
    donulur ama Linux'ta ASLA korumasiz yol yok (Linux'ta /proc vardir).
    """
    parcalar = cmdline_oku(pid)
    if parcalar is None:
        return True  # dogrulanamadi (Linux disi) -- Linux'ta bu yol kullanilmaz
    gercek = os.path.basename(parcalar[0])
    # Tam eslesme ya da ayni temel ad (argv[0] mutlak yol olabilir).
    return gercek == argv0 or os.path.splitext(gercek)[0] == os.path.splitext(argv0)[0]


def pid_yaz(ad: str, pid: int) -> None:
    hedef = pid_yolu(ad)
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text(f"{pid}\n", encoding="utf-8")


def pid_sil(ad: str) -> None:
    """Basarisiz baslatmadan kalma pid dosyasini temizler (durdurma basarisinda da)."""
    try:
        pid_yolu(ad).unlink()
    except FileNotFoundError:
        pass


def log_son_satirlar(ad: str, adet: int = LOG_SON_SATIR) -> list[str]:
    """Log'un son N satiri (dosya yoksa bos liste)."""
    try:
        metin = log_yolu(ad).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return metin.splitlines()[-adet:]


def _hedef_durumuna_geldi(servis: Servis) -> bool:
    """Port acik MI ve (saglik_url varsa) saglikli MI."""
    if not port_dinleniyor(servis.port):
        return False
    saglik = saglik_yok(servis.saglik_url)
    return saglik != "sagliksiz"


def _portu_bosalt(servis: Servis) -> bool:
    """Dinlenen yuvayi boslmasini bekler; bosalirsa True.

    Surec oldukten sonra dinleme yuvasi aninda kapanmaz: `durdur` cikis kodunu
    geri dondurunce kernel girdi tablosuna islenmemis bir yuva kalabilir. Bu
    arada yapilan bir `baslat` EADDRINUSE ile olur ve -- bizim oldurdugumuz
    servisi -- sessizce kaybederiz. Yalniz KENDI durmus pid'imizin yuvasini
    bekleriz; baska birinin portu ASLA dokunulmaz.
    """
    bitis = time.monotonic() + PORT_BOSALMA_SN
    while time.monotonic() < bitis:
        if not port_dinleniyor(servis.port):
            return True
        time.sleep(BEKLE_ADIM_SN)
    return not port_dinleniyor(servis.port)


def baslat(servis: Servis, *, kuru: bool = False) -> dict:
    """Servisi baslatir. Zaten calisiyorsa atlar. `--kuru` yalniz ne yapacagini yazar."""
    if kuru:
        return {"ad": servis.ad, "sonuc": KURU, "mesaj": f"baslatilacak: {servis.komut_metin}"}

    mevcut = durum_modul.olc(servis)
    if mevcut["durum"] == durum_modul.CALISIYOR:
        return {"ad": servis.ad, "sonuc": ZATEN_CALISIYOR, "mesaj": "zaten calisiyor, atlandi"}
    if mevcut["durum"] == durum_modul.PORT_DOLU_BILINMEYEN:
        # Port dolu ama bizim pid dosyamiz yok: baskasinin servisi. Uzerine
        # baslatmak onu bozabilir; dokunmadan hata veriyoruz. Tek istisna:
        # pid dosyamiz durmus bir sureci gosteriyorsa o yuva bizimki ve
        # sigalden hemen sonra bosalir (asagida bkz. _portu_bosalt).
        if mevcut["pid_dosyasindaki"] is None or not _portu_bosalt(servis):
            return {
                "ad": servis.ad,
                "sonuc": BASARISIZ,
                "mesaj": f"port {servis.port} dolu ama bizim pid dosyamiz yok -- baslatilmadi",
            }

    if servis.cwd is not None and not servis.cwd.is_dir():
        return {
            "ad": servis.ad,
            "sonuc": BASARISIZ,
            "mesaj": f"cwd yok: {servis.cwd}",
        }

    log = log_yolu(servis.ad)
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        # start_new_session: surec kendi grubu olur, durdurmada grup olarak sinyal alir.
        akis = log.open("ab")
        try:
            surec = subprocess.Popen(
                servis.baslat,
                cwd=str(servis.cwd) if servis.cwd else None,
                stdout=akis,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            akis.close()
    except (OSError, ValueError) as exc:
        return {"ad": servis.ad, "sonuc": BASARISIZ, "mesaj": f"baslatilamadi: {exc}"}

    pid_yaz(servis.ad, surec.pid)

    # bekle_sn icinde port acilana (ve saglikli olana) kadar bekle.
    bitis = time.monotonic() + servis.bekle_sn
    while time.monotonic() < bitis:
        if _hedef_durumuna_geldi(servis):
            return {"ad": servis.ad, "sonuc": CALISTI, "mesaj": f"calisti (pid {surec.pid})", "pid": surec.pid}
        if surec.poll() is not None:
            # Surec daha coktan sonlanmis; beklemeye devam etmenin anlami yok.
            pid_sil(servis.ad)
            return {
                "ad": servis.ad,
                "sonuc": BASARISIZ,
                "mesaj": f"komut hemen sonlandi (cikis {surec.returncode})",
            }
        time.sleep(BEKLE_ADIM_SN)

    # Zaman asimi: surec yine de yasiyor olabilir ama hedef duruma gelmedi.
    return {
        "ad": servis.ad,
        "sonuc": BASARISIZ,
        "mesaj": f"{servis.bekle_sn:g} sn icinde port {servis.port} acilmadi",
        "pid": surec.pid,
    }


def _sinyal_gonder(pid: int, sig: int) -> None:
    # Surec baslatirken start_new_session=True idi; grup olarak sinyal gonder.
    try:
        os.killpg(os.getpgid(pid), sig)
    except ProcessLookupError:
        pass
    except (OSError, PermissionError):
        # Grup yoksa (veya erisilemiyorsa) tek surece dene.
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def durdur(servis: Servis, *, zorla: bool = False, kuru: bool = False) -> dict:
    """Servisi durdurur -- YALNIZCA kendi pid dosyamizdaki sureci.

    Adimlar: pid yoksa zaten-durdu; port dolu ama bizim pid yoksa dokunma;
    Linux'ta cmdline dogrulamasi; durdur argv'si varsa onu; yoksa SIGTERM,
    SERVIS_DURDUR_BEKLE_SN (varsayilan 10) sn bekle, hâlâ yasiyorsa yalniz
    `--zorla` ile SIGKILL. Basarili durdurmada dinleme yuvasi da bosalir.
    """
    pid = pid_oku(servis.ad)

    if kuru:
        eylem = "durdurulacak" if pid else "durdurulacak yok (zaten durdu)"
        return {
            "ad": servis.ad,
            "sonuc": KURU,
            "mesaj": f"{eylem}: {' '.join(servis.durdur) if servis.durdur else f'sinyal (pid {pid})' if pid else '-'}",
        }

    if pid is None:
        # Bizim pid dosyamiz yok. Port doluysa baska biri kullaniyor -> ASLA dokunma.
        if port_dinleniyor(servis.port):
            return {
                "ad": servis.ad,
                "sonuc": PORT_DOLU_BILINMEYEN,
                "mesaj": f"port {servis.port} dolu ama bizim pid dosyamiz yok -- dokunulmadi",
            }
        return {"ad": servis.ad, "sonuc": ZATEN_DURDU, "mesaj": "zaten durdu (pid dosyasi yok)"}

    # Pid dosyamiz var ama sureci olu ise hedef zaten saglaniyor: pid YENIDEN
    # kullanimda olabilir, o yuzden hicbir sinyal GONDERILMEZ.
    if not durum_modul.surec_yasiyor(pid):
        pid_sil(servis.ad)
        return {
            "ad": servis.ad,
            "sonuc": ZATEN_DURDU,
            "mesaj": f"zaten durdu (pid {pid} yasamiyor)",
        }

    # Linux guvenlik korumasi: pid yeniden kullanilmis olabilir.
    if not cmdline_uyusuyor(pid, _argv0_duruyor(servis.baslat)):
        return {
            "ad": servis.ad,
            "sonuc": UYUSMUYOR,
            "mesaj": f"pid {pid} artik baska bir surec; dokunulmadi",
        }

    # Tanimda `durdur` argv'si varsa onu calistir (pid sinyali yerine).
    if servis.durdur:
        try:
            sonuc = subprocess.run(servis.durdur, cwd=str(servis.cwd) if servis.cwd else None)
        except (OSError, ValueError) as exc:
            return {"ad": servis.ad, "sonuc": DURMADI, "mesaj": f"durdur komutu calismadi: {exc}"}
        bitis = time.monotonic() + servis.bekle_sn
        while time.monotonic() < bitis:
            if not durum_modul.surec_yasiyor(pid) or not port_dinleniyor(servis.port):
                pid_sil(servis.ad)
                _portu_bosalt(servis)
                return {
                    "ad": servis.ad,
                    "mesaj": f"durduruldu (durdur komutu, cikis {sonuc.returncode})",
                    "sonuc": DURDU_SONUC,
                }
            time.sleep(BEKLE_ADIM_SN)
        return {
            "ad": servis.ad,
            "sonuc": DURMADI,
            "mesaj": "durdur komutu calisti ama hala ayakta",
        }

    # Sinyal yolu: SIGTERM -> bekle -> gerekirse SIGKILL (yalniz --zorla).
    _sinyal_gonder(pid, signal.SIGTERM)
    bitis = time.monotonic() + durdurme_bekle_sn()
    while time.monotonic() < bitis:
        if not durum_modul.surec_yasiyor(pid):
            pid_sil(servis.ad)
            _portu_bosalt(servis)
            return {"ad": servis.ad, "sonuc": DURDU_SONUC, "mesaj": "durduruldu (SIGTERM)"}
        time.sleep(BEKLE_ADIM_SN)

    if not zorla:
        return {
            "ad": servis.ad,
            "sonuc": DURMADI,
            "mesaj": "hala calisiyor, --zorla ekleyin",
        }

    _sinyal_gonder(pid, signal.SIGKILL)
    bitis = time.monotonic() + ZORLA_BEKLE_SN
    while time.monotonic() < bitis:
        if not durum_modul.surec_yasiyor(pid):
            pid_sil(servis.ad)
            _portu_bosalt(servis)
            return {"ad": servis.ad, "sonuc": DURDU_SONUC, "mesaj": "durduruldu (SIGKILL)"}
        time.sleep(BEKLE_ADIM_SN)
    return {"ad": servis.ad, "sonuc": DURMADI, "mesaj": "SIGKILL sonrasi hala ayakta"}