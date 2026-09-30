"""Dalga D — arama performansı (1200 notluk sentetik vault).

Ölçülen: indeksleme süresi (aramalı/aramasız) ve `harita ara` tek sorgu
gecikmesi (medyan, p95). Kabul: sorgu p95 < 150 ms.
"""

from __future__ import annotations

import sqlite3
import statistics
import time
from pathlib import Path

import pytest

from conftest import sentetik_vault

from harita import ara as ara_modulu
from harita.index import baglan, indeksle

pytestmark = pytest.mark.perf

# Kabul eşiği (Dalga D).
P95_HEDEF_MS = 150.0

# Sorgu kümesi: kısa/yaygın, nadir, Türkçe karakterli ve kök eki olanlar.
SORGULAR = [
    "not",
    "bağlantı",
    "sentetik",
    "performans ölçümü",
    "kafes",
    "güvenlik sızıntısı",
    "veri temizleme",
    "ışık ölçümü",
    "planlama",
    "kullanıcı araştırması",
]


def _sure(baglanti: sqlite3.Connection, sorgu: str, tekrar: int = 20) -> list[float]:
    """Tek sorgu gecikmeleri (ms). İlk çağrı ısınma (sıcak DB) sayılmaz."""
    for _ in range(3):
        ara_modulu.ara(baglanti, sorgu, ara_modulu.Ayarlar(ilk=10))
    olcumler: list[float] = []
    for _ in range(tekrar):
        bas = time.perf_counter()
        ara_modulu.ara(baglanti, sorgu, ara_modulu.Ayarlar(ilk=10))
        olcumler.append((time.perf_counter() - bas) * 1000.0)
    return olcumler


@pytest.fixture(scope="module")
def perf_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """1200 notluk sentetik vault (çalışma zamanında üretilir)."""
    return sentetik_vault(tmp_path_factory.mktemp("ara-perf"), not_sayisi=1200)


@pytest.fixture(scope="module")
def perf_db(perf_vault: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    db = tmp_path_factory.mktemp("ara-perf-db") / "perf.db"
    indeksle(perf_vault, db)
    return db


def test_indeksleme_suresi_olculur(perf_vault: Path, tmp_path: Path) -> None:
    """İndekleme süresi ölçülür ve arama indeksinin kurulduğu doğrulanır."""
    db = tmp_path / "sure.db"
    bas = time.perf_counter()
    ozet = indeksle(perf_vault, db)
    sure = time.perf_counter() - bas
    assert ozet.arama_belge == 1200
    assert ozet.arama_terim > 0
    # Makul üst sınır: 1200 not 60 sn'de indekslenmeli.
    assert sure < 60.0, f"indeksleme çok yavaş: {sure:.1f}s"


def test_indeks_boyutu(perf_db: Path) -> None:
    """İndeks boyutu ölçülür (arama tablolarının payı)."""
    baglanti = baglan(perf_db)
    try:
        terim = baglanti.execute("SELECT COUNT(*) FROM ara_terim").fetchone()[0]
        belge = baglanti.execute("SELECT COUNT(*) FROM ara_belge").fetchone()[0]
    finally:
        baglanti.close()
    assert belge == 1200
    assert terim > 0
    boyut = perf_db.stat().st_size
    assert boyut > 0


def test_sorgu_gecikmesi_p95_hedefin_altinda(perf_db: Path) -> None:
    """Sıcak DB'de sorgu p95 < 150 ms (kabul kriteri)."""
    baglanti = baglan(perf_db)
    try:
        tum: list[float] = []
        for sorgu in SORGULAR:
            tum.extend(_sure(baglanti, sorgu, tekrar=20))
    finally:
        baglanti.close()

    tum.sort()
    medyan = statistics.median(tum)
    p95 = tum[int(len(tum) * 0.95)]
    print(f"\n  ARAMA: medyan={medyan:.2f} ms, p95={p95:.2f} ms, n={len(tum)}")
    assert p95 < P95_HEDEF_MS, f"p95 çok yüksek: {p95:.1f} ms (hedef {P95_HEDEF_MS})"


def test_medyan_ve_p95_raporlanabilir(perf_db: Path) -> None:
    """Medyan ve p95 hesaplanabilir (rapor için sayı üretir)."""
    baglanti = baglan(perf_db)
    try:
        tum: list[float] = []
        for sorgu in SORGULAR:
            tum.extend(_sure(baglanti, sorgu, tekrar=15))
    finally:
        baglanti.close()
    tum.sort()
    medyan = statistics.median(tum)
    p95 = tum[min(len(tum) - 1, int(len(tum) * 0.95))]
    assert medyan > 0
    assert p95 >= medyan
