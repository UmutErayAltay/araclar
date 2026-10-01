"""cli.py: komutlar, çıkış kodları ve gizlilik (gerçek ağ yok)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tekrar import cli, telegram, uret
from tekrar.kartlar import Depo
from tekrar.llm import LLMError

BUGUN = "2026-10-01"
GIZLI = "ÇOK-ÖZEL-NOT-İÇERİĞİ-12345"


def _vault(tmp_path: Path, icerik: str = GIZLI) -> Path:
    k = tmp_path / "vault" / "knowledge" / "concepts"
    k.mkdir(parents=True)
    (k / "a.md").write_text(icerik, encoding="utf-8")
    return tmp_path / "vault"


def _depo_yolu(tmp_path: Path) -> str:
    return str(tmp_path / "kartlar.json")


def _kart_ekle(tmp_path: Path, n: int = 3) -> Depo:
    from datetime import date

    depo = Depo(Path(_depo_yolu(tmp_path)))
    depo.ekle("a.md", "h", [(f"S{i}?", f"C{i}") for i in range(n)], date(2026, 10, 1))
    depo.kaydet()
    return depo


class FakeLLM:
    cagrilar = 0
    mod = "ok"

    def __init__(self, *a, **k):
        pass

    def complete(self, prompt):
        FakeLLM.cagrilar += 1
        if FakeLLM.mod == "hata":
            raise LLMError("kapalı")
        return json.dumps([{"soru": "Üretilen soru?", "cevap": "Üretilen cevap"}])


@pytest.fixture(autouse=True)
def _sahte_llm(monkeypatch):
    from tekrar import llm

    FakeLLM.cagrilar, FakeLLM.mod = 0, "ok"
    monkeypatch.setattr(llm, "CorLLMClient", FakeLLM)


class TestUret:
    def test_bayraksiz_aga_cikmaz_ve_icerik_yazmaz(self, tmp_path, capsys):
        vault = _vault(tmp_path)
        rc = cli.main(["uret", str(vault), "--depo", _depo_yolu(tmp_path)])
        cikti = capsys.readouterr()
        assert rc == 0
        assert FakeLLM.cagrilar == 0
        assert "cor'a gönderilmedi" in cikti.out
        assert GIZLI not in cikti.out + cikti.err

    def test_kuru_aga_cikmaz(self, tmp_path, capsys):
        vault = _vault(tmp_path)
        assert cli.main(["uret", str(vault), "--cor", "--kuru", "--depo", _depo_yolu(tmp_path)]) == 0
        assert FakeLLM.cagrilar == 0

    def test_cor_akisi_kaydeder(self, tmp_path, capsys):
        vault = _vault(tmp_path)
        rc = cli.main(["uret", str(vault), "--cor", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN])
        out = capsys.readouterr().out
        assert rc == 0 and FakeLLM.cagrilar == 1
        assert "eklenen kart: 1" in out
        assert "Üretilen soru" not in out  # kart metni yazılmaz
        assert len(Depo(Path(_depo_yolu(tmp_path))).kartlar) == 1

    def test_llm_hatasi_3_ve_kismi_kayit(self, tmp_path, capsys):
        vault = _vault(tmp_path)
        FakeLLM.mod = "hata"
        rc = cli.main(["uret", str(vault), "--cor", "--depo", _depo_yolu(tmp_path)])
        assert rc == 3
        assert "UYARI" in capsys.readouterr().err

    def test_vault_yok_2(self, tmp_path, capsys):
        assert cli.main(["uret", str(tmp_path / "yok"), "--depo", _depo_yolu(tmp_path)]) == 2
        assert "Hata" in capsys.readouterr().err

    def test_loopback_disi_cor_url_2(self, tmp_path, monkeypatch, capsys):
        from tekrar import llm

        monkeypatch.undo()  # gerçek istemci: konak denetimi çalışmalı
        vault = _vault(tmp_path)
        rc = cli.main(["uret", str(vault), "--cor", "--cor-url", "http://evil.example:8787",
                       "--depo", _depo_yolu(tmp_path)])
        assert rc == 2
        err = capsys.readouterr().err
        assert "Hata" in err and "Traceback" not in err
        assert llm.LLMError  # içe aktarma kontrolü


class TestSor:
    def test_onizleme_ilerletmez(self, tmp_path, capsys):
        _kart_ekle(tmp_path)
        assert cli.main(["sor", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN]) == 0
        out = capsys.readouterr().out
        assert "1. S" in out and out.count("?") == 2  # aynı kaynaktan en çok 2 kart
        assert all(k.kutu == 0 for k in Depo(Path(_depo_yolu(tmp_path))).kartlar)

    def test_vade_yoksa(self, tmp_path, capsys):
        assert cli.main(["sor", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN]) == 0
        assert "Bugün tekrar yok." in capsys.readouterr().out

    def test_kaydet_ilerletir(self, tmp_path):
        _kart_ekle(tmp_path)
        cli.main(["sor", "--kaydet", "--adet", "2", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN])
        kutular = sorted(k.kutu for k in Depo(Path(_depo_yolu(tmp_path))).kartlar)
        assert kutular == [0, 1, 1]

    def test_telegram_basari_ilerletir(self, tmp_path, monkeypatch):
        _kart_ekle(tmp_path)
        gonderilen = []
        monkeypatch.setattr(telegram, "gonder", lambda m, *a, **k: gonderilen.append(m) or True)
        rc = cli.main(["sor", "--telegram", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN])
        assert rc == 0 and len(gonderilen) == 1 and "||C" in gonderilen[0]
        # aynı kaynaktan en çok 2 kart gönderilir ve yalnız onlar ilerler
        assert sorted(k.kutu for k in Depo(Path(_depo_yolu(tmp_path))).kartlar) == [0, 1, 1]

    def test_telegram_basarisiz_ilerletmez_4(self, tmp_path, monkeypatch, capsys):
        _kart_ekle(tmp_path)
        monkeypatch.setattr(telegram, "gonder", lambda *a, **k: False)
        rc = cli.main(["sor", "--telegram", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN])
        assert rc == 4
        assert "gönderilemedi" in capsys.readouterr().err
        assert all(k.kutu == 0 for k in Depo(Path(_depo_yolu(tmp_path))).kartlar)


class TestZorVeDurum:
    def test_zor(self, tmp_path, capsys):
        depo = _kart_ekle(tmp_path, 1)
        kart_id = depo.kartlar[0].id
        assert cli.main(["zor", kart_id, "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN]) == 0
        assert Depo(Path(_depo_yolu(tmp_path))).kartlar[0].zor_sayisi == 1
        assert "yarın tekrar" in capsys.readouterr().out

    def test_zor_bulunamadi_1(self, tmp_path, capsys):
        assert cli.main(["zor", "yok", "--depo", _depo_yolu(tmp_path)]) == 1
        assert "bulunamadı" in capsys.readouterr().err

    def test_durum(self, tmp_path, capsys):
        _kart_ekle(tmp_path)
        assert cli.main(["durum", "--depo", _depo_yolu(tmp_path), "--bugun", BUGUN]) == 0
        out = capsys.readouterr().out
        assert "Toplam kart: 3" in out and "Vadesi gelen: 3" in out and "kutu 0: 3" in out

    def test_bozuk_depo_2_traceback_yok(self, tmp_path, capsys):
        Path(_depo_yolu(tmp_path)).write_text("{bozuk", encoding="utf-8")
        assert cli.main(["durum", "--depo", _depo_yolu(tmp_path)]) == 2
        err = capsys.readouterr().err
        assert "Hata" in err and "Traceback" not in err

    def test_gecersiz_tarih_2(self, tmp_path, capsys):
        assert cli.main(["durum", "--depo", _depo_yolu(tmp_path), "--bugun", "yarin"]) == 2
