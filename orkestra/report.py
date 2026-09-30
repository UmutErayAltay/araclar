"""Ajan raporunu ayrıştırır: "bitti" demeyi kanıtla (Dalga D).

Neden var: `claude -p` çıktısı ajanın **SON MESAJIDIR**; araç çıktıları yoktur.
Yani rapordaki "525 passed", "giderildi", "hizalama mükemmel" birer **BEYANdır**
ve tek başına kanıt değildir. Bu modül beyanı toplar, ama orkestranın **kendi
baktığı** GÖZLEMLENEN kanıtlarla (dosya diskte var mı, imza doğru mu, koşu
boyunca git değişti mi) karşılaştırır.

Saf fonksiyondur: ağa çıkmaz, alt süreç çalıştırmaz, dosya YAZMAZ. Git durumu
dışarıdan verilir (`git_once`/`git_sonra`), çalışma dizini dışına çıkmaz.

Sonuç sınıfları (öncelik sırasıyla, ilk eşleşen kazanır):
  1. `reddedildi-suphesi` — SON MESAJINDA birinci şahıs red/engel bildirimi.
  2. `basarisiz`        — test `failed/error` > 0 ya da FAILED/Traceback.
  3. `kanitsiz`         — iddia var ama GÖZLEMLENEN kanıt yok.
  4. `kanitli`          — en az bir GÖZLEMLENEN kanıt.
  5. `degerlendirilmedi`— yalnızca eski/hatalı koşular.

Güvenlik: çözümlenen her görsel yolu `calisma_dizini` İÇİNDE olmalıdır; `..`,
mutlak dışı yol ve sembolik bağ kaçışı reddedilir (Dalga C'deki `guvenli_log_yolu`
deseninin aynısı). Rapor dosyası da aynı kurallara ve 512 KiB üst sınırına tabidir.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import guard

# -- sonuç sınıfları ------------------------------------------------------

KANITLI = "kanitli"
KANITSIZ = "kanitsiz"
BASARISIZ = "basarisiz"
REDDEDILDI = "reddedildi-suphesi"
DEGERLENDIRILMEDI = "degerlendirilmedi"

SONUC_SINIFLARI = (KANITLI, KANITSIZ, BASARISIZ, REDDEDILDI, DEGERLENDIRILMEDI)

# Web rozeti: renk + METİN (renge tek başına dayanmaz).
SONUC_ETIKETLERI = {
    KANITLI: "kanıtlı",
    KANITSIZ: "kanıtsız",
    BASARISIZ: "başarısız",
    REDDEDILDI: "red şüphesi",
    DEGERLENDIRILMEDI: "değerlendirilmedi",
}

KISA_RAPOR_ESIK = 40
SON_MESAJ_SATIR = 60
RAPOR_DOSYASI_TAVAN = 512 * 1024
# Koşu log'u için okuma üst sınırı (bellek koruması). Runner zaten 5 MiB'de
# kırpar; buradaki sınır aynı mertebededir.
MAX_LOG_OKUMA = 8 * 1024 * 1024

# -- kanıt bölümü biçimi --------------------------------------------------

KANIT_BASLIGI = re.compile(r"^#{1,6}\s*kan[ıi]t\b", re.IGNORECASE | re.MULTILINE)
SATIR_KANIT_TEST = re.compile(r"^\s*[-*]?\s*\**\s*test\s*:", re.IGNORECASE)
SATIR_KANIT_GORSEL = re.compile(r"^\s*[-*]?\s*\**\s*görsel\s*:", re.IGNORECASE)
GORSEL_UZANTI = re.compile(r"\.(png|jpe?g|webp|gif)\b", re.IGNORECASE)

# Rapor metnindeki görsel yolları: backtick, parantez, tırnak veya boşlukla ayrılmış.
# `--` ve `:` gibi ayraçlar yolun parçası olabilir; yalnız gerçek dosya adı yakalanır.
YOL_DESENI = re.compile(
    r"`([^`\n]*?\.(?:png|jpe?g|webp|gif))`"
    r"|\(([^()\n]*?\.(?:png|jpe?g|webp|gif))\)"
    r"|[\"'“]([^\"'“”\n]*?\.(?:png|jpe?g|webp|gif))[\"'”]"
    # Çıplak yol: mutlak (`/…`) veya göreli (`a/b/…`). Sondaki nokta/pozisyon
    # `test.png.` (cümle sonu) ve `...png` (glob) kalıntılarını sızdırmaz.
    r"|(?<![\w.-])(/[^\s:,;()\[\]{}<>\"']*?\.(?:png|jpe?g|webp|gif))(?=[\s)\],.;:'\"”]|$)"
    r"|(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:png|jpe?g|webp|gif))(?=[\s)\],.;:'\"”]|$)"
)


# -- izin reddi (1. öncelik, YANLIŞ POZİTİF koruması zorunlu) -------------

# Bu repo'nun kendi raporları "PermissionError", "permission denied durumunda",
# "IZIN_REDDI_DESENI" gibi sözcükleri sık kullanır. Bunlar KOD/ERROR anlatısıdır,
# red bildirimi DEĞİLDİR. Aşağıdaki desenler BİRİNCİ ŞAHIS + red/engel anlamı
# birlikte ister; ayrıca eşleşmenin ÇEVRESİNDEKİ pencere kod bağlamıysa (backtick,
# dosya yolu, hata sembolü, test/senaryo anlatısı) reddedilir.
#
# Türkçe büyük/nüfus `İ`/`ı` altında `re.IGNORECASE` İŞE YARAMAZ (Unicode
# katlama `İ`yi `i`+birleşen nokta yapar). Bu yüzden Türkçe desenler açık
# `[İIiı]` sınıflarıyla yazılmıştır.
REDDEDILME_KALIPLARI: tuple[re.Pattern[str], ...] = (
    # "I was blocked", "I could not run X because ... denied"
    re.compile(
        r"\b(?:i|we)\s+(?:was|were|am|are)\s+(?:blocked|denied|barred|refused|prevented)\b"
        r"|\b(?:i|we)\s+(?:could\s+not|couldn't|cannot|can't|was\s+unable\s+to|were\s+unable\s+to)\s+"
        r"\w+[^.\n]{0,80}?\b(?:denied|blocked|refused|disallowed|not\s+granted|needs?\s+approval"
        r"|requires?\s+approval|awaiting\s+approval|pending\s+approval)\b",
        re.IGNORECASE,
    ),
    # "Permission to write the file was not granted" / "permissions were denied"
    re.compile(
        r"\bpermissions?\b[^.\n]{0,70}?\b(?:was|were|is|are|has\s+been|have\s+been)?\s*"
        r"(?:denied|not\s+granted|not\s+available|not\s+authori[sz]ed)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:denied|blocked)\s+by\s+[^.\n]{0,40}?classifier\b", re.IGNORECASE),
    re.compile(r"\bthe\s+action\s+was\s+denied\b|\baction\s+denied\s+by\b", re.IGNORECASE),
    # "I requested permission to edit the config, but you haven't granted it"
    re.compile(
        r"\brequested\s+(?:permission|permissions|access)[^.\n]{0,70}?"
        r"\b(?:but\s+)?you\s+(?:haven'?t|have\s+not|never)\s+granted\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:needs?|requires?|awaiting|waiting\s+for|pending)\s+"
        r"(?:your\s+|the\s+user'?s?\s+|explicit\s+|manual\s+|further\s+)?"
        r"(?:approval|permission|confirmation|authori[sz]ation)\b",
        re.IGNORECASE,
    ),
    # "The command is not allowed" — ajan kendi çalıştıramadığını anlatıyor.
    re.compile(
        r"\b(?:the\s+)?\w+[^.\n]{0,40}?\bis\s+not\s+allowed\b",
        re.IGNORECASE,
    ),
    # --- Türkçe (büyük/nüfus I için açık sınıflar) ---
    re.compile(r"\b[İIiı]zin\s+verilmedi\b"),
    re.compile(r"\b[İIiı]zin\s+veril[İIiı]yor\b"),
    # Ek fiil zinciri: "İzin verilmediği için", "değiştiremedim", "yapamadım".
    re.compile(r"\bverilmed[iİı]\b|\bverilmi[şş]yor\b|\bverilir\s+se\b"
               # Fiil çekimi: "çalıştırılamadı", "değiştiremedim", "yapamadım",
               # "ekleyemedim". Gerçek `claude -p` red cümlesi tam budur.
               r"|\b[oO]nay\s+verilirse\b"
               r"|\b[çc]al[ıi][şs][tT]?[ıi]r[ıi]lamad[iı]\b"
               r"|\b[çc]al[ıi][şs]t[ıi]r[ıi]lamad[ıi]\b"
               r"|\bde[ğg][iİı]şt[iİı]remedim\b|\byapamad[iİı]m\b"
               r"|\b[ıi]lerleyemedim\b"
               r"|\bekleyemedim\b|\b[ée]kleyemedim\b"
               # "yazma izni gerektiriyor" / "izin gerektiriyor" — izin İSTEĞİ.
               r"|\b[ıi]zn[iıı]\s+gerektiriyor\b|\b[ıi]zn[iıı]\s+gerekiyor\b"),
    re.compile(r"\bengellendi\b|\bengellendi[ğĞ]im[iİ]?\b|\bengellenmi[şŞ]tir\b"),
    # NOT: `s`/dotless `ı` Unicode'te harf olduğundan `\b` burada güvenilmez
    # ("Sınıflandırıcı" içinde `S`+`ı` sınırı oluşmaz). `re.IGNORECASE` ASCII
    # büyük harfleri (S/SINIFLANDIRICI) yakalar; Türkçe'ye özgü harfler için
    # sınıflar AÇIK yazılmıştır (IGNORECASE noktasız ı'yı I'ya katlamaz).
    re.compile(r"[sS][ıIiı]n[ıIiı]fland[ıIiı]r[ıIiı]c[ıIiı]\s+reddetti\b"
               r"|[sS][ıIiı]n[ıIiı]fland[ıIiı]r[ıIiı]c[ıIiı]\s+reddi\s+(?:geldi|al[ıIiı]nd[ıIiı])\b",
               re.IGNORECASE),
    # "onay gerektiriyor" (istekli çekim) gerçek `claude -p` red cümlesinde
    # EN SIK gelen biçimdir; yalnız "gerekiyor/gerekiyordu" yetersiz kalıyordu.
    re.compile(r"\bonay\s+(?:gerekiyor|gerekiyordu|gerektiriyor|gerektiriyordu|bekliyor)\b"
               r"|\bkullan[ıI]c[ıI]\s+onay[ıI]\s+gerek\w*\b"
               r"|\bonay\s+alamadan\b"
               # "çıktısı bende yok", "bende yok" — red cümlesinin devamı.
               r"|\b(?:[çc][ıi]kt[ıi]s[ıi]|sonucu|ç[ıi]kt[ıi])\s+bende\s+yok\b"),
)

# Eşleşmenin ÇEVRESİNDEKİ pencere kod/tespit bağlamını gösteriyorsa reddedilir.
# Satırın tamamı değil: çünkü "525 passed" gibi gerçek kanıtlar aynı satırda
# olabilir ve kod bağlamı yalnız eşleşmenin etrafındadır.
KOD_BAGLAMLARI: tuple[re.Pattern[str], ...] = (
    re.compile(r"`[^`\n]*(?:denied|blocked|izin|IZIN|permission|onay|engell)[^`\n]*`",
               re.IGNORECASE),
    re.compile(r"\b(?:PermissionError|PermissionDenied|Errno\s*13|EACCES|EPERM)\b"),
    re.compile(r"\bIZIN_REDDI_DESENI\b"),
    re.compile(r"\bden\(y|ied\)\b|\|\s*not\s+granted", re.IGNORECASE),
    # Kural/kod anlatısı: "permission-denied path", "IZIN_REDDI_DESENI", "den(y|ied)".
    re.compile(r"\b(?:[a-z]+-)?denied[-\s]path\b|\bpath\b", re.IGNORECASE),
    # Türkçe: "permission denied durumunda yeniden deneme yok" — DAVRANIŞ kuralı.
    re.compile(r"\bdurumunda\b|\byeniden\s+deneme\b|\bdeneme\s+yok\b", re.IGNORECASE),
    # Test/senaryo ANLATISI: "testi: permission denied senaryosu ...",
    # "Test edildi: ... ", "senaryosunda ...", "I added a test asserting ...".
    re.compile(r"\btest(?:i|leri|ler|te|ler)?\s*(?:edildi|eklendi|yaz[ıI]ld[ıI]|mi[şŞ])\b",
               re.IGNORECASE),
    re.compile(r"\btest(?:i|leri|ler)?\s*:", re.IGNORECASE),
    re.compile(r"\b(?:added|wrote|assert(?:ing|ed)?|covered|verifying|checking)\s+"
               r"(?:a\s+|an?\s+|the\s+)?(?:new\s+)?(?:test|spec|case|assertion)\b",
               re.IGNORECASE),
    re.compile(r"\bsenaryo(?:su|lar|larında|sunda)?\b", re.IGNORECASE),
    re.compile(r"\b(?:pytest|unittest|assert|raises|fixture)\b", re.IGNORECASE),
    re.compile(r"\b(?:kural|kal[ıI]b[ıI]|desen|deseni|ö[çc][üu][şs]esi)\s+"
               r"(?:geni[şs]letildi|yaz[ıI]ld[ıI]|tan[ıI]ml[ıI]|test)", re.IGNORECASE),
    re.compile(r"\.(?:py|js|ts|go|rs|java|rb|sh)\b"),
    re.compile(r"\bTraceback\b"),
)

# Emin olunamayan durumlar: `uyari` listesine düşer, `reddedildi-suphesi` DEĞİLDİR.
BELIRSIZ_KALIP = re.compile(
    r"\b(?:cannot|can't|could not|couldn't|not\s+allowed|blocked|denied)\b"
    r"|\b[İIiı]zin|\bengell|\bredded",
    re.IGNORECASE,
)

# Eşleşme çevresinde bakılacak pencere (karakter).
PENCERE = 70


def _kod_iceriginde_mi(metin: str, bas: int, bit: int) -> bool:
    """Eşleşme (`bas:bit`) kod/tespit bağlamında mı?

    Kod blokları (```) zaten `_reddedilme_bul` içinde boşaltılır; burada
    yalnız EŞLEŞMENİN ETRAFINDaki pencere denetlenir.
    """
    pencere = metin[max(0, bas - PENCERE): bit + PENCERE]
    return any(desen.search(pencere) for desen in KOD_BAGLAMLARI)


# -- iddia (BEYAN) kalıpları ------------------------------------------------

IDDIA_DESENLERI: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgiderildi\b|\bdüzeltildi\b|\bdüzeltme yapıldı\b", re.IGNORECASE),
    re.compile(r"\bsorunsuz\b|\bhatasız\b|\bmükemmel\b|\b kusursuz\b", re.IGNORECASE),
    re.compile(r"\btamamen\b|\beksiksiz\b|\bhijikensiz\b", re.IGNORECASE),
    # "hiçbir etiket daireye binmiyor", "hiçbir sorun kalmadı" — olumsuz
    # cümle gerekir: yalnız "hiçbir" iddia saymaz (bir kural adı olabilir).
    re.compile(
        r"\bhi[çc]bir\b[^.\n]{0,80}?\b(?:yok|binmiyor|kalmad[ıi]|kalm[ıi]yor|"
        r"g[öo]r[üu]nm[üu]yor|de[ğg]il)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bfixed\b|\bresolved\b|\bno\s+issues\b|\bno\s+problems\b", re.IGNORECASE),
    re.compile(r"\bworks\b|\ball\s+tests?\s+(?:pass|passed)\b|\bgreen\b", re.IGNORECASE),
    re.compile(r"\b(?:implemented|added|removed|cleaned\s+up)\b", re.IGNORECASE),
    re.compile(r"\b(?:uygulandı|eklendi|ekledim|yazdım|değiştirdim|commit(?:ledim)?)\b",
               re.IGNORECASE),
)

# "dosya yazdım/değiştirdim/commit" — git kanıtı olmadan kanıtsız sayılır
DEGISIM_IDDIASI = re.compile(
    r"\b(?:yazdım|yazdı|ekledim|ekledi|değiştirdim|değiştirdi|commit(?:ledim|ledi)?|"
    r"uyguladım|güncelledim|created|wrote|added|modified|committed|edited)\b",
    re.IGNORECASE,
)


# -- veri sınıfları --------------------------------------------------------


@dataclass
class TestBeyani:
    """Raporda BEYAN edilen test sonucu (gözlemlenebilir çıktı DEĞİLDİR)."""

    tur: str            # pytest | unittest | go | jest | cargo
    passed: int | None = None
    failed: int | None = None
    error: int | None = None
    skipped: int | None = None
    metin: str = ""     # MASKELİ ham kalıntı

    def json(self) -> dict:
        return asdict(self)

    @property
    def basarisiz_mi(self) -> bool:
        return bool(self.failed or self.error)


@dataclass
class GorselKaniti:
    """Raporda geçen görsel yolunun GÖZLEMLENEN denetimi."""

    yol: str
    cozulmus: str = ""
    gecerli: bool = False
    gerekce: str = ""
    bayt: int = 0
    yeni_mi: bool | None = None   # baslangic sonrası mı değişti

    def json(self) -> dict:
        return asdict(self)


@dataclass
class Gerekce:
    """Bir kuralın neden uygulandığı — insan okur."""

    kural: str
    sonuc: str
    kanit: str = ""

    def json(self) -> dict:
        return asdict(self)


@dataclass
class Degerlendirme:
    """`degerlendir()`'in döndürdüğü tam sonuç (JSON'a çevrilebilir)."""

    sonuc: str = DEGERLENDIRILMEDI
    gorseller: list[GorselKaniti] = field(default_factory=list)
    testler: list[TestBeyani] = field(default_factory=list)
    iddialar: list[str] = field(default_factory=list)
    beyanlar: list[str] = field(default_factory=list)
    gorsel_beyanlar: list[str] = field(default_factory=list)
    gerekceler: list[Gerekce] = field(default_factory=list)
    uyarilar: list[str] = field(default_factory=list)
    git_degisti: bool | None = None
    rapor_dosyasi: str = ""
    kanit_durumu: str = DEGERLENDIRILMEDI
    ozet: str = ""
    # Dalga E: `claude -p --output-format stream-json` akışından gelen araç
    # sonuçları. `None` = akış kullanılmadı (eski koşu) → aşağıdaki kurallar
    # işlemez, davranış DALGA D'DEKİ GİBİDİR.
    yapisal: dict | None = None
    # Dalga E: akıştan GÖZLEMLENEN test sonuçları (beyan DEĞİLDİR; orkestra
    # `Bash` aracının gerçek çıktısını kendisi okumuştur).
    gozlemlenen_testler: list[TestBeyani] = field(default_factory=list)

    # -- türetilmiş görünümler ----------------------------------------

    @property
    def gecerli_gorsel_sayisi(self) -> int:
        return sum(1 for g in self.gorseller if g.gecerli)

    @property
    def gecerli_test_sayisi(self) -> int:
        return sum(1 for t in self.testler if not t.basarisiz_mi)

    def gozlemlenen_kanit_sayi(self) -> int:
        """GÖZLEMLENEN kanıt sayısı (beyan SAYILMAZ).

        Dalga E: akıştan okunan (gözlemlenen) temiz test koşuları da sayılır.
        """
        return (
            self.gecerli_gorsel_sayisi
            + (1 if self.git_degisti else 0)
            + self.gozlemlenen_temiz_test_sayisi()
        )

    def gozlemlenen_temiz_test_sayisi(self) -> int:
        """GÖZLEMLENEN (beyan olmayan) ve BAŞARILI test koşusu sayısı."""
        return len([t for t in self.gozlemlenen_testler if not t.basarisiz_mi])

    @property
    def kanitli_mi(self) -> bool:
        return self.sonuc == KANITLI

    @property
    def uyari_mi(self) -> bool:
        """`liste`/web'de görünür uyarı taşıyan sonuçlar."""
        return self.sonuc in (KANITSIZ, BASARISIZ, REDDEDILDI)

    def json(self) -> dict:
        return {
            "sonuc": self.sonuc,
            "sonuc_etiket": SONUC_ETIKETLERI.get(self.sonuc, self.sonuc),
            "gorseller": [g.json() for g in self.gorseller],
            "testler": [t.json() for t in self.testler],
            "iddialar": list(self.iddialar),
            "beyanlar": list(self.beyanlar),
            "gorsel_beyanlar": list(self.gorsel_beyanlar),
            "gerekceler": [g.json() for g in self.gerekceler],
            "uyarilar": list(self.uyarilar),
            "git_degisti": self.git_degisti,
            "rapor_dosyasi": self.rapor_dosyasi,
            "kanit_durumu": self.kanit_durumu,
            "ozet": self.ozet,
            "gozlemlenen_kanit_sayi": self.gozlemlenen_kanit_sayi(),
        }

    def ozet_metin(self) -> str:
        """Tek satırlık insan-okur özet."""
        return (
            f"{SONUC_ETIKETLERI.get(self.sonuc, self.sonuc)}: "
            f"{self.gecerli_gorsel_sayisi} gözlemlenen görsel, "
            f"{self.gecerli_test_sayisi} test beyanı, "
            f"{len(self.iddialar)} iddia, "
            f"git={'değişti' if self.git_degisti else ('değişmedi' if self.git_degisti is False else 'bilinmiyor')}"
        )


# -- yol güvenliği (Dalga C deseni) ----------------------------------------


def guvenli_cöz(yol: str, kok: Path) -> Path | None:
    """Yolu `kok` ALTINDA olacak şekilde çözer; kaçış varsa `None`.

    `resolve()` + `is_relative_to` çifti `..`, mutlak dışı yol ve **dışarıya
    işaret eden sembolik link** üçünü birden reddeder (Dalga C `guvenli_log_yolu`).
    """
    if not yol or not isinstance(yol, str):
        return None
    try:
        aday = Path(yol).expanduser()
        if not aday.is_absolute():
            aday = kok / aday
        cozulmus = aday.resolve()
        kok_c = kok.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if cozulmus == kok_c or not cozulmus.is_relative_to(kok_c):
        return None
    return cozulmus


# -- görsel imzaları -------------------------------------------------------

PNG_IMZA = b"\x89PNG\r\n\x1a\n"
GIF_IMZA = (b"GIF87a", b"GIF89a")
JPEG_IMZA = b"\xff\xd8\xff"
WEBP_IMZA = b"RIFF"


def imza_tur(baytlar: bytes) -> str:
    """İlk baytlardan gerçek formatı söyler; bilinmiyorsa boş dize."""
    if baytlar.startswith(PNG_IMZA):
        return "png"
    if baytlar.startswith(GIF_IMZA):
        return "gif"
    if baytlar.startswith(JPEG_IMZA):
        return "jpeg"
    if baytlar[:4] == WEBP_IMZA and baytlar[8:12] == b"WEBP":
        return "webp"
    return ""


def _beklenen_tur(yol: str) -> str:
    k = yol.lower().rsplit(".", 1)[-1] if "." in yol else ""
    return "jpeg" if k in ("jpg", "jpeg") else k


# -- test beyanları ayrıştırma --------------------------------------------

def testleri_ayikla(metin: str) -> list[TestBeyani]:
    """Rapordan test sonucu BEYANlarını çıkarır (gözlemleme değil)."""
    testler: list[TestBeyani] = []
    gecen = set()

    def _ekle(tur: str, **kw) -> None:
        anahtar = (tur, kw.get("metin", "")[:60])
        if anahtar in gecen:
            return
        gecen.add(anahtar)
        testler.append(TestBeyani(tur=tur, metin=guard.maskele(kw.pop("metin", ""))[:160], **kw))

    for satir in metin.splitlines():
        s = satir.strip()
        if not s:
            continue

        # --- ÖZGÜL biçimler ÖNCE denenir: jest/cargo satırları da "N passed"
        # içerdiği için genel pytest deseni onları YUTMASIN.

        # cargo: "test result: ok. 12 passed; 0 failed" / "FAILED. 3 passed; 2 failed"
        m = re.search(r"test result:\s*ok\.\s*(\d+)\s+passed;\s*(\d+)\s+failed", s)
        if m:
            _ekle("cargo", passed=int(m.group(1)), failed=int(m.group(2)), metin=s)
            continue
        m = re.search(r"test result:\s*FAILED\.\s*(\d+)\s+passed;\s*(\d+)\s+failed", s)
        if m:
            _ekle("cargo", passed=int(m.group(1)), failed=int(m.group(2)), metin=s)
            continue
        m = re.search(r"test result:\s*FAILED\.\s*(\d+)\s+failed", s)
        if m:
            _ekle("cargo", passed=None, failed=int(m.group(1)), metin=s)
            continue

        # jest/vitest: "Tests:  4 passed, 4 total" | "Tests: 2 failed, 5 passed, 7 total"
        if re.search(r"\bTests:", s):
            f = re.search(r"(\d+)\s+failed", s, re.IGNORECASE)
            p = re.search(r"(\d+)\s+passed", s, re.IGNORECASE)
            if p or f:
                _ekle("jest", passed=int(p.group(1)) if p else 0,
                      failed=int(f.group(1)) if f else 0, metin=s)
                continue

        # go: "ok  \tpkg/name\t0.2s" | "FAIL\tpkg/name\t0.1s"
        if re.match(r"^ok\s+\S+\s+[\d.]+s$", s) or re.match(r"^FAIL\s+\S+", s):
            _ekle("go", passed=1 if s.startswith("ok") else 0,
                  failed=0 if s.startswith("ok") else 1, metin=s)
            continue

        # unittest: "Ran 12 tests" + "OK" / "FAILED (failures=2, errors=1)"
        m = re.search(r"\bRan\s+(\d+)\s+tests?\b", s, re.IGNORECASE)
        if m:
            _ekle("unittest", passed=int(m.group(1)), failed=0, metin=s)
            continue
        if re.search(r"\bFAILED\s*\(", s):
            f = re.search(r"failures?\s*=\s*(\d+)", s, re.IGNORECASE)
            e = re.search(r"errors?\s*=\s*(\d+)", s, re.IGNORECASE)
            _ekle("unittest", passed=None, failed=int(f.group(1)) if f else 0,
                  error=int(e.group(1)) if e else None, metin=s)
            continue

        if re.search(r"\bno tests ran\b", s, re.IGNORECASE):
            _ekle("pytest", passed=0, failed=0, metin=s)
            continue

        # --- GENEL pytest: "== 12 passed in 1.2s ==" | "525 passed" | "3 failed, 10 passed"
        m = re.search(r"(?:=+\s*)?(\d+)\s+passed", s, re.IGNORECASE)
        if m and re.search(r"passed", s, re.IGNORECASE):
            f = re.search(r"(\d+)\s+failed", s, re.IGNORECASE)
            e = re.search(r"(\d+)\s+error", s, re.IGNORECASE)
            k = re.search(r"(\d+)\s+skipped", s, re.IGNORECASE)
            _ekle("pytest", passed=int(m.group(1)),
                  failed=int(f.group(1)) if f else None,
                  error=int(e.group(1)) if e else None,
                  skipped=int(k.group(1)) if k else None, metin=s)
            continue
    return testler


# -- iddia (beyan) ayrıştırma ---------------------------------------------

def _iddialari_bul(metin: str) -> list[str]:
    """Rapordaki iddia CÜMLELERİNİ (beyan) döndürür."""
    bulunan: list[str] = []
    for satir in metin.splitlines():
        s = satir.strip().lstrip("-*#").strip()
        if not s:
            continue
        for desen in IDDIA_DESENLERI:
            if desen.search(s):
                bulunan.append(guard.maskele(s[:160]))
                break
    return bulunan


def _gorsel_yollari(metin: str) -> list[str]:
    """Raporda geçen görsel yollarını sırayla döndürür (tekilleştirilmiş)."""
    yollar: list[str] = []
    for m in YOL_DESENI.finditer(metin):
        ham = next((g for g in m.groups() if g), None)
        if not ham:
            continue
        yol = ham.strip().strip("*_ ")
        # Markdown tablo/glob kalıntıları: "docs/ekran/*.png" tek dosya değildir.
        if "*" in yol or "?" in yol or yol.startswith("/tmp/") and "*" in yol:
            continue
        if yol not in yollar:
            yollar.append(yol)
    return yollar


def _kanit_bolumu(metin: str) -> str | None:
    """`## Kanıt` bölümünü döndürür; yoksa `None` (hata DEĞİLDİR)."""
    satirler = metin.splitlines()
    baslangic = None
    seviye = 0
    for indeks, satir in enumerate(satirler):
        if KANIT_BASLIGI.match(satir):
            baslangic = indeks + 1
            seviye = len(satir) - len(satir.lstrip("#"))
            break
    if baslangic is None:
        return None
    govde: list[str] = []
    for satir in satirler[baslangic:]:
        if satir.lstrip().startswith("#"):
            seviye2 = len(satir) - len(satir.lstrip("#"))
            if seviye2 <= seviye:
                break
        govde.append(satir)
    return "\n".join(govde)


# -- Dalga E: yapısal (GÖZLEMLENEN) akış kanıtı -------------------------


def _gozlemlenen_testler(yapisal: dict | None) -> list[TestBeyani]:
    """Akıştaki `Bash` araç çıktılarından test sonucu okur.

    `Bash` çıktısı orkestranın KENDİ gördüğü veridir → beyan değildir. Başarısız
    bir `pytest` (çıkış kodu 1) canlıda `is_error=true` gelir ve GÖZLEMLENEN bir
    gerçektir: `hata` bayrağı ELENMEZ, `basarisiz` sınıfını üretmesi beklenir.
    Yalnız izin/onay reddi (`red`) atlanır: o bir test çıktısı değildir.
    """
    bulunan: list[TestBeyani] = []
    if not yapisal:
        return bulunan
    for sonuc in yapisal.get("arac_sonuclari") or []:
        if not isinstance(sonuc, dict):
            continue
        if sonuc.get("arac") != "Bash" or sonuc.get("red"):
            continue
        cikti = sonuc.get("cikti")
        if isinstance(cikti, str) and cikti:
            bulunan.extend(testleri_ayikla(cikti))
    return bulunan


def _gozlemlenen_basarisiz(testler: list[TestBeyani]) -> TestBeyani | None:
    """GÖZLEMLENEN son test koşusu başarısız mı?

    Aynı test koşusunun ARACIN SON gözlemi belirleyicidir: ajan "hepsi geçti"
    dese bile gözlem onu düşeltir. Beyan gözleme ASLA yükseltmez.
    """
    for tur in ("pytest", "unittest", "jest", "cargo", "go"):
        o_tur = [t for t in testler if t.tur == tur]
        if o_tur and o_tur[-1].basarisiz_mi:
            return o_tur[-1]
    return None


# -- ana giriş noktası ----------------------------------------------------


def degerlendir(
    rapor_metni: str,
    *,
    calisma_dizini: str | Path,
    baslangic: str | None = None,
    git_once: str | None = None,
    git_sonra: str | None = None,
    rapor_dosyasi: str | None = None,
    yapisal: dict | None = None,
) -> Degerlendirme:
    """Ajan raporunu bağımsız kanıtlarla karşılaştırır.

    `calisma_dizini` dışına çıkılmaz; git durumu dışarıdan verilir (saf fonksiyon).
    `rapor_dosyasi` verilirse log + dosya içeriği BİRLİKTE ayrıştırılır.
    `yapisal` (Dalga E) stream-json akış özetidir: verilmezse (varsayılan)
    davranış DALGA D'DEKİ GİBİ AYNEN çalışır.
    """
    d = Degerlendirme()
    d.yapisal = yapisal
    kok = Path(calisma_dizini)

    # -- rapor dosyası (yol güvenliği + boyut sınırı) ----------------------
    metinler: list[str] = []
    if rapor_dosyasi:
        d.rapor_dosyasi = str(rapor_dosyasi)
        cozulmus = guvenli_cöz(rapor_dosyasi, kok)
        if cozulmus is None:
            d.gerekceler.append(
                Gerekce("rapor-dosyasi-guvenlik",
                        "kanitsiz",
                        f"rapor dosyasi calisma dizini disinda: {guard.maskele(rapor_dosyasi)}")
            )
            d.sonuc = KANITSIZ
            d.uyarilar.append("rapor dosyasi guvenli cozumlemede; kanitsiz sayildi")
        elif not cozulmus.is_file():
            d.gerekceler.append(
                Gerekce("rapor-dosyasi", "kanitsiz", "belirtilen rapor dosyasi yok")
            )
            d.sonuc = KANITSIZ
            d.uyarilar.append("rapor dosyasi bulunamadi")
        elif cozulmus.stat().st_size > RAPOR_DOSYASI_TAVAN:
            d.gerekceler.append(
                Gerekce("rapor-dosyasi-tavan", "kanitsiz",
                        f"rapor dosyasi {RAPOR_DOSYASI_TAVAN} bayt asiyor")
            )
            d.sonuc = KANITSIZ
            d.uyarilar.append("rapor dosyasi boyut sinirini asti")
        else:
            try:
                icerik = cozulmus.read_text(encoding="utf-8", errors="replace")
            except OSError as hata:
                icerik = None
                d.gerekceler.append(
                    Gerekce("rapor-dosyasi", "kanitsiz",
                            f"rapor dosyasi okunamadi: {type(hata).__name__}")
                )
                d.sonuc = KANITSIZ
            if icerik is not None:
                metinler.append(icerik)
                d.gerekceler.append(
                    Gerekce("rapor-dosyasi-okundu", "bilgi",
                            f"rapor dosyasi icerigi ayristirmaya katildi ({len(icerik)} karakter)")
                )

    if rapor_metni:
        metinler.append(rapor_metni)
    metin = "\n\n".join(metinler)
    # Ayrıştırılan tüm metinler maskelemeTEN önce toplanır (desenler ham metin
    # üzerinde çalışmalı), ama SAKLANAN her şey maskeli olur.
    baslangic_satir = None
    if baslangic:
        try:
            from datetime import datetime

            baslangic_satir = datetime.fromisoformat(
                baslangic.replace("Z", "+00:00")
            ).timestamp()
        except (TypeError, ValueError):
            baslangic_satir = None

    # -- 1) izin reddi (yalnız SON MESAJ) --------------------------------
    son_mesaj = "\n".join(metin.splitlines()[-SON_MESAJ_SATIR:])
    red = _reddedilme_bul(son_mesaj)
    if red:
        d.sonuc = REDDEDILDI
        d.gerekceler.append(
            Gerekce("izin-reddi-son-mesaj", REDDEDILDI, red)
        )
    belirsiz = [m.group(0) for m in BELIRSIZ_KALIP.finditer(son_mesaj)][:5]
    if belirsiz:
        d.uyarilar.append(
            "son mesajda belirsiz engel ifadesi var, tetiklenmedi: " + ", ".join(belirsiz)
        )

    # -- 2) test beyanları ------------------------------------------------
    d.testler = testleri_ayikla(metin)
    # Dalga E: akıştan GÖZLEMLENEN test sonuçları (beyandan AYRI tutulur).
    d.gozlemlenen_testler = _gozlemlenen_testler(yapisal)

    # -- 3) görsel kanıt (GÖZLEMLENEN) ------------------------------------
    kanit_bolumu = _kanit_bolumu(metin)
    if kanit_bolumu is not None:
        d.gorsel_beyanlar.append("rapor `## Kanıt` bölümü içeriyor (ayrıştırma öncelikli okundu)")
    kaynak = kanit_bolumu if kanit_bolumu is not None else metin
    for yol in _gorsel_yollari(kaynak):
        d.gorseller.append(
            _gorseli_denetle(yol, kok, baslangic_satir)
        )
    # Gerçek bir görsel kanıtı varsa kısa-rapor kuralı geçerli değildir:
    # kanıt zaten gözlemlendi, raporun kısa olması onu geçersiz kılmaz.
    # Dalga E: gözlemlenen TEMİZ test koşusu da aynı ölçüdedir.
    gozlemlenen_var = (
        d.gecerli_gorsel_sayisi > 0 or d.gozlemlenen_temiz_test_sayisi() > 0
    )
    # Kanıt bölümünde görsel satırı "gördüğüm kusur" metnini de beyan olarak saklar.
    if kanit_bolumu is not None:
        for satir in kanit_bolumu.splitlines():
            if SATIR_KANIT_GORSEL.match(satir) or SATIR_KANIT_TEST.match(satir):
                d.beyanlar.append(guard.maskele(satir.strip()[:160]))

    # -- 4) iddialar -------------------------------------------------------
    d.iddialar = _iddialari_bul(metin)
    d.beyanlar.extend(d.iddialar)

    # -- 5) git değişimi (GÖZLEMLENEN) ------------------------------------
    if git_once is not None and git_sonra is not None:
        d.git_degisti = git_once != git_sonra
        d.gerekceler.append(
            Gerekce("git-degisimi", "gözlemlenen" if d.git_degisti else "gözlemlenen-yok",
                    "calisma dizini git deposu; agac/HEAD degisti" if d.git_degisti
                    else "calisma dizini git deposu; agac/HEAD DEGISMEDI")
        )

    # -- sonuç sınıfları (öncelik sırasıyla) ------------------------------
    # 1) red  2) başarısız  3) kanıtsız  4) kanıtlı
    basarisiz = _belirleyici_basarisizlar(d.testler)
    gecmis_basarisiz = [t for t in d.testler if t.basarisiz_mi and t not in basarisiz]
    if gecmis_basarisiz and not basarisiz:
        d.uyarilar.append(
            "onceki/kucuk kosuda basarisizlik anilmis, en buyuk sonuc temiz: "
            + ", ".join(f"{t.tur}: {t.failed or 0} failed" for t in gecmis_basarisiz[:3])
        )
    # Dalga E — YAPISAL RED: izin/onay kalıbı akışta GÖZLEMLENDİ. Metin
    # heuristiği gerekmez: ajanın son mesajı temiz olsa da yakalanır.
    if yapisal and d.sonuc != REDDEDILDI:
        if (
            int(yapisal.get("izin_reddi_sayisi") or 0) > 0
            or any(r.get("red") for r in yapisal.get("arac_sonuclari") or [])
        ):
            d.sonuc = REDDEDILDI
            d.gerekceler.append(
                Gerekce("yapisal-red", REDDEDILDI,
                        "izni reddedilen arac sonucu var; izin reddi sayisi: "
                        f"{yapisal.get('izin_reddi_sayisi') or 0}")
            )
    # Dalga E — GÖZLEMLENEN TEST: akıştaki son `Bash` test koşusu başarısızsa
    # BEYAN ne derse desin `basarisiz` olur (beyan gözlemi ASLA yükseltmez).
    gozlemlenen_bozuk = _gozlemlenen_basarisiz(d.gozlemlenen_testler)
    if d.sonuc != REDDEDILDI:
        if gozlemlenen_bozuk is not None:
            d.sonuc = BASARISIZ
            d.gerekceler.append(
                Gerekce("gozlemlenen-test-basarisiz", BASARISIZ,
                        f"akis son {gozlemlenen_bozuk.tur} kosusu: "
                        f"{gozlemlenen_bozuk.failed or 0} failed/"
                        f"{gozlemlenen_bozuk.error or 0} error")
            )
        elif basarisiz or _traceback_var(son_mesaj):
            d.sonuc = BASARISIZ
            k = ", ".join(
                f"{t.tur}: {t.failed or 0} failed/{t.error or 0} error" for t in basarisiz
            ) or "son bolumde FAILED/Traceback"
            d.gerekceler.append(Gerekce("test-basarisiz", BASARISIZ, k))
        elif len(metin.strip()) < KISA_RAPOR_ESIK and not gozlemlenen_var:
            d.sonuc = KANITSIZ
            d.gerekceler.append(
                Gerekce("kisa-rapor", KANITSIZ,
                        f"rapor {len(metin.strip())} karakter; kanit yok")
            )
        elif d.gorseller and not d.gecerli_gorsel_sayisi:
            d.sonuc = KANITSIZ
            d.gerekceler.append(
                Gerekce("gorsel-gecersiz", KANITSIZ,
                        "; ".join(f"{g.yol}: {g.gerekce}" for g in d.gorseller))
            )
        elif DEGISIM_IDDIASI.search(metin) and d.git_degisti is False:
            # Rapor "dosya yazdım/değiştirdim" diyor ama git ağacı/HEAD
            # DEĞİŞMEMİŞ: iddia gözlemlenebilir biçimde çürütülmüştür.
            d.sonuc = KANITSIZ
            d.gerekceler.append(
                Gerekce("degisim-iddiasi-kanitsiz", KANITSIZ,
                        "rapor dosya degistirdigini soyluyor ama git agaci/HEAD degismedi")
            )
        elif d.iddialar and d.gozlemlenen_kanit_sayi() == 0:
            d.sonuc = KANITSIZ
            d.gerekceler.append(
                Gerekce("iddia-kanitsiz", KANITSIZ,
                        "iddia var, gozlemlenen kanit yok")
            )
        elif d.gozlemlenen_testler:
            # Gözlemlenen (beyan OLMAYAN) kanıt: `iddialar` boş olsa da kanıtlı.
            d.sonuc = KANITLI
            temiz = [t for t in d.gozlemlenen_testler if not t.basarisiz_mi]
            d.gerekceler.append(
                Gerekce("gozlemlenen-akis-kaniti", KANITLI,
                        f"{len(temiz)} gozlemlenen temiz test kosusu: "
                        + ", ".join(f"{t.tur}: {t.passed or 0} passed" for t in temiz[:3]))
            )
        else:
            d.sonuc = KANITLI
            d.gerekceler.append(
                Gerekce("gozlemlenen-kanit", KANITLI,
                        f"{d.gecerli_gorsel_sayisi} gorsel dogrulandi"
                        + (", git degisti" if d.git_degisti else ""))
            )

    d.kanit_durumu = d.sonuc
    d.ozet = d.ozet_metin()
    return d


def _belirleyici_basarisizlar(testler) -> list:
    """`failed/error` iceren sonuclardan yalniz BELIRLEYICI olanlar.

    Raporlar sik sik duzeltmeden ONCEKI durumu anar ("524 passed, 1 failed") ve
    ardindan guncel sonucu verir ("738 passed"). Ayni test turunde en BUYUK
    toplamli (passed+failed+error) sonuc guncel/tam kosu sayilir; yalniz onun
    basarisizligi raporu basarisiz yapar. Kucuk/eski kosulardaki failed uyaridir.
    """
    def toplam(t) -> int:
        return (t.passed or 0) + (t.failed or 0) + (t.error or 0)

    en_buyuk: dict[str, int] = {}
    for t in testler:
        en_buyuk[t.tur] = max(en_buyuk.get(t.tur, 0), toplam(t))
    return [t for t in testler if t.basarisiz_mi and toplam(t) >= en_buyuk[t.tur]]


def _traceback_var(son_mesaj: str) -> bool:
    """Son bölüm `FAILED`/`Traceback` ile bitiyorsa başarısızdır."""
    satirlar = [s.strip() for s in son_mesaj.splitlines() if s.strip()]
    if not satirlar:
        return False
    son = satirlar[-1]
    return bool(re.search(r"\bFAILED\b|\bTraceback\b", son))


def _reddedilme_bul(son_mesaj: str) -> str:
    """Son mesajda birinci şahıs red/engel bildirimi (kod bağlamı hariç)."""
    # Kod bloklarını boşalt: içlerindeki "denied" tetiklemez.
    temiz = re.sub(r"```.*?```", " ", son_mesaj, flags=re.DOTALL)
    for desen in REDDEDILME_KALIPLARI:
        for m in desen.finditer(temiz):
            if _kod_iceriginde_mi(temiz, m.start(), m.end()):
                continue
            return guard.maskele(m.group(0).strip()[:160])
    return ""


def _aday_yollar(yol: str, kok: Path) -> list[str]:
    """Yol adaylarını çözer: verilen yol + sınırlı alt dizin taraması.

    Gerçek raporlar görseli kısa adla (`ozet-masaustu.png`) yazıp dosyayı
    `docs/ekran/` gibi bir alt dizine koyar; yalnız bu durumda ad geçerli bir
    adaya dönüşür. Arama **derinlik 3'e ve 400 dizine sınırlıdır**, sembolik
    bağ dizinlerine girmez ve `.git`'i atlar — `calisma_dizini` dışına çıkamaz.
    """
    adaylar = [yol]
    if Path(yol).is_absolute() or ".." in Path(yol).parts:
        return adaylar
    ad = Path(yol).name
    adaylar.extend(yollar_ara(kok, ad))
    return adaylar


def yollar_ara(kok: Path, ad: str, derinlik: int = 3, en_fazla: int = 400) -> list[str]:
    """`kok` altında `ad` dosyasını bulur; göreli yolları döndürür.

    `derinlik`/`en_fazla` sınırları: raporu yüzlerce dosyalık bir depoda
    okunmaz taramaya yol açmasın. Sembolik bağ dizinlerine GİRİLMEZ.
    """
    import os

    bulunan: list[str] = []
    kok_c = kok.expanduser().resolve()
    if not kok_c.is_dir():
        return bulunan
    for kok_dizin, dizinler, dosyalar in os.walk(kok_c, followlinks=False):
        # Sembolik bağ dizinleri dışarı çıkabilir → hiç girilmez.
        dizinler[:] = [
            d for d in dizinler
            if d != ".git" and not (Path(kok_dizin) / d).is_symlink()
        ]
        if ad in dosyalar:
            try:
                goreli = Path(kok_dizin, ad).resolve().relative_to(kok_c)
            except (ValueError, OSError):
                continue
            bulunan.append(str(goreli))
        if len(bulunan) >= 4:
            break
        if (kok_dizin != kok_c) and kok_dizin[len(str(kok_c)):].count(os.sep) >= derinlik:
            dizinler[:] = []
        if len(bulunan) >= en_fazla:
            break
    return bulunan


def _gorseli_denetle(yol: str, kok: Path, baslangic: float | None) -> GorselKaniti:
    """Bir görsel yolunu GÖZLEMLENEN denetimlerden geçirir."""
    k = GorselKaniti(yol=yol)
    # Kapsama denetimi İLK aday üzerinde yapılır: yol çalışma dizini DIŞINDA
    # ise bu bir KAÇIŞTIR ve aday taraması ASLA denenmez. Dosyanın var olup
    # olmadığı ise "dosya diskte yok" gerekçesiyle ayrıca bildirilir.
    coz = guvenli_cöz(yol, kok)
    if coz is None:
        k.gerekce = "calisma dizini disinda (yol kacisi/sembolik bag reddedildi)"
        return k
    if not coz.is_file():
        # Rapor kısa ad yazmış olabilir: sınırlı arama bir kez denenir.
        for aday in _aday_yollar(yol, kok)[1:]:
            alternatif = guvenli_cöz(aday, kok)
            if alternatif is not None and alternatif.is_file():
                coz = alternatif
                break
    k.cozulmus = str(coz)
    if not coz.is_file():
        k.gerekce = "dosya diskte yok"
        return k
    try:
        boyut = coz.stat().st_size
    except OSError:
        k.gerekce = "dosya istatistigi okunamadi"
        return k
    k.bayt = boyut
    if boyut == 0:
        k.gerekce = "dosya bos (0 bayt)"
        return k
    try:
        with coz.open("rb") as akis:
            bas = akis.read(16)
    except OSError:
        k.gerekce = "dosya okunamadi"
        return k
    gercek = imza_tur(bas)
    beklenen = _beklenen_tur(yol)
    if not gercek:
        k.gerekce = f"imza gecersiz: gercek dosya degil ({beklenen} bekleniyordu)"
        return k
    if beklenen and gercek != beklenen:
        k.gerekce = f"imza uyusmuyor: dosya {gercek}, ad {beklenen} diyor"
        return k
    if baslangic is not None:
        try:
            degisti = coz.stat().st_mtime >= baslangic
        except OSError:
            degisti = None
        k.yeni_mi = degisti
        if degisti is False:
            k.gerekce = f"dosya kosudan once yazilmis (mtime < baslangic)"
            return k
    k.gecerli = True
    k.gerekce = f"gecerli {gercek} ({boyut} bayt" + (
        f", kosudan sonra yazildi" if k.yeni_mi else ""
    ) + ")"
    return k


# -- git durumu (salt okunur, yalnız bu iki komut) -------------------------


def git_ozeti(cwd: str | Path, zaman_asimi: float = 10.0) -> str | None:
    """`git rev-parse HEAD` + `git status --porcelain` özeti; depo değilse `None`.

    Yalnızca SALT-OKUNUR komutlar çalıştırır ve zaman aşımı uygular. Depo
    değilse `None` döner → kanıt kuralı işlemez, "bilinmiyor" sayılır.
    """
    import subprocess

    try:
        kok = Path(cwd)
        kok.resolve()
    except (OSError, ValueError):
        return None
    parcalar: list[str] = []
    for komut in (["git", "rev-parse", "HEAD"], ["git", "status", "--porcelain"]):
        try:
            tamam = subprocess.run(  # noqa: S603 — sabit komut listesi
                komut, cwd=str(kok), capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=zaman_asimi, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if tamam.returncode != 0:
            return None
        parcalar.append((tamam.stdout or "").strip())
    return "\n".join(parcalar)
