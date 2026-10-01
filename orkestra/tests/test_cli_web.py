"""Dalga C CLI testleri: `web`, `kota`, `kota-guncelle` (alt süreç).

Gerçek `claude`/cor ÇAĞRILMAZ; `kota` yalnızca kurgusal `proxy.log` okur.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from orkestra.queue import SEMA

KOK = Path(__file__).resolve().parent.parent

# Gerçek log biçiminde kurgusal satırlar. Kota "bugünü" saydığı için tarihler sabit
# yazılmaz: sabit tarih gün değişince testleri kırıyordu (2026-10-01 CI hatası).
_BUGUN = datetime.now(timezone.utc).date()
_D0 = _BUGUN.isoformat()
_D4 = (_BUGUN - timedelta(days=4)).isoformat()
LOG_1 = f"[{_D0}T00:00:25.675Z] openrouter -> stealth/space-bunny-alpha (stream)"
LOG_2 = f"[{_D0}T00:00:26.000Z] openrouter -> stealth/space-bunny-alpha"
LOG_3 = f"[{_D4}T09:02:11.400Z] openrouter -> nvidia/nemotron-3-ultra-550b-a55b:free"
LOG_BILINMEYEN = f"[{_D0}T00:00:15.000Z] proxy dinliyor: http://127.0.0.1:8787"


@pytest.fixture()
def db(tmp_path):
    yol = tmp_path / "cli.db"
    b = sqlite3.connect(yol)
    b.executescript(SEMA)
    b.commit()
    b.close()
    return yol


@pytest.fixture()
def cor_log(tmp_path):
    yol = tmp_path / "proxy.log"
    yol.write_text("\n".join([LOG_1, LOG_2, LOG_3, LOG_BILINMEYEN]) + "\n", encoding="utf-8")
    return yol


def calistir(*args, cwd=KOK):
    """Alt süreç olarak `python -m orkestra ...` çalıştırır."""
    return subprocess.run(
        [sys.executable, "-m", "orkestra", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


# -- kota-guncelle ----------------------------------------------------------


def test_kota_guncelle(db, cor_log):
    sonuc = calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    assert sonuc.returncode == 0, sonuc.stderr
    assert "3 yeni istek" in sonuc.stdout
    assert "1 taninmayan satir" in sonuc.stdout


def test_kota_guncelle_sonrasi_db_yazilir(db, cor_log):
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    b = sqlite3.connect(db)
    satir = b.execute("SELECT * FROM quota_snapshots").fetchall()
    b.close()
    assert len(satir) == 2  # iki gun, iki model


def test_kota_guncelle_iki_kez_idempotent(db, cor_log):
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    sonuc = calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    assert sonuc.returncode == 0
    assert "yeni istek yok" in sonuc.stdout


def test_kota_guncelle_olmayan_log(db, tmp_path):
    sonuc = calistir(
        "--db", str(db), "kota-guncelle", "--cor-log", str(tmp_path / "yok.log")
    )
    assert sonuc.returncode == 0
    assert "yeni istek yok" in sonuc.stdout


# -- kota -------------------------------------------------------------------


def test_kota_bos_db(db):
    sonuc = calistir("--db", str(db), "kota")
    assert sonuc.returncode == 0
    assert "Kota verisi yok" in sonuc.stdout


def test_kota_gosterir(db, cor_log):
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    sonuc = calistir("--db", str(db), "kota")
    assert sonuc.returncode == 0
    assert "stealth/space-bunny-alpha" in sonuc.stdout
    assert "limitsiz" in sonuc.stdout


def test_kota_json(db, cor_log):
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    sonuc = calistir("--db", str(db), "kota", "--json")
    assert sonuc.returncode == 0
    veri = json.loads(sonuc.stdout)
    assert "modeller" in veri
    assert veri["gun"]


def test_kota_kota_toml_uygulanir(db, cor_log, tmp_path):
    toml = tmp_path / "kota.toml"
    toml.write_text('[limitler]\n"stealth/space-bunny-alpha" = 2\n', encoding="utf-8")
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    sonuc = calistir("--db", str(db), "kota", "--json", "--kota-toml", str(toml))
    veri = json.loads(sonuc.stdout)
    model = next(m for m in veri["modeller"] if m["model"] == "stealth/space-bunny-alpha")
    assert model["limit"] == 2
    assert model["durum"] == "asildi"  # 2 istek / 2 limit


def test_kota_uyari_esigi(db, cor_log, tmp_path):
    toml = tmp_path / "kota.toml"
    toml.write_text('[limitler]\n"stealth/space-bunny-alpha" = 10\n', encoding="utf-8")
    calistir("--db", str(db), "kota-guncelle", "--cor-log", str(cor_log))
    veri = json.loads(calistir("--db", str(db), "kota", "--json", "--kota-toml", str(toml)).stdout)
    model = next(m for m in veri["modeller"] if m["model"] == "stealth/space-bunny-alpha")
    # 2/10 = %20 -> normal
    assert model["durum"] == "normal"


# -- web (yardimci seviye; sunucu e2e'de baslar) ---------------------------


def test_web_yardimi(db):
    sonuc = calistir("web", "--help")
    assert sonuc.returncode == 0
    assert "--port" in sonuc.stdout
    assert "--cikti-dizini" in sonuc.stdout
    assert "--cor-log" in sonuc.stdout
    assert "--kota-toml" in sonuc.stdout


def test_web_varsayilan_port_8780():
    """Sözleşmedeki varsayılan port 8780."""
    from orkestra import cli

    assert cli.VARSAYILAN_PORT == 8780


def test_web_host_secenegi_yok(db):
    """`--host` OLMAMALI: adres koda sabit."""
    sonuc = calistir("web", "--help")
    assert "--host" not in sonuc.stdout


def test_ana_yardimda_web_kota_var():
    sonuc = calistir("--help")
    assert "web" in sonuc.stdout
    assert "kota" in sonuc.stdout
    assert "kota-guncelle" in sonuc.stdout
