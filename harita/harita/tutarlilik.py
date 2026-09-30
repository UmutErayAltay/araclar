"""Vault↔repo tutarlılığı: notun iddiası ile gerçek repo durumu çelişiyor mu?

GİRDİ:
  * vault (salt okunur) — proje notları, durum sözcükleri, `Threads.md`
  * atlas'ın SQLite DB'si (`--atlas-db`, varsayılan `~/.atlas/atlas.db`),
    `mode=ro` ile açılır. atlas paketi İÇE AKTARILMAZ; şema belge olarak
    kabul edilir:
        repos(path PK, name, scanned_at, dirty, unpushed, branch,
              last_commit_at, has_remote)

  * `unpushed` NULL = BİLİNMİYOR. Bu durumda "pushlanmamış" iddiası ASLA
    yapılmaz.

KURALLAR (her bulgu: önem, güven, gerekçe, tek satır öneri):
  1. Not `planlandı`/`planned`/"kod yok" ama repoda ≥1 commit ve son commit
     ≤ eşik gün → UYARI: "durum 'planlandı' ama repoda kod var".
  2. Not `tamam`/`bitti`/`done`/`archived` ama repo `dirty>0` ya da BİLİNEN
     `unpushed>0` → UYARI.
  3. Not "aktif"/"devam" ama son commit `--esik-gun` günden eski → BİLGİ
     (durgun).
  4. Atlas'ta son 7 günde commit'i olan repo HİÇBİR nota eşleşmiyor →
     BİLGİ: "vault'ta karşılığı olmayan aktif repo".
  5. `Threads.md`'de açık (`🟢`/`🟡`) işaretli ve repo adı (backtick) geçen
     konu için eşleşen reponun son commit'i eşik günden eski → BİLGİ (durgun).

EŞLEME (not→repo), öncelik sırasıyla:
  1. frontmatter `repo: <ad>` (yüksek güven)
  2. eşleme dosyası (`~/.harita/repolar.toml` veya `--esleme`), `[eslesme]`
     altında `"not yolu" = "repo adı"` (yüksek güven)
  3. notun ilk 30 satırında backtick içinde geçen ve atlas DB'sinde VAR olan
     bir repo adı (orta güven, çıktıda "(tahmin)")

Bu modül HİÇBİR ŞEYİ DEĞİŞTİRMEZ: yalnızca okur ve öneri metni üretir.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from .parse import frontmatter_ayir, normalize

VARSAYILAN_ATLAS_DB = Path.home() / ".atlas" / "atlas.db"
VARSAYILAN_ESLESME = Path.home() / ".harita" / "repolar.toml"

VARSAYILAN_ESIK_GUN = 30
VARSAYILAN_AKTIF_GUN = 7

# atlas şeması: bu sütunlar bulunmalı. Eksikse net hata verilir.
BEKLENEN_SUTUNLAR = frozenset(
    {"path", "name", "scanned_at", "dirty", "unpushed", "branch",
     "last_commit_at", "has_remote"}
)

# ---------------------------------------------------------------------------
# Durum sözcükleri tablosu (Türkçe/İngilizce, büyük-küçük harf, İ/ı)
# ---------------------------------------------------------------------------

# Notun söylediği durum → normalize (küçük harf, aksan/İ sadeleştirilmiş) sözcük.
DURUM_SOZCUKLERI: dict[str, str] = {}


def _kaydet(grup: str, *sozcukler: str) -> None:
    for s in sozcukler:
        DURUM_SOZCUKLERI[normalize(s)] = grup


# planlı / henüz kod yok
_kaydet("planli", "planlandı", "planlandi", "planned", "plan", "kod yok",
         "henüz kod yok", "henuz kod yok", "fikir", "idea", "taslak", "draft")
# sürüyor / devam
# NOT: gerçek vault'ta Obsidian/Dataview `status:` alanı ÇİFT TIRNAKLI
# ("in-progress") veya serbest metin olarak yazılabiliyor. `normalize` tireyi
# BOŞLUĞA ÇEVİRMEZ; bu yüzden tireli biçimler AÇIKÇA kaydedilir.
_kaydet("aktif", "aktif", "active", "devam", "devam ediyor", "in progress",
         "in-progress", "inprogress", "sürüyor", "suruyor", "çalışılıyor",
         "calisiliyor", "wip", "ongoing", "devam ediyor", "yapım aşamasında",
         "geliştirme aşamasında", "development", "under development")
# bitti / tamam
_kaydet("bitti", "tamam", "tamamlandı", "tamamlandi", "bitti",
         "done", "finished", "complete", "completed", "shipped",
         "archived", "arşiv", "arsiv", "kapalı", "kapali", "kapatıldı",
         "closed", "deprecated", "iptal")

DURUM_GRUPLARI = ("planli", "aktif", "bitti")


def durum_grup(sozcuk: str) -> str | None:
    """Bir durum sözcüğünü `planli`/`aktif`/`bitti` grubuna eşler."""
    return DURUM_SOZCUKLERI.get(normalize(sozcuk))


def durum_metni_ara(metin: str) -> str | None:
    """Bir metinden durum grubunu bulur (`**Durum:**` veya `status:`)."""
    for satir in metin.split("\n"):
        m = re.match(r"^\s*(?:\*\*Durum:\*\*|status:)\s*(.+?)\s*$", satir, re.I)
        if m:
            # Değer birkaç sözcükten oluşabilir; hepsini tek tek dene.
            for parca in re.split(r"[,;|]", m.group(1)):
                grup = durum_grup(parca)
                if grup:
                    return grup
            # Sözcük listesi tutmazsa değerin kendisini dene.
            return durum_grup(m.group(1))
    return None


# ---------------------------------------------------------------------------
# atlas DB okuma
# ---------------------------------------------------------------------------


@dataclass
class Repo:
    """atlas `repos` tablosundan bir satır."""

    path: str
    name: str
    scanned_at: datetime | None
    dirty: int
    unpushed: int | None       # None = BİLİNMİYOR
    branch: str | None
    last_commit_at: datetime | None
    has_remote: bool


@dataclass
class AtlasVerisi:
    """atlas DB'sinin okunmuş hali + tazelik uyarısı."""

    repolar: list[Repo] = field(default_factory=list)
    en_eski_scan: datetime | None = None
    uyari: str | None = None


def _iso(coerce: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(coerce)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def atlas_oku(db_yolu: Path | str) -> AtlasVerisi:
    """atlas DB'sini `mode=ro` ile okur. Şema uyuşmazlığında hata verir."""
    yol = Path(db_yolu).expanduser()
    if not yol.exists():
        raise SystemExit(
            f"atlas veritabanı bulunamadı: {yol}\n"
            "Önce `atlas tara` çalıştırın veya `--atlas-db` ile yol verin."
        )
    baglanti = sqlite3.connect(f"file:{quote(yol.as_posix())}?mode=ro", uri=True)
    try:
        try:
            sutunlar = {r[1] for r in baglanti.execute("PRAGMA table_info(repos)")}
        except sqlite3.OperationalError as exc:
            raise SystemExit(f"atlas DB'si okunamadı: {exc}") from exc
        eksik = BEKLENEN_SUTUNLAR - sutunlar
        if eksik:
            raise SystemExit(
                "atlas şeması beklenenden farklı; eksik sütunlar: "
                + ", ".join(sorted(eksik))
            )
        veri = AtlasVerisi()
        for satir in baglanti.execute(
            "SELECT path, name, scanned_at, dirty, unpushed, branch, "
            "last_commit_at, has_remote FROM repos"
        ):
            scan = _iso(satir[2])
            veri.repolar.append(
                Repo(
                    path=satir[0], name=satir[1], scanned_at=scan,
                    dirty=int(satir[3] or 0), unpushed=satir[4],
                    branch=satir[5], last_commit_at=_iso(satir[6]),
                    has_remote=bool(satir[7]),
                )
            )
        if veri.repolar:
            veri.en_eski_scan = min(r.scanned_at for r in veri.repolar if r.scanned_at)
    finally:
        baglanti.close()
    return veri


def atlas_eski_mi(veri: AtlasVerisi, gun: int = 24, simdi: datetime | None = None) -> bool:
    """`scanned_at` 24 saatten eski mi? (en eski tarama dikkate alınır).

    `simdi` verilmezse gerçek saat kullanılır; testler `--bugun` ile aynı
    referansı geçer (takvim günü UTC gece yarısı olduğundan, gerçek saatle
    karşılaştırmak gün sınırında yanlış "eski" sonucu verirdi).
    """
    if veri.en_eski_scan is None:
        return False
    simdi = simdi or datetime.now(timezone.utc)
    return veri.en_eski_scan < simdi - timedelta(hours=gun)


# ---------------------------------------------------------------------------
# Eşleme dosyası (repolar.toml)
# ---------------------------------------------------------------------------

_ESLESME_KV = re.compile(r'^\s*"(?P<not>[^"]+)"\s*=\s*"(?P<repo>[^"]+)"\s*$')


def eslesme_dosyasi_oku(yol: Path | str) -> dict[str, str]:
    """`[eslesme]` bölümündeki `"not yolu" = "repo adı"` çiftleri.

    `tomllib` stdlib'de (3.11+) var; yine de basit bir ayrıştırıcı kullanılır
    çünkü dosya küçük ve biçimi sabit. Anahtar/ değer sözlüğü de yazılabilir.
    """
    yol = Path(yol).expanduser()
    if not yol.exists():
        return {}
    sozluk: dict[str, str] = {}
    bolumde = False
    for satir in yol.read_text(encoding="utf-8", errors="replace").split("\n"):
        temiz = satir.split("#", 1)[0]
        baslik = re.match(r"^\s*\[(?P<b>[^\]]+)\]\s*$", temiz)
        if baslik:
            bolumde = normalize(baslik.group("b")) == "eslesme"
            continue
        if not bolumde:
            continue
        m = _ESLESME_KV.match(temiz)
        if m:
            sozluk[unicodedata.normalize("NFC", m.group("not")).strip()] = m.group("repo").strip()
    return sozluk


# ---------------------------------------------------------------------------
# Vault notları
# ---------------------------------------------------------------------------


@dataclass
class NotBilgi:
    """Bir proje notunun tutarlılık için gereken özeti."""

    yol: str            # vault'a göreli
    baslik: str
    durum: str | None   # "planli" | "aktif" | "bitti"
    durum_nerede: str   # "satir" | "frontmatter" | ""
    ilk_30_satir: str
    frontmatter: dict[str, object]


def _notlari_tara(vault: Path) -> list[NotBilgi]:
    """Vault'taki tüm `.md` notlarını okur (salt okunur)."""
    notlar: list[NotBilgi] = []
    for yol in sorted(vault.rglob("*.md")):
        if not yol.is_file():
            continue
        parcalar = yol.relative_to(vault).parts
        norm = [normalize(p) for p in parcalar]
        if any(p in ("receipts", ".git", ".obsidian", ".claude", ".agents") for p in norm):
            continue
        if any("000-inbox/dump" in p for p in norm):
            continue
        try:
            ham = yol.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
        except OSError:
            continue
        veri, govde = frontmatter_ayir(ham)
        ilk_30 = "\n".join(ham.split("\n")[:30])
        # `**Durum:**` satırı frontmatter `status:`'tan ÖNCELİKLİDİR.
        durum = durum_metni_ara(govde) or durum_metni_ara(ilk_30)
        if durum is None and "status" in veri:
            durum = durum_grup(str(veri["status"]))
        baslik = str(veri.get("title") or "").strip() or yol.stem
        notlar.append(
            NotBilgi(
                yol=yol.relative_to(vault).as_posix(),
                baslik=baslik, durum=durum, durum_nerede="",
                ilk_30_satir=ilk_30, frontmatter=veri,
            )
        )
    return notlar


# ---------------------------------------------------------------------------
# Eşleme
# ---------------------------------------------------------------------------

# backtick içinde repo adı geçen düğüm notu (ilk 30 satır)
_BACKTICK = re.compile(r"`([^`\n]{1,60})`")


def _bilinen_repo_adlari(atlas: AtlasVerisi) -> dict[str, Repo]:
    return {normalize(r.name): r for r in atlas.repolar}


def eslestir(
    not_: NotBilgi, atlas: AtlasVerisi, eslesme: dict[str, str]
) -> tuple[Repo | None, str, bool]:
    """(repo, yöntem, tahmin_mi). Öncelik: frontmatter > dosya > backtick."""
    bilinen = _bilinen_repo_adlari(atlas)

    # 1) frontmatter `repo: <ad>`
    if "repo" in not_.frontmatter:
        ad = str(not_.frontmatter["repo"]).strip()
        repo = bilinen.get(normalize(ad))
        if repo:
            return repo, "frontmatter", False

    # 2) eşleme dosyası (tam yol veya normalize yol)
    anahtarlar = [not_.yol, unicodedata.normalize("NFC", not_.yol)]
    for a in anahtarlar:
        if a in eslesme:
            repo = bilinen.get(normalize(eslesme[a]))
            if repo:
                return repo, "esleme dosyasi", False

    # 3) ilk 30 satırda backtick içinde bilinen repo adı (orta güven)
    for m in _BACKTICK.finditer(not_.ilk_30_satir):
        repo = bilinen.get(normalize(m.group(1).strip()))
        if repo:
            return repo, "backtick", True
    return None, "", False


# ---------------------------------------------------------------------------
# Kurallar
# ---------------------------------------------------------------------------


@dataclass
class Bulgu:
    """Tek bir tutarsızlık bulgusu."""

    onem: str            # "uyari" | "bilgi"
    guven: str           # "yuksek" | "orta"
    kural: str
    baslik: str          # proje/repo adı (not içeriği DEĞİL)
    gerekce: str
    oneri: str

    def sozluk(self) -> dict[str, str]:
        return {
            "onem": self.onem, "guven": self.guven, "kural": self.kural,
            "baslik": self.baslik, "gerekce": self.gerekce, "oneri": self.oneri,
        }


@dataclass
class EslesmeCifti:
    """Eşleşen bir not↔repo çifti — "ne kontrol edildi" cevabı."""

    not_yolu: str
    repo: str
    yontem: str      # "frontmatter" | "eslesme dosyasi" | "backtick"
    tahmin: bool     # backtick ile bulunduysa True (orta güven)

    @property
    def guven(self) -> str:
        return "orta" if self.tahmin else "yuksek"

    def sozluk(self) -> dict[str, object]:
        return {
            "not": self.not_yolu,
            "repo": self.repo,
            "yontem": self.yontem,
            "tahmin": self.tahmin,
            "guven": self.guven,
        }


@dataclass
class KuralSayaci:
    """Bir kuralın kaç çift üzerinde DEĞERLENDİRİLDİĞİ sayacı."""

    kural: str
    cift: int = 0     # bu kurala girebilecek çift sayısı
    degerlendirilen: int = 0
    bulgu: int = 0

    def sozluk(self) -> dict[str, object]:
        return {
            "kural": self.kural,
            "cift": self.cift,
            "degerlendirilen": self.degerlendirilen,
            "bulgu": self.bulgu,
        }


@dataclass
class Rapor:
    """`tutarlilik` çıktısı."""

    uyarilar: list[Bulgu] = field(default_factory=list)
    bilgiler: list[Bulgu] = field(default_factory=list)
    kontrol_edilemeyenler: list[str] = field(default_factory=list)
    atlas_uyari: str | None = None
    eslesmeyenler: int = 0
    ciftler: list[EslesmeCifti] = field(default_factory=list)
    kural_sayaclari: list[KuralSayaci] = field(default_factory=list)
    eslesme_anahtari: dict[str, int] = field(default_factory=dict)

    @property
    def tumu(self) -> list[Bulgu]:
        return self.uyarilar + self.bilgiler

    @property
    def cift_guven_sayisi(self) -> dict[str, int]:
        sayac = {"yuksek": 0, "orta": 0}
        for c in self.ciftler:
            sayac[c.guven] += 1
        return sayac

    def kontrol_et_metni(self) -> str:
        """"Kontrol edilenler" bloğu — 0 uyarının ne anlama geldiğini söyler."""
        guven = self.cift_guven_sayisi
        yontem = self.eslesme_anahtari
        satirlar = [
            f"Eşleşen not↔repo çifti: {len(self.ciftler)} "
            f"(yüksek güven: {guven['yuksek']}, orta güven/tahmin: {guven['orta']})",
            "  kaynak: "
            + ", ".join(f"{ad}={adet}" for ad, adet in sorted(yontem.items()))
            if yontem
            else "  kaynak: (eşleşme yok)",
            f"Durum sözcüğü bulunan not: {len(self.ciftler)} eşleşti, "
            f"{self.eslesmeyenler} not eşleşmedi (bulgu üretmez)",
            f"Çalıştırılan kural: {len(self.kural_sayaclari)}",
        ]
        for k in self.kural_sayaclari:
            satirlar.append(
                f"  - {k.kural}: {k.degerlendirilen}/{k.cift} çift üzerinde "
                f"değerlendirildi, {k.bulgu} bulgu"
            )
        return "\n".join(satirlar)

    def sozluk(self) -> dict[str, object]:
        return {
            "uyarilar": [b.sozluk() for b in self.uyarilar],
            "bilgiler": [b.sozluk() for b in self.bilgiler],
            "kontrol_edilemeyenler": sorted(self.kontrol_edilemeyenler),
            "atlas_uyari": self.atlas_uyari,
            "kontrol_edilenler": {
                "cift_sayisi": len(self.ciftler),
                "guven": self.cift_guven_sayisi,
                "eslesme_yontemi": self.eslesme_anahtari,
                "eslesmeyen_not": self.eslesmeyenler,
                "ciftler": [c.sozluk() for c in self.ciftler],
                "kurallar": [k.sozluk() for k in self.kural_sayaclari],
            },
        }


def vault_adi_girisi(vault: Path) -> str:
    """Vault'un kendi adı.

    Kural 4, vault'un kendi git deposunu "vault'ta karşılığı yok" diye
    bildirmemesi için burada karşılaştırılır. atlas, kök dizini taradığı
    için vault'u da `Mt3Ui55OS` adıyla kaydeder; bu bir PROJE değildir.
    """
    return Path(vault).name


def vaultta_gecen_repo_adlari(vault: Path, atlas: AtlasVerisi) -> set[str]:
    """Vault'un HERHANGİ bir notunda adı geçen repo adları (normalize).

    Kural 4'ün yanlış pozitiflerini keser: repo vault'ta bir yerde (günlük,
    Last-Session, kavramsal not) anılıyorsa "vault'ta karşılığı yok"
    denemez — en kötü haliyle notu eksiktir.
    """
    bulunan: set[str] = set()
    for yol in sorted(Path(vault).rglob("*.md")):
        if not yol.is_file():
            continue
        parcalar = [normalize(p) for p in yol.relative_to(vault).parts]
        if any(p in ("receipts", ".git", ".obsidian", ".claude", ".agents") for p in parcalar):
            continue
        try:
            ham = yol.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        for m in _BACKTICK.finditer(ham):
            ad = normalize(m.group(1).strip())
            if ad in _bilinen_repo_adlari(atlas):
                bulunan.add(ad)
        # Backtick'sız düz ad geçişi de sayılır (örn. "atlas projesi").
        for repo in atlas.repolar:
            ad = normalize(repo.name)
            if len(ad) >= 4 and re.search(rf"\b{re.escape(ad)}\b", normalize(ham)):
                bulunan.add(ad)
    return bulunan


def _gun_once(tarih: datetime | None, gun: int, bugun: date) -> bool:
    if tarih is None:
        return False
    esik = datetime.combine(bugun - timedelta(days=gun), datetime.min.time(),
                            tzinfo=timezone.utc)
    return tarih < esik


def _commit_var(repo: Repo) -> bool:
    return repo.last_commit_at is not None


def _pushlanmamis(repo: Repo) -> bool | None:
    """`unpushed > 0` mi? `unpushed` NULL ise None (= bilinmiyor, iddia yok)."""
    if repo.unpushed is None:
        return None
    return repo.unpushed > 0


def _KURALLAR_SIRASI() -> list[KuralSayaci]:
    """Kural sayaçları — çıktıda SABİT sırada görünür."""
    return [
        KuralSayaci("planli-ama-kod-var"),
        KuralSayaci("bitti-ama-dirty"),
        KuralSayaci("aktif-ama-durgun"),
        KuralSayaci("vaultsuz-aktif-repo"),
        KuralSayaci("konu-aktif-ama-repo-durgun"),
    ]


def bulgular_uret(
    vault: Path,
    atlas: AtlasVerisi,
    eslesme: dict[str, str] | None = None,
    esik_gun: int = VARSAYILAN_ESIK_GUN,
    aktif_gun: int = VARSAYILAN_AKTIF_GUN,
    bugun: date | None = None,
) -> Rapor:
    """Tüm kuralları çalıştırır, bulguları üretir. HİÇBİR ŞEYİ DEĞİŞTİRMEZ."""
    bugun = bugun or date.today()
    eslesme = eslesme or {}
    rapor = Rapor()
    # `scanned_at` UTC ISO'dur; referansı `--bugun` gününün UTC gece yarısı al.
    simdi = datetime.combine(bugun, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
    if atlas_eski_mi(atlas, simdi=simdi):
        rapor.atlas_uyari = "atlas verisi eski (24 saatten fazla) — kararlar güncel olmayabilir"

    notlar = _notlari_tara(Path(vault))
    eslesilen_repo_adlari: set[str] = set()
    eslesilen_repo_yollari: set[str] = set()
    sayaclar = {k.kural: k for k in _KURALLAR_SIRASI()}

    for not_ in notlar:
        if not_.durum is None:
            continue   # durum sözcüğü yoksa bu not bir kural tetiklemez
        repo, yontem, tahmin = eslestir(not_, atlas, eslesme)
        if repo is None:
            # Not bir repo'ya eşleşmedi: BULGU ÜRETMEZ (yalnız sayılır).
            rapor.eslesmeyenler += 1
            continue
        eslesilen_repo_adlari.add(normalize(repo.name))
        eslesilen_repo_yollari.add(repo.path)
        guven = "orta" if tahmin else "yuksek"
        etiket = " (tahmin)" if tahmin else ""
        rapor.ciftler.append(EslesmeCifti(not_.yol, repo.name, yontem, tahmin))
        rapor.eslesme_anahtari[yontem] = rapor.eslesme_anahtari.get(yontem, 0) + 1

        # Kurallar 1-3 yalnız DURUM sözcüğüne bakar; durumu olan her eşleşmiş
        # çift bu üç kuralın adaydır. Aday sayısı = değerlendirilen sayısı.
        if not_.durum == "planli":
            sayaclar["planli-ama-kod-var"].cift += 1
        elif not_.durum == "bitti":
            sayaclar["bitti-ama-dirty"].cift += 1
        elif not_.durum == "aktif":
            sayaclar["aktif-ama-durgun"].cift += 1

        # Kural 1: "planlandı" ama repoda kod var.
        # `cift` = kurala GİREBİLECEK çift sayısı (durum sözcüğü eşleşmesi),
        # `degerlendirilen` = gerçekten koşul denenen çift sayısı. Böylece
        # "kaç çift üzerinde çalıştı" sorusu BOŞ payda vermez.
        if not_.durum == "planli":
            sayaclar["planli-ama-kod-var"].degerlendirilen += 1
        if not_.durum == "planli" and _commit_var(repo) and not _gun_once(repo.last_commit_at, esik_gun, bugun):
            sayaclar["planli-ama-kod-var"].bulgu += 1
            rapor.uyarilar.append(
                Bulgu(
                    onem="uyari", guven=guven, kural="planli-ama-kod-var",
                    baslik=repo.name + etiket,
                    gerekce=f"not durumu 'planlandı' diyor ama repoda {repo.last_commit_at.date()} tarihli commit var",
                    oneri="notu güncelle: durum artık 'aktif'",
                )
            )

        # Kural 2: "bitti" ama repo kirli / pushlanmamış.
        if not_.durum == "bitti":
            sayaclar["bitti-ama-dirty"].degerlendirilen += 1
        if not_.durum == "bitti":
            push = _pushlanmamis(repo)
            if repo.dirty > 0 or push is True:
                sayaclar["bitti-ama-dirty"].bulgu += 1
                parcalar = []
                if repo.dirty > 0:
                    parcalar.append(f"{repo.dirty} değiştirilmemiş dosya")
                if push is True:
                    parcalar.append(f"{repo.unpushed} pushlanmamış commit")
                rapor.uyarilar.append(
                    Bulgu(
                        onem="uyari", guven=guven, kural="bitti-ama-dirty",
                        baslik=repo.name + etiket,
                        gerekce="not 'bitti' diyor ama repoda " + " ve ".join(parcalar),
                        oneri="değişiklikleri commit/push et veya notu 'aktif'e çek",
                    )
                )

        # Kural 3: "aktif" ama son commit eski.
        if not_.durum == "aktif":
            sayaclar["aktif-ama-durgun"].degerlendirilen += 1
        if not_.durum == "aktif" and _gun_once(repo.last_commit_at, esik_gun, bugun):
            sayaclar["aktif-ama-durgun"].bulgu += 1
            rapor.bilgiler.append(
                Bulgu(
                    onem="bilgi", guven=guven, kural="aktif-ama-durgun",
                    baslik=repo.name + etiket,
                    gerekce=f"not 'aktif' diyor ama son commit {esik_gun} günden eski",
                    oneri="projeyi sürdür ya da notu 'bitti'/'planlandı' yap",
                )
            )

    # Kural 4: son 7 günde commit'i olan ama HİÇBİR nota eşleşmeyen repo.
    #
    # YANLIŞ POZİTİF KORUMASI: vault'un KENDİSİ bir git reposudur ve
    # `Mt3Ui55OS` adıyla taranır; vault'a "bu repo için not aç" önermesi
    # anlamsızdır. Aynı biçimde UZAK (remote'suz) repolar gerçek bir
    # projeyi temsil etmeyebilir. Bu yüzden yalnız `has_remote` OLAN
    # repolar bildirilir; vault kendisi `vault_adi` ile eşleşirse
    # dışlanır.
    aktif_esik = datetime.combine(
        bugun - timedelta(days=aktif_gun), datetime.min.time(), tzinfo=timezone.utc
    )
    vault_adi = normalize(vault_adi_girisi(vault))
    # Vault'ta ADI GEÇEN her repo: eşleşmese bile artık "karşılığı yok"
    # sayılmaz. `anlat` yalnız günlükte geçse de vault onu BİLİYOR; "not
    # aç" önermesi yerine "notunu güncelle" denmelidir.
    bahsedilenler = vaultta_gecen_repo_adlari(vault, atlas)
    for repo in atlas.repolar:
        if normalize(repo.name) in eslesilen_repo_adlari:
            continue
        if repo.path in eslesilen_repo_yollari:
            continue
        # Kural 4 bir "aday" listesidir: aşağıdaki eleme adımlarının
        # HEPSİ sayacı düşürür, böylece "kaç repo değerlendirildi" görünür.
        sayaclar["vaultsuz-aktif-repo"].cift += 1
        if normalize(repo.name) == vault_adi:
            continue          # vault'un kendisi: proje DEĞİLDİR
        if normalize(repo.name) in bahsedilenler:
            continue          # vault'ta adı geçiyor: karşılığı VAR
        if not repo.has_remote:
            continue          # remote yok: paylaşılan/proje deposu sayılmaz
        sayaclar["vaultsuz-aktif-repo"].degerlendirilen += 1
        if repo.last_commit_at is not None and repo.last_commit_at >= aktif_esik:
            sayaclar["vaultsuz-aktif-repo"].bulgu += 1
            rapor.bilgiler.append(
                Bulgu(
                    onem="bilgi", guven="yuksek", kural="vaultsuz-aktif-repo",
                    baslik=repo.name,
                    gerekce=f"son 7 günde commit var ({repo.last_commit_at.date()}) ama vault'ta karşılığı yok",
                    oneri="vault'ta bu repo için bir proje notu aç",
                )
            )

    # Kural 5: Threads.md'de açık konu, eşleşen repo durgun.
    konu_bulgulari, konu_degerlendirilen = _konu_bulgulari(
        Path(vault), atlas, eslesme, esik_gun, bugun, sayaci=sayaclar["konu-aktif-ama-repo-durgun"]
    )
    rapor.bilgiler.extend(konu_bulgulari)
    sayaclar["konu-aktif-ama-repo-durgun"].degerlendirilen = konu_degerlendirilen
    sayaclar["konu-aktif-ama-repo-durgun"].bulgu = len(konu_bulgulari)
    rapor.kural_sayaclari = list(sayaclar.values())
    return rapor


# --- Kural 5: Threads.md ---------------------------------------------------

_THREAD_BASLIK = re.compile(r"^###\s+Thread:\s*(.+)$", re.M)
_STATUS_SATIR = re.compile(r"^\*\*Status:\*\*\s*(.+)$", re.M)
# Açık işaretleri
_ACIK_ISARET = re.compile(r"[🟢🟡]")
# Konu adı içinde geçen backtick'li repo adı
_KONU_BACKTICK = re.compile(r"`([^`\n]{1,60})`")

# `Threads.md` "Active Threads" bölümünü bul
_THREAD_DOSYA = "Threads.md"


def _bolum_adi(baslik: str) -> str:
    """Başlığın normalize edilmiş adı (Markdown `##` işaretleri atılmış)."""
    return normalize(re.sub(r"^#+\s*", "", baslik))


def _konu_bulgulari(
    vault: Path,
    atlas: AtlasVerisi,
    eslesme: dict[str, str],
    esik_gun: int,
    bugun: date,
    sayaci: KuralSayaci | None = None,
) -> tuple[list[Bulgu], int]:
    """`Threads.md`'de açık işaretli ve durgun reponun geçtiği konular.

    Döner: (bulgular, değerlendirilen_konu_sayısı). `sayaci` verilirse
    kural 4'ün "aday" sayacı da burada artırılır (aşama elemesi görünür olsun).
    """
    from .ozet import _bul  # ada göre bul (emoji klasör/NFC)

    yol = _bul(vault, _THREAD_DOSYA)
    if yol is None:
        return [], 0
    ham = yol.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    bilinen = _bilinen_repo_adlari(atlas)

    # Yalnız "Active Threads" bölümü.
    basliklar = list(re.finditer(r"^##\s+.*$", ham, re.M))
    bolum = ""
    for i, m in enumerate(basliklar):
        if _bolum_adi(m.group(0)).startswith("active threads"):
            bitis = basliklar[i + 1].start() if i + 1 < len(basliklar) else len(ham)
            bolum = ham[m.start() : bitis]
            break
    if not bolum:
        return [], 0

    bulgular: list[Bulgu] = []
    degerlendirilen = 0
    eslesmeler = list(_THREAD_BASLIK.finditer(bolum))
    for i, eslesme in enumerate(eslesmeler):
        if sayaci is not None:
            sayaci.cift += 1
        baslik = eslesme.group(1)
        bitis = eslesmeler[i + 1].start() if i + 1 < len(eslesmeler) else len(bolum)
        govde = bolum[eslesme.start() : bitis]
        # Açık işareti: başlıkta veya gövdede 🟢/🟡.
        if not _ACIK_ISARET.search(baslik) and not _ACIK_ISARET.search(govde):
            continue
        # Başlıkta veya gövdede backtick içinde geçen repo adı.
        repo = None
        for m in list(_KONU_BACKTICK.finditer(baslik)) + list(_KONU_BACKTICK.finditer(govde)):
            aday = bilinen.get(normalize(m.group(1).strip()))
            if aday:
                repo = aday
                break
        if repo is None:
            continue
        degerlendirilen += 1
        if _gun_once(repo.last_commit_at, esik_gun, bugun):
            bulgular.append(
                Bulgu(
                    onem="bilgi", guven="orta", kural="konu-aktif-ama-repo-durgun",
                    baslik=repo.name,
                    gerekce=f"Threads'ta açık konu ama reponun son commit'i {esik_gun} günden eski",
                    oneri="konuyu kapat ya da repoyu sürdür",
                )
            )
    return bulgular, degerlendirilen
