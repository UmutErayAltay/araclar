"""Çalıştırıcı arayüzü.

`ClaudeRunner` dalga B'nin gerçek headless çalıştırıcısıdır: `claude -p` alt süreç
olarak, istem STDIN'den, çıktı maskelenerek log dosyasına.

Dalga E: varsayılan olarak `--output-format stream-json --verbose` kullanılır; ham
JSONL **log'a yazılmaz**. Log'un içeriği ESKİ BİÇİMDE (insan okur düz metin) kalır:
akıştaki `result.result` metni, yoksa `assistant` metin bloklarının birleşimi.
Böylece `report.degerlendir`'in metin ayrıştırması ve ESKİ koşuların yeniden
değerlendirilmesi etkilenmez. Ham akırdan ayrıca bir YAPISAL özet çıkarılır ve
`RunSonuc.yapisal` ile kanıt katmanına verilir.

Güvenlik (bağlayıcı): izin sınıflandırıcısı reddederse görev `onay-bekliyor`
olur — reddi ASLA yeniden denemez, ASLA başka yoldan aşılmaz.
`--permission-mode bypassPermissions` ASLA kullanılmaz.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable, NamedTuple, Protocol, runtime_checkable

from . import guard
from .models import RunSonuc, Task

VARSAYILAN_KOMUT = ["cor", "claude", "-p"]
IZIN_KIPI = "acceptEdits"
# bypassPermissions bilinçli olarak yok: bu ortamda "unsafe agent" diye engellenir
# ve PLAN.md'nin bağlayıcı güvenlik kuralına aykırıdır.
SABIT_BAYRAKLAR = ("--permission-mode", IZIN_KIPI)
IZIN_ALETLERI = "Read,Write,Edit,Bash,Glob,Grep"

# Dalga E: akış (stream-json) bayrakları. `ORKESTRA_AKIS=duz` veya
# `akis_json=False` bunları tamamen kaldırıp ESKİ düz davranışa döner.
AKIS_BAYRAKLARI = ("--output-format", "stream-json", "--verbose")
AKIS_DUZ_ENV = "ORKESTRA_AKIS"
AKIS_TAVAN = 20 * 1024 * 1024
ARAC_CIKTI_TAVAN = 800
ARAC_SONUC_TAVAN = 40
YAPISAL_BILINMEYEN_ARAC = "bilinmiyor"

AGAN_ADI_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AGAN_DOSYASI = AGAN_ADI_DESENI.pattern

# Ajan tanım dosyası yoksa davranış DEĞİŞMEZ (yalnızca istem gönderilir), ama
# bu durum log'un İLK satırına görünür bir uyarı olarak düşer: çıktının ajanın
# kurallarına uymadığı kanıtsız kalmaması için (PLAN.md Dalga C).
UYARI_ONEK = "[uyari]"
AJAN_TANIMI_UYARISI = UYARI_ONEK + " ajan tanimi bulunamadi: {ajan} (yalnizca istem gonderildi)\n"

# Yalnızca AĞ hataları yeniden denenir.
AG_HATASI_DESENI = re.compile(
    r"(?i)\b(502|503|504)\b"
    r"|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN"
    r"|socket hang up|unable to connect|network error|fetch failed"
)

# İzin/sınıflandırıcı reddi: yeniden deneme YOK, görev onay bekler.
IZIN_REDDI_DESENI = re.compile(
    r"(?i)permission (for this action )?(was )?denied"
    r"|denied by the .*classifier"
    r"|classifier.*den(y|ied)"
    r"|Irreversible|Git Destructive"
    r"|requires? (user )?(approval|permission)"
    r"|not allowed"
)

AG_KODU = "ag-hatasi"
ZAMAN_ASIMI_KODU = 124
BULUNAMADI_HATASI = "claude-bulunamadi"
ZAMAN_ASIMI_HATASI = "zaman-asimi"

EN_FAZLA_DENEME = 3
GERI_CEKILME = (2, 4, 8)  # saniye; EN_FAZLA_DENEME=3 iken 2 ve 4 kullanılır
SIGKILL_BEKLE = 5.0
MAX_CIKTI = 5 * 1024 * 1024
KIRPILDI_NOTU = "[kırpıldı]"


@runtime_checkable
class Runner(Protocol):
    def calistir(self, task: Task) -> RunSonuc:
        """Görevi çalıştırır ve sonucu döndürür."""
        ...


class FakeRunner:
    """Senaryoya göre sonuç üreten kurgusal çalıştırıcı.

    `senaryo`: `basari` (varsayılan) | `hata` | `onay-gerekli` | `istisna`
    Alternatif olarak `calistir_ile` tek seferlik bir taklit verilebilir.
    """

    SENARYOLAR = ("basari", "hata", "onay-gerekli", "istisna")

    def __init__(
        self,
        senaryo: str = "basari",
        cikti_on: str = "Kurgusal calistirma tamamlandi.",
        kanit_on: list[str] | None = None,
        calistir_ile: Callable[[Task], RunSonuc] | None = None,
    ):
        if calistir_ile is None and senaryo not in self.SENARYOLAR:
            raise ValueError(f"bilinmeyen senaryo: {senaryo}")
        self.senaryo = senaryo
        self.cikti_on = cikti_on
        self.kanit_on = list(kanit_on) if kanit_on is not None else ["/kurgusal/kanit.png"]
        self._calistir_ile = calistir_ile
        self.gorevler: list[Task] = []

    def calistir(self, task: Task) -> RunSonuc:
        self.gorevler.append(task)
        if self._calistir_ile is not None:
            return self._calistir_ile(task)
        if self.senaryo == "basari":
            return RunSonuc(cikis_kodu=0, cikti=self.cikti_on, kanit_yollari=list(self.kanit_on))
        if self.senaryo == "hata":
            return RunSonuc(cikis_kodu=1, hata="kurgusal hata: islem basarisiz")
        if self.senaryo == "onay-gerekli":
            return RunSonuc(cikis_kodu=2, onay_gerekli=True, hata="kullanici onayi gerekiyor")
        raise RuntimeError("kurgusal calistirici istisna firlatti")


# -- ajan tanimi --------------------------------------------------------

_YARDIM_ONBELLEK: str | None = None


def _yardim_metni(komut: list[str]) -> str:
    """`claude --help` çıktısı (modül düzeyinde bir kez önbelleklenir)."""
    global _YARDIM_ONBELLEK
    if _YARDIM_ONBELLEK is None:
        try:
            tamam = subprocess.run(  # noqa: S603 — komut kullanıcı/kurulumdan gelir
                [*komut, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=60,
            )
            _YARDIM_ONBELLEK = (tamam.stdout or "") + (tamam.stderr or "")
        except (OSError, subprocess.SubprocessError):
            _YARDIM_ONBELLEK = ""
    return _YARDIM_ONBELLEK


def yardim_bayragi_var(yardim: str, bayrak: str) -> bool:
    """Yardım metninde tam bu bayrak var mı (`--agent` vs `--append-system-prompt`)."""
    return re.search(rf"^\s+{re.escape(bayrak)}[ ,<]", yardim, re.MULTILINE) is not None


def onbellek_sifirla() -> None:
    """`--help` önbelleğini temizler (testler ve uzun ömürlü süreçler için)."""
    global _YARDIM_ONBELLEK
    _YARDIM_ONBELLEK = None


def ajan_tanimi_yolu(ajan: str, cwd: str | os.PathLike | None) -> Path | None:
    """`<cwd>/.claude/agents/<ajan>.md` ya da `~/.claude/agents/<ajan>.md`.

    Ajan adı `^[a-z0-9][a-z0-9-]*$` ile kısıtlı (yol gezme yok); yine de çözülen
    yolun beklenen dizinde kaldığı doğrulanır.
    """
    if not isinstance(ajan, str) or not AGAN_ADI_DESENI.match(ajan):
        return None
    ad = f"{ajan}.md"
    kokler: list[Path] = []
    if cwd is not None:
        kokler.append(Path(cwd))
    kokler.append(Path.home())
    for kok in kokler:
        dizin = (kok / ".claude" / "agents").resolve()
        aday = dizin / ad
        # Savunma: çözülen yol beklenen dizinin içinde kalmalı.
        if aday.parent == dizin and aday.is_file():
            return aday
    return None


def frontmatter_kaldir(metin: str) -> str:
    """`---` ... `---` YAML başlığını atar, gövdeyi döndürür."""
    satirlar = metin.splitlines()
    if not satirlar or satirlar[0].strip() != "---":
        return metin
    for indeks in range(1, len(satirlar)):
        if satirlar[indeks].strip() == "---":
            return "\n".join(satirlar[indeks + 1 :]).strip()
    return metin


# -- Dalga E: stream-json akisi -----------------------------------------

# `tool_result.is_error` TEK BAŞINA red değildir: sıradan bir komutun çıkış kodu
# 1'i de böyle gelir. Red YALNIZCA içerik izin/onay kalıbına uyuyorsa doğrudur.
IZIN_REDDI_KALIBI = re.compile(
    r"requires? approval|was denied|permission .*denied|not allowed",
    re.IGNORECASE,
)


def akis_tamponu(cikti: str) -> tuple[str, bool]:
    """Ham akışı 20 MiB ile sınırlar; aşarsa **son tavanı** döndürür.

    `(icerik, kirpildi)`. Tavan AŞILIRSA akış ayrıştırılmaz: düz metin geri-düşüşü
    çalışır (5 MiB kırpma aynen korunur) ve yapısal kanıt üretilmez. Bu sınır
    log dosyasının değil, YAKALANAN çıktının sınırıdır: log dosyası zaten 5 MiB'de
    kırpılır, tavan oradan gelen çıktıya uygulanmalıdır.
    """
    kodla = cikti.encode("utf-8")
    if len(kodla) <= AKIS_TAVAN:
        return cikti, False
    return kodla[-AKIS_TAVAN:].decode("utf-8", errors="replace"), True


CIKTI_BASI = 200
CIKTI_KIRPMA_ISARETI = "\n[...]\n"


def _cikti_kirp(cikti: str) -> str:
    """Araç çıktısını `ARAC_CIKTI_TAVAN` karaktere indirir: BAŞ + SON.

    Test özeti (`29 failed, 1 passed in 0.11s`) çıktının SONUNDA olur; yalnız
    baştan kesmek canlıda tam bu satırı kaybettirirdi (gerçek koşuda ölçüldü).
    """
    if len(cikti) <= ARAC_CIKTI_TAVAN:
        return cikti
    son = ARAC_CIKTI_TAVAN - CIKTI_BASI - len(CIKTI_KIRPMA_ISARETI)
    return cikti[:CIKTI_BASI] + CIKTI_KIRPMA_ISARETI + cikti[-son:]


def _metin_birlestir(bloklar: list[str]) -> str:
    """Metin bloklarını ayraçsız birleştirir (araç girdisi JSON'u metinden ayrılır)."""
    return "".join(b for b in bloklar if b).strip()


def _metin_kutusu(deger) -> str:
    """`tool_result.content` metin veya blok listesi olabilir; ikisini de düzleştirir."""
    if isinstance(deger, str):
        return deger
    if isinstance(deger, list):
        parcalar = []
        for blok in deger:
            if isinstance(blok, dict) and blok.get("type") == "text":
                parcalar.append(str(blok.get("text") or ""))
            elif isinstance(blok, str):
                parcalar.append(blok)
        return "\n".join(p for p in parcalar if p)
    return ""


class AkisCiktisi(NamedTuple):
    """`akis_ayikla`'nın döndürdüğü üçlü."""

    duz_metin: str  # log'a yazılacak insan okur metin
    ozet: dict | None  # `result` olayı yoksa None → yapısal KANIT üretilmez
    olay_sayisi: int  # tanınan stream-json olayı sayısı (akış konuştu mu?)


def akis_ayikla(ham: str) -> AkisCiktisi:
    """Ham stream-json metnini `(duz_metin, ozet, olay_sayisi)` üçlüsüne çevirir.

    * `duz_metin` log'a yazılacak **insan okur** metindir: `result.result`
      varsa o (düz `-p` çıktısıyla aynı), yoksa `assistant` metin bloklarının
      birleşimi (kesilmiş akış geri-düşüşü).
    * JSON OLMAYAN satırlar (karışan stderr) SESSİZCE atlanır ama
      `atlanan_satir` sayacına yazılır.
    * `result` olayı YOKSA `ozet` `None` olur: yapısal KANIT üretilmez,
      kanıt katmanı yalnız düz metinden çalışır (eski `-p` ile aynı).
    """
    metin_bloklari: list[str] = []
    arac_adi: dict[str, str] = {}
    bekleyen: list[tuple[str, str]] = []  # (tool_use_id, arac) — FIFO eşleşirme
    arac_sonuclari: list[dict] = []
    son_olay: dict | None = None
    atlanan = 0
    olay_sayisi = 0

    for satir in ham.splitlines():
        satir = satir.strip()
        if not satir:
            continue
        try:
            olay = json.loads(satir)
        except ValueError:
            atlanan += 1  # stderr karışmış ya da kesilmiş satır: yut ve say
            continue
        if not isinstance(olay, dict) or not isinstance(olay.get("type"), str):
            atlanan += 1
            continue
        tur = olay["type"]
        olay_sayisi += 1

        if tur == "assistant":
            for blok in _mesaj_bloklari(olay):
                if blok.get("type") == "text":
                    metin_bloklari.append(str(blok.get("text") or ""))
                elif blok.get("type") == "tool_use" and isinstance(blok.get("id"), str):
                    arac_adi[blok["id"]] = str(blok.get("name") or YAPISAL_BILINMEYEN_ARAC)
                    bekleyen.append((blok["id"], arac_adi[blok["id"]]))
            continue

        if tur == "user":
            for blok in _mesaj_bloklari(olay):
                if blok.get("type") != "tool_result":
                    continue
                arac = _arac_eslestir(blok.get("tool_use_id"), bekleyen, arac_adi)
                cikti = _metin_kutusu(blok.get("content"))
                hata = blok.get("is_error") is True
                arac_sonuclari.append(
                    {
                        "arac": arac,
                        "hata": hata,
                        "red": bool(hata and IZIN_REDDI_KALIBI.search(cikti)),
                        "cikti": guard.maskele(_cikti_kirp(cikti)),
                    }
                )
            continue

        if tur == "result":
            son_olay = olay

    duz_metin = son_olay.get("result") if son_olay is not None else None
    if not isinstance(duz_metin, str):
        duz_metin = _metin_birlestir(metin_bloklari)
    if son_olay is None:
        return AkisCiktisi(duz_metin, None, olay_sayisi)

    return AkisCiktisi(duz_metin, {
        "arac_sonuclari": arac_sonuclari[-ARAC_SONUC_TAVAN:],
        "arac_sayisi": len(arac_sonuclari),
        "izin_reddi_sayisi": len(son_olay.get("permission_denials") or []),
        "durdurma": son_olay.get("stop_reason"),
        "tur_sayisi": _sayi(son_olay.get("num_turns")),
        "istemci_tahmini_usd": _ondalik(son_olay.get("total_cost_usd")),
        "atlanan_satir": atlanan,
    }, olay_sayisi)


def yapisal_ozet(
    ozet_kismi: dict,
    *,
    kirpildi: bool,
    red: bool,
) -> dict:
    """Ayrıştırılan parçayı kayda giden MASKELİ yapısal özete dönüştürür.

    `red`: ham metinde izin reddi kalıbı görüldü mü (metin taraması, akış
    ayrıştırmasından BAĞIMSIZ çalışır → geri-düşüşte de yakalanır).
    `istemci_tahmini_usd` istemcinin Anthropic fiyatıyla TAHMİNİDİR; cor
    ücretsiz modele gittiği için GERÇEK maliyet DEĞİLDİR.
    """
    return {
        "akis": True,
        "arac_sonuclari": ozet_kismi["arac_sonuclari"],
        "arac_sayisi": ozet_kismi["arac_sayisi"],
        "izin_reddi_sayisi": ozet_kismi["izin_reddi_sayisi"],
        "durdurma": ozet_kismi["durdurma"],
        "tur_sayisi": ozet_kismi["tur_sayisi"],
        "istemci_tahmini_usd": ozet_kismi["istemci_tahmini_usd"],
        "istemci_tahmini_notu": "gercek maliyet degildir",
        "atlanan_satir": ozet_kismi["atlanan_satir"],
        "kirpildi": bool(kirpildi),
        "son_mesaj_reddi": bool(red),
    }


def _mesaj_bloklari(olay: dict) -> list[dict]:
    """`assistant`/`user` olayının `message.content[]` blokları (yoksa boş)."""
    icerik = (olay.get("message") or {}).get("content")
    if not isinstance(icerik, list):
        return []
    return [b for b in icerik if isinstance(b, dict)]


def _arac_eslestir(kimlik, bekleyen: list, arac_adi: dict[str, str]) -> str:
    """`tool_result.tool_use_id` → araç adı; eşleşmezse `bilinmiyor`."""
    if isinstance(kimlik, str):
        for indeks, (kimlik_beklenen, arac) in enumerate(bekleyen):
            if kimlik_beklenen == kimlik:
                del bekleyen[indeks]
                return arac
        if kimlik in arac_adi:
            return arac_adi[kimlik]
    return YAPISAL_BILINMEYEN_ARAC


def _sayi(deger) -> int | None:
    """`int` ya da `None` (`bool` sayı sayılmaz)."""
    return (
        int(deger)
        if isinstance(deger, int) and not isinstance(deger, bool)
        else None
    )


def _ondalik(deger) -> float | None:
    """`float`/`int` → `float`, aksi hâlde `None`."""
    if isinstance(deger, bool) or not isinstance(deger, (int, float)):
        return None
    return float(deger)


# -- ClaudeRunner -------------------------------------------------------


def varsayilan_cikti_dizini() -> Path:
    return Path.home() / ".orkestra" / "runs"


class ClaudeRunner:
    """`claude -p` alt süreciyle headless görev çalıştırır.

    İstem STDIN'den verilir (komut satırında görünmez). Birleşik stdout+stderr
    maskelenerek `cikti_dizini/<task_id>-<zaman>.log` dosyasına yazılır ve
    `RunSonuc.cikti` bu dosyanın yoludur.
    """

    def __init__(
        self,
        komut: list[str] | str | None = None,
        model: str | None = None,
        cwd: str | os.PathLike | None = None,
        zaman_asimi: int = 1800,
        cikti_dizini: str | os.PathLike | None = None,
        uyku: Callable[[float], None] = time.sleep,
        akis_json: bool = True,
    ):
        self.komut = self._komutu_coz(komut)
        self.model = model
        self.cwd = str(cwd) if cwd is not None else None
        self.zaman_asimi = int(zaman_asimi)
        self.cikti_dizini = (
            Path(cikti_dizini).expanduser() if cikti_dizini is not None
            else varsayilan_cikti_dizini()
        )
        self.uyku = uyku
        self.akis_json = bool(akis_json) and os.environ.get(AKIS_DUZ_ENV) != "duz"

    @staticmethod
    def _komutu_coz(komut: list[str] | str | None) -> list[str]:
        if komut is not None:
            if isinstance(komut, str):
                return shlex.split(komut)
            return list(komut)
        ortam = os.environ.get("ORKESTRA_CLAUDE_CMD")
        if ortam and ortam.strip():
            return shlex.split(ortam)
        return list(VARSAYILAN_KOMUT)

    # -- komut satiri -------------------------------------------------

    def _taban_bayraklar(self) -> list[str]:
        bayraklar = list(self.komut)
        if self.model:
            bayraklar += ["--model", self.model]
        bayraklar += list(SABIT_BAYRAKLAR)
        bayraklar += ["--allowedTools", IZIN_ALETLERI]
        if self.akis_json:
            bayraklar += list(AKIS_BAYRAKLARI)
        return bayraklar

    def komut_satiri(self, task: Task) -> list[str]:
        """Bu görev için çalıştırılacak tam argv (testler bunu sabitler).

        İstem burada YOK: yalnızca STDIN'den gider, böylece `ps`'te görünmez.
        """
        bayraklar = self._taban_bayraklar()
        ajan = task.ajan
        if not ajan:
            return bayraklar
        yol = ajan_tanimi_yolu(ajan, self.cwd)
        if yol is None:
            # Tanım dosyası yok: yalnızca istem gönderilir. Değişen davranış YOK;
            # durum log'un İLK satırına uyarı olarak düşer (bkz. `calistir`).
            return bayraklar
        if yardim_bayragi_var(_yardim_metni(self.komut), "--agent"):
            return bayraklar + ["--agent", ajan]
        # --agent yoksa gövdeyi sistem istemine ekle.
        return bayraklar + [
            "--append-system-prompt",
            frontmatter_kaldir(yol.read_text(encoding="utf-8", errors="replace")),
        ]

    # -- calistirma ----------------------------------------------------

    def calistir(self, task: Task) -> RunSonuc:
        self.cikti_dizini.mkdir(parents=True, exist_ok=True, mode=0o700)
        log_yolu = self._log_yolu(task)
        argv = self.komut_satiri(task)
        # Uyarı log'un İLK satırına bir kez yazılır; her denemede tekrar edilmez.
        uyari_basligi = ""
        if task.ajan and ajan_tanimi_yolu(task.ajan, self.cwd) is None:
            uyari_basligi = AJAN_TANIMI_UYARISI.format(ajan=task.ajan)
        deneme = 0
        while True:
            deneme += 1
            try:
                return self._tek_deneme(argv, task.istem, log_yolu, deneme, uyari_basligi)
            except FileNotFoundError:
                return RunSonuc(cikis_kodu=127, cikti=str(log_yolu), hata=BULUNAMADI_HATASI)
            except _AgHatasi:
                if deneme >= EN_FAZLA_DENEME:
                    return RunSonuc(
                        cikis_kodu=1,
                        cikti=str(log_yolu),
                        hata=f"{AG_KODU} ({deneme} deneme)",
                    )
                self.uyku(GERI_CEKILME[min(deneme - 1, len(GERI_CEKILME) - 1)])

    def _log_yolu(self, task: Task) -> Path:
        zaman = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
        return self.cikti_dizini / f"{task.id}-{zaman}.log"

    def _tek_deneme(
        self, argv: list[str], istem: str, log_yolu: Path, deneme: int, uyari_basligi: str = ""
    ) -> RunSonuc:
        try:
            surec = subprocess.Popen(  # noqa: S603 — komut kurulumdan/kullanıcıdan gelir
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=self.cwd,
                start_new_session=True,
            )
        except FileNotFoundError:
            raise
        except OSError:
            # Çalıştırılamayan komut (izin yok vb.) — yeniden deneme yok.
            return RunSonuc(cikis_kodu=127, cikti=str(log_yolu), hata=BULUNAMADI_HATASI)

        zaman_asimi = False
        try:
            ham, _ = surec.communicate(input=istem.encode("utf-8"), timeout=self.zaman_asimi)
        except subprocess.TimeoutExpired:
            zaman_asimi = True
            self._surec_grubunu_oldur(surec)
            try:
                ham, _ = surec.communicate(timeout=SIGKILL_BEKLE)
            except subprocess.TimeoutExpired:  # pragma: no cover — SIGKILL sonrasi
                ham = b""

        cikti = (ham or b"").decode("utf-8", errors="replace")
        kod = surec.returncode if surec.returncode is not None else ZAMAN_ASIMI_KODU
        if zaman_asimi:
            kod = ZAMAN_ASIMI_KODU

        self._ham_logu_yaz(log_yolu, cikti, deneme, uyari_basligi)
        # Denetim maskelenmemiş metin üzerinden yapılır; kayda maskeli gider.
        yapisal = self._yapisal_hazirla(log_yolu, cikti) if self.akis_json else None
        if zaman_asimi:
            return RunSonuc(
                cikis_kodu=ZAMAN_ASIMI_KODU, cikti=str(log_yolu),
                hata=ZAMAN_ASIMI_HATASI, yapisal=yapisal,
            )
        if kod == 0:
            return RunSonuc(cikis_kodu=0, cikti=str(log_yolu), yapisal=yapisal)
        if IZIN_REDDI_DESENI.search(cikti):
            # Bağlayıcı kural: sınıflandırıcı reddederse kullanıcı onayı bekler.
            return RunSonuc(
                cikis_kodu=kod, cikti=str(log_yolu), onay_gerekli=True, yapisal=yapisal
            )
        if AG_HATASI_DESENI.search(cikti):
            raise _AgHatasi()
        return RunSonuc(
            cikis_kodu=kod, cikti=str(log_yolu),
            hata=f"claude cikis kodu {kod}", yapisal=yapisal,
        )

    def _yapisal_hazirla(self, log_yolu: Path, cikti: str) -> dict | None:
        """Ham akıştan düz metni + yapısal özeti çıkarır, log'u DÜZ METNE çevirir.

        Ham JSONL log'a YAZILMAZ: log'un içeriği eski biçimde (insan okur metin)
        kalır → `report.degerlendir` ve ESKİ koşuların yeniden değerlendirilmesi
        ETKİLENMEZ. Kararlar:

        * **Akış konuşmadıysa** (hiç stream-json olayı yok — örn. `claude` bu
          bayrakları desteklemiyor, `FAKE_MODE=buyuk` vb.): log DOKUNULMAZ, yani
          deneme başlıkları, ajan-tanımı uyarısı ve 5 MiB kırpma AYNEN kalır.
        * Akış konuştuysa ama `result` olayı yoksa (kesilmiş süreç): yalnız
          düz metne çevrilir, yapısal özet `None` kalır.
        * Akış 20 MiB'ı aşarsa: ham metin + 5 MiB kırpma geri-dönüşü.
        """
        ham_akis, kirpildi = akis_tamponu(cikti)
        duz, ozet_kismi, olay_sayisi = akis_ayikla(ham_akis)
        if not olay_sayisi:
            return None  # akış konuşmadı: log zaten doğru yazıldı, dokunma
        if not kirpildi:
            self._duz_metin_yaz(log_yolu, duz)
        if kirpildi or ozet_kismi is None:
            if kirpildi:
                self._duz_metin_yaz(log_yolu, cikti)  # ham metin + 5 MiB kırpma
            return None
        # `son_mesaj_reddi` HAM metinden okunur: izin reddi taraması akış
        # ayrıştırmasından bağımsızdır (kesilmiş akışta da yakalanır).
        return yapisal_ozet(
            ozet_kismi,
            kirpildi=False,
            red=bool(IZIN_REDDI_DESENI.search(ham_akis)),
        )

    def _surec_grubunu_oldur(self, surec: subprocess.Popen) -> None:
        """Süreç GRUBU: önce SIGTERM, 5 sn sonra SIGKILL (çocuk süreç bırakmaz)."""
        if os.name == "nt":  # pragma: no cover — bu container POSIX
            # Windows'ta en makul karşılık: taskkill /T (ağaç) /F (zorla).
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

    def _yaz_0600(self, log_yolu: Path, metin: str) -> None:
        """Metni 0600 dosyaya YAZAR (dosyayı keser); fsync ile kapatır."""
        fd = os.open(str(log_yolu), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as akis:
            akis.write(metin)
            akis.flush()
            os.fsync(akis.fileno())
        os.chmod(log_yolu, 0o600)

    def _ham_logu_yaz(
        self, log_yolu: Path, cikti: str, deneme: int, uyari_basligi: str = ""
    ) -> None:
        """Ham (akış modunda JSONL) çıktıyı 0600 dosyaya EKler; >5 MiB ise sonu tutar."""
        govde = guard.maskele(cikti)
        if len(govde.encode("utf-8")) > MAX_CIKTI:
            govde = KIRPILDI_NOTU + "\n" + govde[-MAX_CIKTI:]
        baslik = f"--- deneme {deneme} ---\n" if deneme > 1 else ""
        onceki = ""
        if log_yolu.exists():
            onceki = log_yolu.read_text(encoding="utf-8", errors="replace")
        # Uyarı yalnızca ilk yazımda başa düşer (dosya yokken).
        onceki = onceki or uyari_basligi
        # Dosyayı 0600 ile oluştur/aç (çok kanıtlı test için).
        fd = os.open(str(log_yolu), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as akis:
            akis.write(onceki + baslik + govde)
            akis.flush()
            os.fsync(akis.fileno())
        os.chmod(log_yolu, 0o600)

    def _duz_metin_yaz(self, log_yolu: Path, metin: str) -> None:
        """Maskelenmiş düz metni 0600 dosyaya YAZAR (dosyayı keser).

        Akış modunda ham JSONL'i insan okur metne çevirirken kullanılır; 5 MiB
        sınırı aynen uygulanır (sınırı aşarsa `[kırpıldı]` notu düşer).
        """
        govde = guard.maskele(metin)
        if len(govde.encode("utf-8")) > MAX_CIKTI:
            govde = KIRPILDI_NOTU + "\n" + govde[-MAX_CIKTI:]
        self._yaz_0600(log_yolu, govde)


class _AgHatasi(Exception):
    """Yalnızca ağ hatalarında yeniden denemeyi tetikler."""
