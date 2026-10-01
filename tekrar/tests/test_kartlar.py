"""Leitner kart deposu testleri (gerçek ev dizinine yazılmaz)."""

from __future__ import annotations

import json
import os
import stat
from datetime import date, timedelta
from pathlib import Path

import pytest

from tekrar.kartlar import ARALIKLAR, Depo, DepoHatasi

BUGUN = date(2026, 10, 1)


def _depo(tmp_path: Path) -> Depo:
    return Depo(tmp_path / "kartlar.json")


def test_araliklar_sabit() -> None:
    assert ARALIKLAR == (1, 3, 7, 14, 30, 60)


def test_dosya_yoksa_bos_depo(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    assert depo.kartlar == []
    assert not (tmp_path / "kartlar.json").exists()  # okumak yazmaz


def test_ekle_tekrarsiz_ve_id_kararli(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    ilk = depo.ekle("knowledge/concepts/a.md", "h1", [("S1?", "C1"), ("S2?", "C2")], BUGUN)
    assert [k.soru for k in ilk] == ["S1?", "S2?"]
    assert all(k.kutu == 0 and k.sonraki == BUGUN.isoformat() for k in ilk)
    tekrar = depo.ekle("knowledge/concepts/a.md", "h1", [("S1?", "başka cevap")], BUGUN)
    assert tekrar == []
    assert len(depo.kartlar) == 2
    # aynı soru başka kaynakta farklı id
    baska = depo.ekle("knowledge/concepts/b.md", "h2", [("S1?", "C")], BUGUN)
    assert len(baska) == 1 and baska[0].id != ilk[0].id
    assert len(ilk[0].id) == 12


def test_kaynak_degisti_mi_uc_durum(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    assert depo.kaynak_degisti_mi("a.md", "h1") is True  # kart yok
    depo.ekle("a.md", "h1", [("S?", "C")], BUGUN)
    assert depo.kaynak_degisti_mi("a.md", "h1") is False
    assert depo.kaynak_degisti_mi("a.md", "h2") is True


def test_kaynagi_sil(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.ekle("a.md", "h", [("1?", "c"), ("2?", "c")], BUGUN)
    depo.ekle("b.md", "h", [("3?", "c")], BUGUN)
    assert depo.kaynagi_sil("a.md") == 2
    assert [k.kaynak for k in depo.kartlar] == ["b.md"]
    assert depo.kaynagi_sil("yok.md") == 0


def test_vadesi_gelen_siralama_kaynak_siniri_ve_adet(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.ekle("a.md", "h", [("a1?", "c"), ("a2?", "c"), ("a3?", "c")], BUGUN)
    depo.ekle("b.md", "h", [("b1?", "c")], BUGUN - timedelta(days=3))
    depo.ekle("c.md", "h", [("c1?", "c")], BUGUN + timedelta(days=1))  # henüz değil
    secilen = depo.vadesi_gelen(BUGUN, 10)
    sorular = [k.soru for k in secilen]
    assert sorular[0] == "b1?"  # en eski vade önce
    assert "c1?" not in sorular  # vadesi gelmedi
    assert sum(1 for k in secilen if k.kaynak == "a.md") == 2  # kaynak başına 2
    assert len(depo.vadesi_gelen(BUGUN, 2)) == 2
    assert depo.vadesi_gelen(BUGUN, 0) == []
    assert depo.vadesi_gelen(BUGUN, -3) == []


def test_goruldu_arali_ilerler(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    (kart,) = depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    depo.goruldu(kart.id, BUGUN)
    assert kart.kutu == 1
    assert kart.sonraki == (BUGUN + timedelta(days=1)).isoformat()
    assert kart.son_gosterim == BUGUN.isoformat()
    depo.goruldu(kart.id, BUGUN)
    assert kart.kutu == 2
    assert kart.sonraki == (BUGUN + timedelta(days=3)).isoformat()


def test_goruldu_son_basamakta_kalir_ve_60_gun(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    (kart,) = depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    for _ in range(10):
        depo.goruldu(kart.id, BUGUN)
    assert kart.kutu == len(ARALIKLAR) - 1
    assert kart.sonraki == (BUGUN + timedelta(days=60)).isoformat()


def test_goruldu_bilinmeyen_id_sessiz(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.goruldu("yok", BUGUN)  # raise etmemeli


def test_zor_sifirlar(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    (kart,) = depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    for _ in range(3):
        depo.goruldu(kart.id, BUGUN)
    assert depo.zor(kart.id, BUGUN) is True
    assert kart.kutu == 0
    assert kart.sonraki == (BUGUN + timedelta(days=1)).isoformat()
    assert kart.zor_sayisi == 1
    assert depo.zor("yok", BUGUN) is False


def test_kaydet_yukle_round_trip(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.ekle("a.md", "h", [("Türkçe soru ğüşiöç?", "Cevap İı")], BUGUN)
    depo.goruldu(depo.kartlar[0].id, BUGUN)
    depo.kaydet()
    yeni = _depo(tmp_path)
    assert yeni.kartlar == depo.kartlar
    assert yeni.kartlar[0].soru == "Türkçe soru ğüşiöç?"


@pytest.mark.skipif(os.name != "posix", reason="izin bitleri yalnız POSIX")
def test_kaydet_izin_0600_ve_tmp_kalmaz(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    depo.kaydet()
    dosya = tmp_path / "kartlar.json"
    assert stat.S_IMODE(dosya.stat().st_mode) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["kartlar.json"]


def test_kaydet_ust_klasoru_olusturur(tmp_path: Path) -> None:
    depo = Depo(tmp_path / "yeni" / "alt" / "kartlar.json")
    depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    depo.kaydet()
    assert (tmp_path / "yeni" / "alt" / "kartlar.json").is_file()


GECERLI_KART = {
    "id": "abc", "kaynak": "a.md", "kaynak_sha256": "h", "soru": "GIZLI-SORU?",
    "cevap": "GIZLI-CEVAP", "kutu": 0, "sonraki": "2026-10-01",
    "son_gosterim": None, "zor_sayisi": 0,
}


@pytest.mark.parametrize(
    "icerik",
    [
        "{bozuk json",
        "[]",
        json.dumps({"surum": 2, "kartlar": []}),
        json.dumps({"surum": 1, "kartlar": "liste degil"}),
        json.dumps({"surum": 1, "kartlar": [5]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "kutu": "0"}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "kutu": 99}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "kutu": -1}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "kutu": True}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "sonraki": "yarin"}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "son_gosterim": "dün"}]}),
        json.dumps({"surum": 1, "kartlar": [{**GECERLI_KART, "soru": 42}]}),
        json.dumps({"surum": 1, "kartlar": [{k: v for k, v in GECERLI_KART.items() if k != "cevap"}]}),
    ],
)
def test_bozuk_depo_hatasi_dosya_degismez_icerik_sizmaz(tmp_path: Path, icerik: str) -> None:
    dosya = tmp_path / "kartlar.json"
    dosya.write_text(icerik, encoding="utf-8")
    with pytest.raises(DepoHatasi) as hata:
        Depo(dosya)
    assert "GIZLI" not in str(hata.value)
    assert str(dosya) in str(hata.value)
    assert dosya.read_text(encoding="utf-8") == icerik  # asla ezilmez


def test_gecerli_kart_yuklenir(tmp_path: Path) -> None:
    dosya = tmp_path / "kartlar.json"
    dosya.write_text(json.dumps({"surum": 1, "kartlar": [GECERLI_KART]}), encoding="utf-8")
    depo = Depo(dosya)
    assert depo.kartlar[0].id == "abc"
    assert depo.kartlar[0].son_gosterim is None


def test_ozet(tmp_path: Path) -> None:
    depo = _depo(tmp_path)
    depo.ekle("a.md", "h", [("1?", "c"), ("2?", "c")], BUGUN)
    depo.ekle("b.md", "h", [("3?", "c")], BUGUN + timedelta(days=5))
    depo.goruldu(depo.kartlar[0].id, BUGUN)
    ozet = depo.ozet(BUGUN)
    assert ozet["toplam"] == 3
    assert ozet["vadesi_gelen"] == 1  # biri ilerledi, biri gelecekte
    assert ozet["kutular"] == {0: 2, 1: 1}
    assert ozet["kaynak_sayisi"] == 2


def test_varsayilan_tekrar_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEKRAR_DIR", str(tmp_path))
    depo = Depo.varsayilan()
    depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    depo.kaydet()
    assert (tmp_path / "kartlar.json").is_file()


def test_varsayilan_ev_dizini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEKRAR_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    depo = Depo.varsayilan()
    depo.ekle("a.md", "h", [("S?", "C")], BUGUN)
    depo.kaydet()
    assert (tmp_path / ".tekrar" / "kartlar.json").is_file()
