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

from . import guard
from .models import (
    Durum,
    GecersizGecis,
    GorevBulunamadi,
    Run,
    RunSonuc,
    Task,
    gecis_gecerli,
    utc_simdi,
)

YARIM_KALDI_HATASI = "yarim-kaldi"

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
"""


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

    # -- yaşam döngüsü ---------------------------------------------------

    def kapat(self) -> None:
        self._baglanti.close()

    def __enter__(self) -> "Queue":
        return self

    def __exit__(self, *bilgi) -> None:
        self.kapat()

    # -- yazma -----------------------------------------------------------

    def ekle(self, ajan: str, istem: str) -> Task:
        guard.girdi_kontrol(ajan, istem)
        simdi = utc_simdi()
        imlec = self._baglanti.execute(
            "INSERT INTO tasks (ajan, istem, durum, olusturma) VALUES (?, ?, ?, ?)",
            (ajan, istem, Durum.BEKLIYOR.value, simdi),
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
        return [
            Run(
                id=s["id"],
                task_id=s["task_id"],
                baslangic=s["baslangic"],
                bitis=s["bitis"],
                cikis_kodu=s["cikis_kodu"],
                cikti_yolu=s["cikti_yolu"],
                kanit_yollari=json.loads(s["kanit_yollari"]) if s["kanit_yollari"] else [],
                hata=s["hata"],
            )
            for s in satirlar
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

    def calistir_bir(self, runner) -> tuple[Task, Run] | None:
        """Sıradaki bekleyen görevi `runner` ile çalıştırır.

        Bekliyor -> calisiyor geçişi atomiktir: iki eşzamanlı süreç aynı görevi
        asla ikisi birden alamaz.

        Runner istisna fırlatırsa görev `hata` olur, kuyruk ayakta kalır.
        Kuyruk boşsa `None` döner.
        """
        gorev = self._atomik_al()
        if gorev is None:
            return None

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

        if sonuc.onay_gerekli:
            yeni_durum = Durum.ONAY_BEKLIYOR
        elif sonuc.hata or (sonuc.cikis_kodu or 0) != 0:
            yeni_durum = Durum.HATA
        else:
            yeni_durum = Durum.BITTI

        bitis = utc_simdi()
        kanit = [guard.maskele(yol) for yol in (sonuc.kanit_yollari or [])]
        self._baglanti.execute(
            "UPDATE runs SET bitis = ?, cikis_kodu = ?, cikti_yolu = ?, "
            "kanit_yollari = ?, hata = ? WHERE id = ?",
            (
                bitis,
                sonuc.cikis_kodu,
                # `cikti` artık GERÇEKTEN log dosyasının yoludur (Dalga B);
                # yine de gizli kalıp taşıyabileceği için maskelenir.
                guard.maskele(sonuc.cikti) if sonuc.cikti else sonuc.cikti,
                json.dumps(kanit, ensure_ascii=False),
                guard.maskele(sonuc.hata) if sonuc.hata else sonuc.hata,
                run_id,
            ),
        )
        gorev = self.gecis(gorev.id, yeni_durum)
        kosu = next(r for r in self.kosular(gorev.id) if r.id == run_id)
        return gorev, kosu