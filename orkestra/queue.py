"""SQLite tabanlı görev kuyruğu.

Kuyruk bir DB dosyasına bağlıdır; süreç yeniden başlayınca durum korunur.
Yarım kalmış `calisiyor` görevler kendiliğinden düzeltilmez — `kurtar()`
açıkça çağrılmalıdır.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from . import guard, report
from .models import (
    Durum,
    GecersizGecis,
    GecersizGirdi,
    GorevBulunamadi,
    Run,
    RunSonuc,
    Task,
    gecis_gecerli,
    utc_simdi,
)

YARIM_KALDI_HATASI = "yarim-kaldi"
# Kanıt katmanı son mesajda red/engel bulduğunda `runs.hata` bu işareti alır;
# mevcut onay akışı (`onay-bekliyor`) böylece görünür olur.
IZIN_REDDI_SUPHESI = "izin-reddi-suphesi"

SEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ajan      TEXT NOT NULL,
    istem     TEXT NOT NULL,
    durum     TEXT NOT NULL,
    olusturma TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_durum ON tasks(durum, id);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       INTEGER NOT NULL REFERENCES tasks(id),
    baslangic     TEXT NOT NULL,
    bitis         TEXT,
    cikis_kodu     INTEGER,
    cikti_yolu    TEXT,
    kanit_yollari TEXT,
    hata          TEXT
);
CREATE INDEX IF NOT EXISTS runs_task_id ON runs(task_id);

-- C dalgası (kota) için şimdiden hazır; bu dalgada kullanılmaz.
CREATE TABLE IF NOT EXISTS quota_snapshots (
    model   TEXT NOT NULL,
    gun     TEXT NOT NULL,
    istek   INTEGER NOT NULL DEFAULT 0,
    maliyet REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (model, gun)
);

-- Kota ayrıştırıcısının artımlı okuma konumu (Dalga C).
CREATE TABLE IF NOT EXISTS quota_offsets (
    kaynak TEXT PRIMARY KEY,
    konum  INTEGER NOT NULL DEFAULT 0,
    boyut  INTEGER NOT NULL DEFAULT 0
);

-- Dalga D: planlayıcı çıktısı (hedef MASKELİ saklanır).
CREATE TABLE IF NOT EXISTS plans (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    hedef     TEXT NOT NULL,
    olusturma TEXT NOT NULL,
    json      TEXT NOT NULL
);
"""

# `PRAGMA user_version` şema sürümü. Dalga D'de 2: kanıt sütunları + plans.
SEMA_SURUM = 2

# Dalga D'nin eklediği sütunlar. `ALTER TABLE ... ADD COLUMN` boşsa no-op'tur,
# dolayısıyla hem eski hem yeni DB'de güvenle çalışır.
GECIS_SUTUNLARI: tuple[tuple[str, str, str], ...] = (
    ("runs", "kanit_durumu", "TEXT"),
    ("runs", "kanit_ozeti", "TEXT"),
    ("tasks", "rapor_dosyasi", "TEXT"),
)


def _sutunlar(baglanti: sqlite3.Connection, tablo: str) -> set[str]:
    return {s[1] for s in baglanti.execute(f"PRAGMA table_info({tablo})")}


def _goc(baglanti: sqlite3.Connection) -> None:
    """Eski şemayı VERİ KAYBETMEDEN yeni sütunlarla tamamlar.

    `ALTER TABLE ADD COLUMN` yalnız eksik sütunları ekler; satırlara dokunmaz.
    `user_version` ilerleme göstergesidir ve web `mode=ro` bağlantısında
    okunmasa da sorgu bozulmaz (sütun yoksa `COALESCE`/yok sayma yolu var).
    """
    for tablo, sutun, tip in GECIS_SUTUNLARI:
        mevcut = _sutunlar(baglanti, tablo)
        if not mevcut:
            continue  # tablo hiç yoksa (yabancı DB) dokunma
        if sutun not in mevcut:
            baglanti.execute(f"ALTER TABLE {tablo} ADD COLUMN {sutun} {tip}")
    baglanti.execute(f"PRAGMA user_version={SEMA_SURUM}")


def varsayilan_db_yolu() -> Path:
    """`ORKESTRA_DB` varsa o, yoksa `~/.orkestra/orkestra.db`."""
    ortam = os.environ.get("ORKESTRA_DB")
    if ortam:
        return Path(ortam).expanduser()
    return Path.home() / ".orkestra" / "orkestra.db"


class Queue:
    def __init__(self, yol: str | os.PathLike | None = None):
        self.yol = Path(yol).expanduser() if yol is not None else varsayilan_db_yolu()
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self._baglanti = sqlite3.connect(str(self.yol), isolation_level=None)
        self._baglanti.row_factory = sqlite3.Row
        self._baglanti.execute("PRAGMA journal_mode=WAL")
        self._baglanti.execute("PRAGMA foreign_keys=ON")
        self._baglanti.executescript(SEMA)
        # Dalga D: eksik sütunları ekle (eski DB veri kaybetmeden yükselir).
        _goc(self._baglanti)

    # -- yaşam döngüsü ---------------------------------------------------

    def baglanti_al(self) -> sqlite3.Connection:
        """Ham bağlantı (kota güncellemesi gibi yazma yapan işler için).

        Panel BUNU KULLANMAZ; panel `mode=ro` ile kendi bağlantısını açar.
        """
        return self._baglanti

    def kapat(self) -> None:
        self._baglanti.close()

    def __enter__(self) -> "Queue":
        return self

    def __exit__(self, *bilgi) -> None:
        self.kapat()

    # -- yazma -----------------------------------------------------------

    def ekle(self, ajan: str, istem: str, rapor_dosyasi: str | None = None) -> Task:
        """Kuyruğa görev ekler.

        `rapor_dosyasi` çalışma dizinine GÖRELİ bir yoldur (ajanlar gerçek
        raporu dosyaya yazar, log yalnız özet olur). Mutlak yol ve `..`
        kaçışı burada reddedilir; sembolik bağ ve çalışma dizini denetimi
        koşu sırasında `report.degerlendir` içinde yapılır.
        """
        guard.girdi_kontrol(ajan, istem)
        if rapor_dosyasi:
            yol = Path(rapor_dosyasi)
            if yol.is_absolute() or ".." in yol.parts:
                raise GecersizGirdi(
                    "rapor dosyasi calisma dizinine goreli olmali "
                    "(mutlak yol ve '..' reddedildi)"
                )
        simdi = utc_simdi()
        imlec = self._baglanti.execute(
            "INSERT INTO tasks (ajan, istem, durum, olusturma, rapor_dosyasi) "
            "VALUES (?, ?, ?, ?, ?)",
            (ajan, istem, Durum.BEKLIYOR.value, simdi, rapor_dosyasi),
        )
        return self.al(imlec.lastrowid)

    def gecis(self, gorev_id: int, yeni_durum: Durum | str) -> Task:
        """Durum makinesini uygular; geçersizse `GecersizGecis` ve DB değişmez."""
        yeni = Durum(yeni_durum)
        gorev = self.al(gorev_id)
        if not gecis_gecerli(gorev.durum, yeni):
            raise GecersizGecis(
                f"gecersiz gecis: {gorev.durum.value} -> {yeni.value}"
            )
        self._baglanti.execute(
            "UPDATE tasks SET durum = ? WHERE id = ?", (yeni.value, gorev_id)
        )
        return self.al(gorev_id)

    def iptal(self, gorev_id: int) -> Task:
        return self.gecis(gorev_id, Durum.IPTAL)

    def tekrar(self, gorev_id: int) -> Task:
        """Hatalı görevi yeniden denemeye alır (hata -> bekliyor)."""
        return self.gecis(gorev_id, Durum.BEKLIYOR)

    def kurtar(self) -> list[Task]:
        """Süreç ölürken `calisiyor` kalan görevleri `hata`ya çeker."""
        yarim = [
            satir["id"]
            for satir in self._baglanti.execute(
                "SELECT id FROM tasks WHERE durum = ? ORDER BY id", (Durum.CALISIYOR.value,)
            )
        ]
        if not yarim:
            return []
        self._baglanti.execute(
            "UPDATE tasks SET durum = ? WHERE durum = ?",
            (Durum.HATA.value, Durum.CALISIYOR.value),
        )
        for gorev_id in yarim:
            self._baglanti.execute(
                "UPDATE runs SET bitis = ?, hata = ? WHERE task_id = ? AND bitis IS NULL",
                (utc_simdi(), YARIM_KALDI_HATASI, gorev_id),
            )
        return [self.al(gorev_id) for gorev_id in yarim]

    # -- okuma -----------------------------------------------------------

    def al(self, gorev_id: int) -> Task:
        satir = self._baglanti.execute(
            "SELECT * FROM tasks WHERE id = ?", (int(gorev_id),)
        ).fetchone()
        if satir is None:
            raise GorevBulunamadi(f"gorev bulunamadi: {gorev_id}")
        return Task.satirdan(satir)

    def var_mi(self, gorev_id: int) -> bool:
        satir = self._baglanti.execute(
            "SELECT 1 FROM tasks WHERE id = ?", (int(gorev_id),)
        ).fetchone()
        return satir is not None

    def liste(self, durum: Durum | str | None = None) -> list[Task]:
        if durum is None:
            sql = "SELECT * FROM tasks ORDER BY id"
            parametre: tuple = ()
        else:
            sql = "SELECT * FROM tasks WHERE durum = ? ORDER BY id"
            parametre = (Durum(durum).value,)
        return [Task.satirdan(s) for s in self._baglanti.execute(sql, parametre)]

    def sonraki_bekleyen(self) -> Task | None:
        """FIFO: en eski bekleyen görev."""
        satir = self._baglanti.execute(
            "SELECT * FROM tasks WHERE durum = ? ORDER BY id LIMIT 1",
            (Durum.BEKLIYOR.value,),
        ).fetchone()
        return Task.satirdan(satir) if satir else None

    def kosular(self, gorev_id: int) -> list[Run]:
        satirlar = self._baglanti.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY id", (int(gorev_id),)
        ).fetchall()
        return [self._run_satirdan(s) for s in satirlar]

    @staticmethod
    def _run_satirdan(s) -> Run:
        """Satırdan `Run` üretir; eksik sütunlarda (eski DB) alanlar `None` kalır."""
        try:
            ozet = json.loads(s["kanit_ozeti"]) if s["kanit_ozeti"] else None
        except (TypeError, ValueError):
            ozet = None
        try:
            kanit = json.loads(s["kanit_yollari"]) if s["kanit_yollari"] else []
        except (TypeError, ValueError):
            kanit = []
        return Run(
            id=s["id"],
            task_id=s["task_id"],
            baslangic=s["baslangic"],
            bitis=s["bitis"],
            cikis_kodu=s["cikis_kodu"],
            cikti_yolu=s["cikti_yolu"],
            kanit_yollari=kanit,
            hata=s["hata"],
            kanit_durumu=s["kanit_durumu"] if "kanit_durumu" in s.keys() else None,
            kanit_ozeti=ozet,
        )

    def run_bul(self, run_id: int) -> Run | None:
        satir = self._baglanti.execute(
            "SELECT * FROM runs WHERE id = ?", (int(run_id),)
        ).fetchone()
        return self._run_satirdan(satir) if satir else None

    def run_kanit_yaz(self, run_id: int, durum: str, ozet: dict | None) -> None:
        """Kanıt durumunu/özetini yazar (maskeli JSON)."""
        self._baglanti.execute(
            "UPDATE runs SET kanit_durumu = ?, kanit_ozeti = ? WHERE id = ?",
            (durum, json.dumps(ozet, ensure_ascii=False) if ozet else None, int(run_id)),
        )

    def gorev_kanitleri(self, gorev_id: int) -> list[Run]:
        """Bir görevin koşuları arasında UYARI taşıyan (kanıtsız/başarısız/red) koşu var mı."""
        return [
            r for r in self.kosular(gorev_id)
            if r.kanit_durumu in (report.KANITSIZ, report.BASARISIZ, report.REDDEDILDI)
        ]

    # -- calistirma ------------------------------------------------------

    def _atomik_al(self) -> Task | None:
        """En eski bekleyen görevi TEK atomik `UPDATE` ile çalar.

        İki süreç aynı anda çalıştırırsa `WHERE durum='bekliyor'` koşulu yalnızca
        birinde eşleşir; diğeri `rowcount == 0` görür ve bir sonrakine geçer.
        """
        while True:
            bekleyen = self.sonraki_bekleyen()
            if bekleyen is None:
                return None
            imlec = self._baglanti.execute(
                "UPDATE tasks SET durum = ? WHERE id = ? AND durum = ?",
                (Durum.CALISIYOR.value, bekleyen.id, Durum.BEKLIYOR.value),
            )
            if imlec.rowcount == 1:
                return self.al(bekleyen.id)
            # Başka süreç aldı; sıradakine geç.

    def calistir_bir(self, runner, calisma_dizini: str | os.PathLike | None = None) -> tuple[Task, Run] | None:
        """Sıradaki bekleyen görevi `runner` ile çalıştırır.

        Bekliyor -> calisiyor geçişi atomiktir: iki eşzamanlı süreç aynı görevi
        asla ikisi birden alamaz.

        Runner istisna fırlatırsa görev `hata` olur, kuyruk ayakta kalır.
        Kuyruk boşsa `None` döner.

        Dalga D: koşu BAŞLAMADAN önce (çalışma dizini bir git deposuysa) salt
        okunur git özeti alınır; sonuçta log + rapor dosyası ayrıştırılır ve
        `kanit_durumu` yazılır. `reddedildi-suphesi` görevi `onay-bekliyor`
        yapar; diğer durumlar durum makinesine YENİ durum EKLEMEZ.
        """
        gorev = self._atomik_al()
        if gorev is None:
            return None

        # Kanıt değerlendirmesinin tabanı: açıkça verilen dizin, yoksa
        # runner'ın `cwd`'si, o da yoksa süreç dizini. Görsel yolları BUNA
        # göre çözülür (rapor göreli yol yazar).
        kok = Path(
            calisma_dizini
            or getattr(runner, "cwd", None)
            or getattr(runner, "calisma_dizini", None)
            or Path.cwd()
        )
        # Koşu başlamadan ÖNCE git durumu (yalnız iki salt-okunur komut).
        git_once = report.git_ozeti(kok)

        baslangic = utc_simdi()
        run_id = self._baglanti.execute(
            "INSERT INTO runs (task_id, baslangic) VALUES (?, ?)",
            (gorev.id, baslangic),
        ).lastrowid

        try:
            sonuc = runner.calistir(gorev)
        except Exception as istisna:  # noqa: BLE001 — kuyruk düşmemeli
            # İstisna metni runner çıktısından sır taşıyabilir; maskele.
            sonuc = RunSonuc(
                cikis_kodu=1,
                hata=guard.maskele(f"{type(istisna).__name__}: {istisna}"),
            )

        if not isinstance(sonuc, RunSonuc):
            sonuc = RunSonuc(cikis_kodu=1, hata="runner RunSonuc donmedi")

        bitis = utc_simdi()
        # Kanıt değerlendirmesi log'un kendisinden yapılır (maskeli metin DEĞİL,
        # ham log okunur; kayda maskeli gider).
        degerlendirme = self._raporu_degerlendir(sonuc, gorev, baslangic, git_once, kok)

        if sonuc.onay_gerekli or degerlendirme.sonuc == report.REDDEDILDI:
            yeni_durum = Durum.ONAY_BEKLIYOR
            # Mevcut onay akışı `runs.hata` alanını okur; burada da aynı
            # işaret yazılır (izin reddi ASLA yeniden denenmez).
            if not sonuc.hata:
                sonuc.hata = IZIN_REDDI_SUPHESI
        elif sonuc.hata or (sonuc.cikis_kodu or 0) != 0:
            yeni_durum = Durum.HATA
        else:
            yeni_durum = Durum.BITTI

        kanit = [guard.maskele(yol) for yol in (sonuc.kanit_yollari or [])]
        self._baglanti.execute(
            "UPDATE runs SET bitis = ?, cikis_kodu = ?, cikti_yolu = ?, "
            "kanit_yollari = ?, hata = ?, kanit_durumu = ?, kanit_ozeti = ? "
            "WHERE id = ?",
            (
                bitis,
                sonuc.cikis_kodu,
                # `cikti` artık GERÇEKTEN log dosyasının yoludur (Dalga B);
                # yine de gizli kalıp taşıyabileceği için maskelenir.
                guard.maskele(sonuc.cikti) if sonuc.cikti else sonuc.cikti,
                json.dumps(kanit, ensure_ascii=False),
                guard.maskele(sonuc.hata) if sonuc.hata else sonuc.hata,
                degerlendirme.sonuc,
                json.dumps(self._kanit_ozeti(degerlendirme), ensure_ascii=False),
                run_id,
            ),
        )
        gorev = self.gecis(gorev.id, yeni_durum)
        kosu = next(r for r in self.kosular(gorev.id) if r.id == run_id)
        return gorev, kosu

    @staticmethod
    def _kanit_ozeti(degerlendirme: report.Degerlendirme) -> dict:
        """`runs.kanit_ozeti` JSON'u (Dalga E: `yapisal` alt nesnesi içerir).

        DB ŞEMASI DEĞİŞMEZ — anahtar zaten var olan JSON sütununa yazılır.
        Yapısal veri YOKSA anahtar hiç yazılmaz → eski satırlarla aynı biçim,
        okuyanlar `.get("yapisal")` ile None-güvenli kalır.
        """
        ozet = degerlendirme.json()
        if degerlendirme.yapisal:
            yapisal = dict(degerlendirme.yapisal)
            yapisal["gozlemlenen_test_sayisi"] = degerlendirme.gozlemlenen_temiz_test_sayisi()
            ozet["yapisal"] = yapisal
        return ozet

    def _raporu_degerlendir(
        self, sonuc: RunSonuc, gorev: Task, baslangic: str, git_once: str | None,
        calisma_dizini: Path,
    ) -> report.Degerlendirme:
        """Log (+ rapor dosyası) içeriğini kanıta göre değerlendirir.

        Log okunamıyorsa yalnız koşu bilgisiyle (kanıt yolları) değerlendirilir.
        `kanit_yollari` doğrudan gözlemlenen kanıttır, raporda geçse de.
        """
        metin = ""
        if sonuc.cikti:
            # Log yolu RUNNER'IN kendi ürettiği yoldur (kullanıcı girdisi
            # DEĞİLDİR) ve `~/.orkestra/runs` gibi çalışma dizini DIŞINDA
            # olabilir; bu yüzden `calisma_dizini` kısıtı UYGULANMAZ.
            # Yine de dosya boyutu sınırlanır (bellek koruması).
            yol = Path(sonuc.cikti).expanduser()
            try:
                if yol.is_file() and yol.stat().st_size <= report.MAX_LOG_OKUMA:
                    metin = yol.read_text(encoding="utf-8", errors="replace")
            except OSError:
                metin = ""
        git_sonra = report.git_ozeti(calisma_dizini) if git_once is not None else None
        # Dalga E: yapısal akış özeti. `getattr` güvenli — FakeRunner ve eski
        # çalıştırıcılar `yapisal` ALANI OLMAYAN `RunSonuc` döndürebilir.
        yapisal = getattr(sonuc, "yapisal", None)
        degerlendirme = report.degerlendir(
            metin,
            calisma_dizini=calisma_dizini,
            baslangic=baslangic,
            git_once=git_once,
            git_sonra=git_sonra,
            rapor_dosyasi=getattr(sonuc, "rapor_dosyasi", None) or gorev.rapor_dosyasi,
            yapisal=yapisal if isinstance(yapisal, dict) else None,
        )
        # Runner'ın bildirdiği kanıt yolları GÖZLEMLENEN kanıttır; raporda
        # geçmese de kanıt sayılır (dosya gerçekten orada).
        for yol in (sonuc.kanit_yollari or []):
            zaten = any(g.yol == yol for g in degerlendirme.gorseller)
            if zaten:
                continue
            kanit = report._gorseli_denetle(
                yol, calisma_dizini, _zaman_damgasi(baslangic),
            )
            if kanit.gecerli:
                degerlendirme.gorseller.append(kanit)
                if degerlendirme.sonuc == report.KANITSIZ:
                    degerlendirme.sonuc = report.KANITLI
                    degerlendirme.gerekceler.append(
                        report.Gerekce(
                            "runner-kanit-yolu", report.KANITLI,
                            f"kosu tarafindan bildirilen kanit yolu dogrulandi: {yol}",
                        )
                    )
        degerlendirme.kanit_durumu = degerlendirme.sonuc
        degerlendirme.ozet = degerlendirme.ozet_metin()
        return degerlendirme

    # -- planlar (Dalga D) -------------------------------------------------

    def plan_kaydet(self, plan_dict: dict, hedef: str) -> int:
        """Planı kaydeder; `hedef` MASKELİ saklanır."""
        simdi = utc_simdi()
        imlec = self._baglanti.execute(
            "INSERT INTO plans (hedef, olusturma, json) VALUES (?, ?, ?)",
            (guard.maskele(hedef), simdi, json.dumps(plan_dict, ensure_ascii=False)),
        )
        return int(imlec.lastrowid)

    def plan_al(self, plan_id: int) -> dict | None:
        satir = self._baglanti.execute(
            "SELECT * FROM plans WHERE id = ?", (int(plan_id),)
        ).fetchone()
        if satir is None:
            return None
        return {
            "id": satir["id"],
            "hedef": satir["hedef"],
            "olusturma": satir["olusturma"],
            "json": json.loads(satir["json"]),
        }

    def planlar(self) -> list[dict]:
        satirlar = self._baglanti.execute(
            "SELECT id, hedef, olusturma FROM plans ORDER BY id DESC"
        ).fetchall()
        return [
            {"id": s["id"], "hedef": s["hedef"], "olusturma": s["olusturma"]}
            for s in satirlar
        ]

    def rapor_dosyasi_yaz(self, gorev_id: int, dosya: str) -> None:
        self._baglanti.execute(
            "UPDATE tasks SET rapor_dosyasi = ? WHERE id = ?", (dosya, int(gorev_id))
        )


def _zaman_damgasi(s: str | None) -> float | None:
    if not s:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None