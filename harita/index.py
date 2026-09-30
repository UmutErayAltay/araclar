"""SQLite indeksi: notlar, linkler, etiketler, takma adlar, chunks.

Vault'a hiçbir yazma yapılmaz; indeks dosyası `--db` ile verilen yolda durur.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from . import ara as ara_modulu
from . import parse as ayristirici

# Varsayılan olarak taranmayan klasör/dosya adları (vault köküne göreli).
VARSAYILAN_HARIC_TUTULANLAR: tuple[str, ...] = (
    ".obsidian",
    "receipts",
    ".git",
    "📥 000-Inbox/Dump",
    ".claude",
    ".agents",
    "node_modules",
)

VARSAYILAN_PARCA_BOYUTU = 800

SEKIL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY,
    yol        TEXT NOT NULL UNIQUE,
    baslik     TEXT NOT NULL,
    mtime      REAL NOT NULL,
    karakter   INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS links (
    kaynak_id   INTEGER NOT NULL,
    hedef_metin TEXT NOT NULL,
    hedef_id    INTEGER,
    tur         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tags (
    not_id  INTEGER NOT NULL,
    etiket  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS aliases (
    not_id INTEGER NOT NULL,
    alias  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    not_id INTEGER NOT NULL,
    sira   INTEGER NOT NULL,
    metin  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_links_hedef  ON links(hedef_id);
CREATE INDEX IF NOT EXISTS ix_links_kaynak ON links(kaynak_id);
CREATE INDEX IF NOT EXISTS ix_tags_etiket  ON tags(etiket);
CREATE INDEX IF NOT EXISTS ix_chunks_not   ON chunks(not_id, sira);
"""

# Dalga D: BM25 arama indeksi. `chunks` zaten gizli satırlardan arındırılmıştır;
# arama gövde metnini YALNIZCA buradan okur, ham dosyayı ASLA açmaz.
ARA_SEKIL = """
CREATE TABLE IF NOT EXISTS ara_belge (
    not_id  INTEGER PRIMARY KEY,
    uzunluk INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS ara_terim (
    terim  TEXT NOT NULL,
    not_id INTEGER NOT NULL,
    alan   TEXT NOT NULL,
    tf     INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ara_terim    ON ara_terim(terim);
CREATE INDEX IF NOT EXISTS ix_ara_terim_not ON ara_terim(not_id);
CREATE TABLE IF NOT EXISTS ara_meta (
    anahtar TEXT PRIMARY KEY,
    deger   TEXT
);
"""


@dataclass
class IndeksOzeti:
    """`harita indeksle` çıktısı için sayaçlar."""

    notlar: int = 0
    linkler: int = 0
    kirik_linkler: int = 0
    etiketler: int = 0
    parcalar: int = 0
    suzulmus_satir: int = 0
    arama_terim: int = 0
    arama_belge: int = 0

    def ozet_metni(self) -> str:
        return (
            f"Not: {self.notlar}  |  Link: {self.linkler}  |  "
            f"Kırık link: {self.kirik_linkler}  |  Etiket: {self.etiketler}  |  "
            f"Parça: {self.parcalar}  |  Süzülen gizli satır: {self.suzulmus_satir}"
        )


def varsayilan_db() -> Path:
    """`HARITA_DB` ortam değişkeni, yoksa `~/.harita/harita.db`."""
    ortam = os.environ.get("HARITA_DB")
    if ortam:
        return Path(ortam).expanduser()
    return Path.home() / ".harita" / "harita.db"


def baglan(db_yolu: Path | str) -> sqlite3.Connection:
    yol = Path(db_yolu).expanduser()
    yol.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(yol)


def baglan_salt_okunur(db_yolu: Path | str) -> sqlite3.Connection:
    """`mode=ro` ile açar: yazma denemeleri `sqlite3.OperationalError` verir.

    Web sunucusu yalnızca bu yolu kullanır; indeks DB'si buradan değiştirilemez.
    """
    yol = Path(db_yolu).expanduser()
    return sqlite3.connect(f"file:{quote(yol.as_posix())}?mode=ro", uri=True)


def sema_olustur(baglanti: sqlite3.Connection) -> None:
    baglanti.executescript(SEKIL)
    baglanti.executescript(ARA_SEKIL)
    baglanti.commit()


def _goreli_yol(kok: Path, yol: Path) -> str:
    return yol.relative_to(kok).as_posix()


def harici_tutulmus(yol: Path, kok: Path, haric: tuple[str, ...]) -> bool:
    """Yol, hariç tutulan listede mi?

    Kural, yolun bileşenleri içinde KEYFİ bir ardışık dizi olarak geçiyorsa tutulur.
    Böylece tek bileşenli kurallar (`.git`, `node_modules`) ağacın HİÇBİR
    derinliğinde eşleşir, çok bileşenli kurallar (`📥 000-Inbox/Dump`) tam
    diziyi arar.
    """
    try:
        parcalar = yol.relative_to(kok).parts
    except ValueError:
        return False
    for kural in haric:
        kural_parcalar = Path(kural).parts
        for bas in range(len(parcalar) - len(kural_parcalar) + 1):
            if parcalar[bas : bas + len(kural_parcalar)] == kural_parcalar:
                return True
    return False


def notlari_tara(
    kok: Path, haric: tuple[str, ...] = VARSAYILAN_HARIC_TUTULANLAR
) -> list[tuple[Path, Path]]:
    """(mutlak yol, vault'a göreli yol) çiftleri — sıralı ve deterministik."""
    kok = Path(kok)
    bulunan: list[tuple[Path, Path]] = []
    for yol in kok.rglob("*.md"):
        if not yol.is_file():
            continue
        if harici_tutulmus(yol, kok, haric):
            continue
        bulunan.append((yol, yol.relative_to(kok)))
    bulunan.sort(key=lambda c: (c[1].as_posix(), c[0].name))
    return bulunan


# ---------------------------------------------------------------------------
# Bağlantı çözümleme
# ---------------------------------------------------------------------------


@dataclass
class Kayit:
    """Bağlantı çözümlemesi için bir notun kimlik kartı."""

    id: int
    yol: Path
    anahtarlar: list[tuple[str, str]]  # (öncelik, normalize anahtar)


def _sirala(aday: tuple[str, Kayit]) -> tuple[int, int, str]:
    return (aday[0], len(aday[1].yol.parts), aday[1].yol.as_posix())


def cozucu_kur(kayitlar: list[Kayit]) -> dict[str, list[Kayit]]:
    """normalize anahtar → aday notlar.

    Aynı anahtara düşen birden çok not varsa en kısa yol kazanır; eşit yolda
    alfabetik sıra kararı verir (deterministik).
    """
    cozucu: dict[str, list[tuple[str, Kayit]]] = {}
    for kayit in kayitlar:
        for oncelik, anahtar in kayit.anahtarlar:
            if anahtar:
                cozucu.setdefault(anahtar, []).append((oncelik, kayit))
    return {anahtar: [k for _, k in sorted(adaylar, key=_sirala)] for anahtar, adaylar in cozucu.items()}


def _son_parca(yol: str) -> str:
    return Path(yol.replace("\\", "/")).name


def linki_coz(hedef_metin: str, cozucu: dict[str, list[Kayit]]) -> Kayit | None:
    """Obsidian mantığı: (1) dosya adı, (2) frontmatter `title`, (3) takma ad.

    Arama sırası: önce dosya adı (yolsuz hedefte tüm metin, yol biçimli
    hedefte yalnızca yolun SON PARÇASI), sonra tam metin → başlık/takma ad.

    Yedek arama (2. adım) yol biçimli bağlantılarda KULLANILMAZ: aksi halde
    `[[klasör/not]]`, ön eki yanlış yazılmış bir notu yanlışlıkla çözerdi.
    """
    hedef_metin = hedef_metin.strip()
    if not hedef_metin:
        return None

    yol_bicimli = "/" in hedef_metin or "\\" in hedef_metin
    adaylar = cozucu.get(ayristirici.normalize(Path(_son_parca(hedef_metin)).stem))
    if adaylar:
        return adaylar[0]
    if yol_bicimli:
        return None
    adaylar = cozucu.get(ayristirici.normalize(hedef_metin))
    return adaylar[0] if adaylar else None


# ---------------------------------------------------------------------------
# İndeksleme
# ---------------------------------------------------------------------------


def indeksle(
    vault: Path | str,
    db_yolu: Path | str | None = None,
    haric: tuple[str, ...] = VARSAYILAN_HARIC_TUTULANLAR,
    parca_boyutu: int = VARSAYILAN_PARCA_BOYUTU,
    baglanti: sqlite3.Connection | None = None,
) -> IndeksOzeti:
    """Vault'u (yeniden) indeksler. Temiz indeks: silinen notlar DB'den gider."""
    vault = Path(vault).expanduser().resolve()
    db_yolu = Path(db_yolu).expanduser() if db_yolu is not None else varsayilan_db()

    sahiplenildi = baglanti is None
    baglanti = baglanti or baglan(db_yolu)
    try:
        sema_olustur(baglanti)
        # Tam yeniden indeksleme: önceki turdan kalan hiçbir satır kalmaz.
        for tablo in ("links", "tags", "aliases", "chunks", "notes"):
            baglanti.execute(f"DELETE FROM {tablo}")
        for tablo in ("ara_terim", "ara_belge", "ara_meta"):
            baglanti.execute(f"DELETE FROM {tablo}")

        ozet = IndeksOzeti()
        for _, goreli in notlari_tara(vault, haric):
            not_ = ayristirici.not_ayristir(vault / goreli, vault)
            imleç = baglanti.execute(
                "INSERT INTO notes (yol, baslik, mtime, karakter) VALUES (?, ?, ?, ?)",
                (goreli.as_posix(), not_.baslik, not_.mtime, not_.karakter),
            )
            not_id = int(imleç.lastrowid or 0)
            ozet.notlar += 1
            ozet.parcalar += _chunks_ekle(baglanti, not_id, not_.govde, parca_boyutu)
            for etiket in not_.etiketler:
                baglanti.execute("INSERT INTO tags (not_id, etiket) VALUES (?, ?)", (not_id, etiket))
            for takma in not_.takma_adlar:
                baglanti.execute("INSERT INTO aliases (not_id, alias) VALUES (?, ?)", (not_id, takma))
            for hedef, tur in not_.linkler:
                baglanti.execute(
                    "INSERT INTO links (kaynak_id, hedef_metin, hedef_id, tur) VALUES (?, ?, NULL, ?)",
                    (not_id, hedef, tur),
                )
            ozet.suzulmus_satir += not_.suzulmus_satir
            # Arama terimleri: gövde `chunks`'tan okunur (gizli satırlar
            # `not_ayristir` içinde zaten süzüldü).
            ozet.arama_terim += _ara_terim_ekle(baglanti, not_id, not_, goreli)

        linkleri_coz(baglanti)
        _ara_meta_yaz(baglanti)
        baglanti.commit()
        ozet.linkler = baglanti.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        ozet.kirik_linkler = baglanti.execute(
            "SELECT COUNT(*) FROM links WHERE hedef_id IS NULL"
        ).fetchone()[0]
        ozet.etiketler = baglanti.execute(
            "SELECT COUNT(DISTINCT etiket) FROM tags"
        ).fetchone()[0]
        ozet.arama_belge = baglanti.execute("SELECT COUNT(*) FROM ara_belge").fetchone()[0]
        return ozet
    finally:
        if sahiplenildi:
            baglanti.close()


def _chunks_ekle(baglanti: sqlite3.Connection, not_id: int, govde: str, boyut: int) -> int:
    parcalar = ayristirici.parca_bol(govde, boyut)
    for sira, metin in enumerate(parcalar):
        baglanti.execute(
            "INSERT INTO chunks (not_id, sira, metin) VALUES (?, ?, ?)", (not_id, sira, metin)
        )
    return len(parcalar)


# ---------------------------------------------------------------------------
# Dalga D: arama indeksi
# ---------------------------------------------------------------------------


def _alan_terimleri(metin: str) -> list[str]:
    return ara_modulu.terimler(metin)


def _ara_terim_ekle(baglanti: sqlite3.Connection, not_id: int, not_: object, goreli: Path) -> int:
    """Bir notun alan alan terim sayılarını `ara_terim`'e yazar.

    Alanlar ve ağırlıkları `ara.ALAN_AGIRLIK`'tadır: başlık ×4, alias ×4,
    etiket ×3, yol ×1.5, gövde ×1. Gövde metni `chunks`'tan okunur; gizli
    satırlar `not_ayristir` sırasında süzüldüğü için buraya hiç girmez.
    """
    govde = "\n".join(
        m for (m,) in baglanti.execute(
            "SELECT metin FROM chunks WHERE not_id = ? ORDER BY sira", (not_id,)
        )
    )
    alanlar: list[tuple[str, str]] = [
        ("baslik", not_.baslik),
        ("yol", goreli.as_posix().replace("/", " ")),
        ("govde", govde),
    ]
    alanlar += [("alias", a) for a in not_.takma_adlar]
    alanlar += [("etiket", e) for e in not_.etiketler]

    sayac = 0
    for alan, metin in alanlar:
        tf_sayaci: dict[str, int] = {}
        for terim in _alan_terimleri(metin):
            tf_sayaci[terim] = tf_sayaci.get(terim, 0) + 1
        for terim, tf in tf_sayaci.items():
            baglanti.execute(
                "INSERT INTO ara_terim (terim, not_id, alan, tf) VALUES (?, ?, ?, ?)",
                (terim, not_id, alan, tf),
            )
            sayac += 1

    # Belge uzunluğu = terimlerin TOPLAM sayısı (tekrar sayılı; BM25 `b`
    # cezası uzun belgeleri kısa belgelere göre kısar).
    uzunluk = baglanti.execute(
        "SELECT COALESCE(SUM(tf), 0) FROM ara_terim WHERE not_id = ?", (not_id,)
    ).fetchone()[0]
    baglanti.execute(
        "INSERT INTO ara_belge (not_id, uzunluk) VALUES (?, ?)", (not_id, int(uzunluk))
    )
    return sayac


def _ara_meta_yaz(baglanti: sqlite3.Connection) -> None:
    """Belge sayısı, ortalama uzunluk ve tokenleştirici sürümünü yazar."""
    belge_sayisi, toplam = baglanti.execute(
        "SELECT COUNT(*), COALESCE(SUM(uzunluk), 0) FROM ara_belge"
    ).fetchone()
    ort = (toplam / belge_sayisi) if belge_sayisi else 1.0
    for anahtar, deger in (
        ("surum", ara_modulu.TOKENLEŞTIRICI_SURUM),
        ("belge_sayisi", str(int(belge_sayisi))),
        ("ortalama_uzunluk", f"{ort:.4f}"),
    ):
        baglanti.execute(
            "INSERT INTO ara_meta (anahtar, deger) VALUES (?, ?) "
            "ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
            (anahtar, deger),
        )


def linkleri_coz(baglanti: sqlite3.Connection) -> None:
    """`links.hedef_id` alanını doldurur (NULL = kırık link)."""
    kayitlar: list[Kayit] = []
    kimlik: dict[int, Kayit] = {}
    for not_id, yol, baslik in baglanti.execute("SELECT id, yol, baslik FROM notes ORDER BY id"):
        kayit = Kayit(
            id=int(not_id),
            yol=Path(yol),
            anahtarlar=[
                ("ad", ayristirici.normalize(Path(yol).stem)),
                ("baslik", ayristirici.normalize(baslik)),
            ],
        )
        kayitlar.append(kayit)
        kimlik[kayit.id] = kayit
    for not_id, alias in baglanti.execute("SELECT not_id, alias FROM aliases ORDER BY not_id, alias"):
        kimlik[int(not_id)].anahtarlar.append(("takma_ad", ayristirici.normalize(alias)))
    cozucu = cozucu_kur(kayitlar)

    for link_id, hedef in baglanti.execute("SELECT rowid, hedef_metin FROM links").fetchall():
        kayit = linki_coz(hedef, cozucu)
        baglanti.execute("UPDATE links SET hedef_id = ? WHERE rowid = ?", (kayit.id if kayit else None, link_id))


# ---------------------------------------------------------------------------
# Sorgular
# ---------------------------------------------------------------------------


def kirik_linkler(baglanti: sqlite3.Connection) -> list[tuple[str, str, str]]:
    """(kaynak yol, kaynak başlık, hedef metin) — kırık linkler."""
    return [
        (yol, baslik, hedef)
        for yol, baslik, hedef in baglanti.execute(
            """
            SELECT k.yol, k.baslik, l.hedef_metin
            FROM links l JOIN notes k ON k.id = l.kaynak_id
            WHERE l.hedef_id IS NULL
            ORDER BY k.yol, l.rowid
            """
        )
    ]


def yetim_notlar(baglanti: sqlite3.Connection) -> list[tuple[str, str]]:
    """Kimse link vermemiş VE link vermemiş notlar: (yol, başlık)."""
    return [
        (yol, baslik)
        for yol, baslik in baglanti.execute(
            """
            SELECT n.yol, n.baslik
            FROM notes n
            WHERE NOT EXISTS (SELECT 1 FROM links g WHERE g.hedef_id = n.id)
              AND NOT EXISTS (SELECT 1 FROM links c WHERE c.kaynak_id = n.id)
            ORDER BY n.yol
            """
        )
    ]


# "Yok sayılabilir" iki YAPISAL kuraldır (Dalga B.1 kararı Q2/Q3):
#   1) Kökteki tek-bileşenli HER `.md` dosyası. Sabit isim listesi
#      (`README`, `CLAUDE`…) kalktı: gerçek vault'ta `1.md`,
#      `AUDIT_REPORT.md` gibi kök notları gerçek yetim sayıyordu.
#   2) `daily/` ile başlayan yol (`daily/v3/` dahil) — günlük kaydıdır.
# Kökteki ALT KLASÖR (`klasor/not.md`) yalnız kalıyorsa GERÇEK yetimdir.
YOK_SAYILABILIR_KLASORLER: tuple[str, ...] = ("daily",)


def yok_sayilabilir_mi(yol: str) -> bool:
    """Yol, yapı gereği "yalnız" kalan bir not mu?

    Kökteki tek-bileşenli `.md` dosyası ya da `daily/` altındaki bir yol
    `True` döner. Diğer her şey gerçek yetimdir.
    """
    parcalar = yol.split("/")
    if len(parcalar) == 1:
        return parcalar[0].lower().endswith(".md")
    return parcalar[0] in YOK_SAYILABILIR_KLASORLER


@dataclass
class YetimBolum:
    """`yetim_ayir` sonucu: gerçek yetimler ve yapı gereği yalnız kalanlar."""

    gercek: list[tuple[int, str, str]]  # (id, yol, başlık)
    yok_sayilabilir: list[tuple[int, str, str]]

    @property
    def toplam(self) -> int:
        return len(self.gercek) + len(self.yok_sayilabilir)


def yetim_ayir(baglanti: sqlite3.Connection) -> YetimBolum:
    """Yetimleri ikiye ayırır (Dalga B kararı).

    `yetim_notlar` ile aynı küme, yalnızca sınıflandırılır: "gerçek yetim"
    (grafın uçları, gerçekten bağlantısız) ve "yok sayılabilir" (`daily/`
    günlükleri, kök dosyaları).
    """
    gercek: list[tuple[int, str, str]] = []
    yok_sayilabilir: list[tuple[int, str, str]] = []
    for not_id, yol, baslik in baglanti.execute(
        """
        SELECT n.id, n.yol, n.baslik
        FROM notes n
        WHERE NOT EXISTS (SELECT 1 FROM links g WHERE g.hedef_id = n.id)
          AND NOT EXISTS (SELECT 1 FROM links c WHERE c.kaynak_id = n.id)
        ORDER BY n.yol
        """
    ):
        kayit = (int(not_id), yol, baslik)
        (yok_sayilabilir if yok_sayilabilir_mi(yol) else gercek).append(kayit)
    return YetimBolum(gercek=gercek, yok_sayilabilir=yok_sayilabilir)


def etiket_sikligi(baglanti: sqlite3.Connection, ilk: int | None = None) -> list[tuple[str, int]]:
    """(etiket, adet) — sıklığa göre azalan."""
    sql = """
    SELECT etiket, COUNT(*) AS adet
    FROM tags GROUP BY etiket ORDER BY adet DESC, etiket ASC
    """
    if ilk is not None:
        sql += f" LIMIT {int(ilk)}"
    return [(etiket, adet) for etiket, adet in baglanti.execute(sql)]


def not_ozet(baglanti: sqlite3.Connection, not_id: int) -> dict[str, object]:
    satir = baglanti.execute(
        "SELECT yol, baslik, karakter FROM notes WHERE id = ?", (not_id,)
    ).fetchone()
    if satir is None:
        return {}
    return {
        "yol": satir[0],
        "baslik": satir[1],
        "karakter": satir[2],
        "etiketler": [e for (e,) in baglanti.execute("SELECT etiket FROM tags WHERE not_id = ?", (not_id,))],
        "linkler": [
            (h, t, h2 is not None)
            for h, t, h2 in baglanti.execute(
                "SELECT hedef_metin, tur, hedef_id FROM links WHERE kaynak_id = ?", (not_id,)
            )
        ],
    }


# ---------------------------------------------------------------------------
# Web (Dalga B) sorguları — hepsi yalnızca indeks DB'sini okur.
# ---------------------------------------------------------------------------

KOK_ETIKET = "(kök)"
OZET_KARAKTER = 600


def klasor_ad(yol: str) -> str:
    """Yolun en üst klasörü; kökteki notlar için `"(kök)"`."""
    parcalar = yol.split("/")
    return parcalar[0] if len(parcalar) > 1 else KOK_ETIKET


def graf_dugumleri(baglanti: sqlite3.Connection) -> list[dict[str, object]]:
    """Graf için düğüm listesi: id, başlık, yol, klasör, etiketler, derece.

    Derece = gelen + giden çözülmüş link sayısı. Kırık linkler kenarda yok,
    bu yüzden dereceye katılmaz.
    """
    etiketler: dict[int, list[str]] = {}
    for not_id, etiket in baglanti.execute("SELECT not_id, etiket FROM tags ORDER BY not_id, etiket"):
        etiketler.setdefault(int(not_id), []).append(etiket)

    dugumler: list[dict[str, object]] = []
    for not_id, yol, baslik in baglanti.execute("SELECT id, yol, baslik FROM notes ORDER BY id"):
        # Gelen linkler KAYNAK NOTA GÖRE tekrarsız sayılır (bir not birden çok
        # linkle aynı hedefe bağlanabilir); böylece derece, paneldeki
        # `giden + gelen` uzunluğuyla birebir tutarlıdır. Kendine bağlanan
        # (`[[kendi]]`) linkler graf kenarı olmadığı için dereceye girmez.
        gelen = baglanti.execute(
            "SELECT COUNT(DISTINCT kaynak_id) FROM links WHERE hedef_id = ? AND kaynak_id <> hedef_id",
            (not_id,),
        ).fetchone()[0]
        giden = baglanti.execute(
            "SELECT COUNT(*) FROM links "
            "WHERE kaynak_id = ? AND hedef_id IS NOT NULL AND hedef_id <> kaynak_id",
            (not_id,),
        ).fetchone()[0]
        dugumler.append(
            {
                "id": int(not_id),
                "baslik": baslik,
                "yol": yol,
                "klasor": klasor_ad(yol),
                "etiketler": etiketler.get(int(not_id), []),
                "derece": int(gelen) + int(giden),
            }
        )
    return dugumler


def graf_kenarlari(baglanti: sqlite3.Connection) -> list[dict[str, int]]:
    """Çözülmüş linklerden graf kenarları (kaynak_id, hedef_id).

    Aynı çift için tekrarlanan linkler tek kenara indirgenir; ağırlık kaybı
    kabul, çizim hızı kazanımı için bilinçli tercihtir.
    """
    return [
        {"kaynak": int(kaynak), "hedef": int(hedef)}
        for kaynak, hedef in baglanti.execute(
            """
            SELECT DISTINCT kaynak_id, hedef_id FROM links
            WHERE hedef_id IS NOT NULL AND hedef_id <> kaynak_id
            ORDER BY kaynak_id, hedef_id
            """
        )
    ]


def not_detay(baglanti: sqlite3.Connection, not_id: int) -> dict[str, object] | None:
    """`/api/not/<id>` gövdesi: özet, etiketler, giden/gelen linkler, kırıklar.

    `ozet` yalnızca `chunks` tablosundan okunur — ham vault dosyası ASLA
    yeniden açılmaz, böylece gizlilik süzümü tek noktada kalır.
    """
    satir = baglanti.execute(
        "SELECT id, yol, baslik FROM notes WHERE id = ?", (not_id,)
    ).fetchone()
    if satir is None:
        return None
    not_id, yol, baslik = int(satir[0]), satir[1], satir[2]

    parcalar = [m for (m,) in baglanti.execute(
        "SELECT metin FROM chunks WHERE not_id = ? ORDER BY sira", (not_id,)
    )]
    ozet = "\n\n".join(parcalar)[:OZET_KARAKTER].strip()
    # Karar Q4: kesildiyse panel bunu gösterir ("… (devamı notta)").
    ozet_kesildi = len(ozet) >= OZET_KARAKTER

    giden: list[dict[str, object]] = []
    kirik: list[str] = []
    for hedef_id, hedef_metin in baglanti.execute(
        "SELECT hedef_id, hedef_metin FROM links WHERE kaynak_id = ? ORDER BY rowid", (not_id,)
    ):
        if hedef_id is None:
            kirik.append(hedef_metin)
            continue
        # Kendine bağlanan link graf kenarı değildir; dereceye de girmemeli.
        if int(hedef_id) == not_id:
            continue
        giden.append({"id": int(hedef_id), "baslik": _baslik_id(baglanti, int(hedef_id))})

    gelen = [
        {"id": int(kaynak_id), "baslik": _baslik_id(baglanti, int(kaynak_id))}
        for (kaynak_id,) in baglanti.execute(
            "SELECT DISTINCT kaynak_id FROM links "
            "WHERE hedef_id = ? AND kaynak_id <> hedef_id ORDER BY kaynak_id",
            (not_id,),
        )
    ]

    return {
        "id": not_id,
        "baslik": baslik,
        "yol": yol,
        "klasor": klasor_ad(yol),
        "etiketler": [e for (e,) in baglanti.execute(
            "SELECT etiket FROM tags WHERE not_id = ? ORDER BY etiket", (not_id,)
        )],
        "ozet": ozet,
        "ozet_kesildi": ozet_kesildi,
        "giden": giden,
        "gelen": gelen,
        "kirik": kirik,
    }


def _baslik_id(baglanti: sqlite3.Connection, not_id: int) -> str:
    satir = baglanti.execute("SELECT baslik FROM notes WHERE id = ?", (not_id,)).fetchone()
    return satir[0] if satir else ""


def kirik_linkler_detayli(baglanti: sqlite3.Connection) -> list[dict[str, object]]:
    """`/kirik` listesi için (kaynak_id, kaynak yol, kaynak başlık, hedef metin)."""
    return [
        {"kaynak_id": int(kaynak_id), "yol": yol, "baslik": baslik, "hedef": hedef}
        for kaynak_id, yol, baslik, hedef in baglanti.execute(
            """
            SELECT k.id, k.yol, k.baslik, l.hedef_metin
            FROM links l JOIN notes k ON k.id = l.kaynak_id
            WHERE l.hedef_id IS NULL
            ORDER BY k.yol, l.rowid
            """
        )
    ]


def toplam_sayaclar(baglanti: sqlite3.Connection) -> dict[str, int]:
    """Üst özet şeridi için: not, link ve kırık link sayıları."""
    notlar = int(baglanti.execute("SELECT COUNT(*) FROM notes").fetchone()[0])
    linkler = int(baglanti.execute("SELECT COUNT(*) FROM links").fetchone()[0])
    kirik = int(
        baglanti.execute("SELECT COUNT(*) FROM links WHERE hedef_id IS NULL").fetchone()[0]
    )
    return {"not": notlar, "link": linkler, "kirik": kirik}
