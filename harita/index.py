"""SQLite indeksi: notlar, linkler, etiketler, takma adlar, chunks.

Vault'a hiçbir yazma yapılmaz; indeks dosyası `--db` ile verilen yolda durur.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

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


@dataclass
class IndeksOzeti:
    """`harita indeksle` çıktısı için sayaçlar."""

    notlar: int = 0
    linkler: int = 0
    kirik_linkler: int = 0
    etiketler: int = 0
    parcalar: int = 0
    suzulmus_satir: int = 0

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


def sema_olustur(baglanti: sqlite3.Connection) -> None:
    baglanti.executescript(SEKIL)
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

        linkleri_coz(baglanti)
        baglanti.commit()
        ozet.linkler = baglanti.execute("SELECT COUNT(*) FROM links").fetchone()[0]
        ozet.kirik_linkler = baglanti.execute(
            "SELECT COUNT(*) FROM links WHERE hedef_id IS NULL"
        ).fetchone()[0]
        ozet.etiketler = baglanti.execute(
            "SELECT COUNT(DISTINCT etiket) FROM tags"
        ).fetchone()[0]
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
