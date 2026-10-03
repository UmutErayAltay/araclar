"""cli: denetim kapısı yapılandırmadaki `sahip.eposta` adresini bulgu saymaz.

Sayfa içeriği `html.render` sahte veriyle üretilir: test yalnız kapının
`izinli_eposta` davranışını ölçer, alanın HTML'e yansımasını değil.
"""

from __future__ import annotations

import json
from pathlib import Path

from portfolyo import cli, denetim

SAHIP = {"ad": "Test", "unvan": "Dev", "github": "testuser", "hakkinda": "Merhaba."}
REPO = {"ad": "demo", "herkese_acik": True}


def _ayar_yaz(tmp_path: Path, sahip: dict, repolar: list[dict] | None = None) -> Path:
    veri = {"sahip": {**SAHIP, **sahip}, "repolar": repolar or [REPO]}
    yol = tmp_path / "p.json"
    yol.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    return yol


def test_denetle_yapilandirmadaki_eposta_bulgu_degil():
    sayfalar = {"index.html": "<p>umut@example.com</p>"}
    assert cli._denetle(sayfalar, "umut@example.com") == []
    bulgular = cli._denetle(sayfalar, "baskasi@example.com")
    assert [(b.tur, b.ornek) for _, b in bulgular] == [("eposta", "umut…")]
    assert cli._denetle(sayfalar) == bulgular  # parametresiz çağrı eski davranış


def test_denetle_baska_eposta_hala_bulgu():
    sayfalar = {"index.html": "<p>umut@example.com ve baska@example.com</p>"}
    bulgular = cli._denetle(sayfalar, "umut@example.com")
    assert [(b.tur, b.ornek) for _, b in bulgular] == [("eposta", "bask…")]


def test_denetim_tara_izinli_eposta_dogrudan():
    assert denetim.tara("a umut@x.com", ["umut@x.com"]) == []
    assert [b.tur for b in denetim.tara("a umut@x.com", ["baska@x.com"])] == ["eposta"]


def _sahte_eposta_sayfasi(monkeypatch):
    """index.html: sahip e-postası + repo açıklaması (gerçek render'ın yaptığı gibi)."""
    def render(ayar, veriler, bugun, yazilar, **kw):
        return "".join(f"<p>{ayar.sahip.eposta}</p><p>{r.aciklama}</p>" for r in ayar.repolar)

    monkeypatch.setattr(cli.html, "render", render)


def test_uret_yapilandirmadaki_eposta_sayfada_gecince_0(tmp_path, monkeypatch):
    _sahte_eposta_sayfasi(monkeypatch)
    ayar = _ayar_yaz(tmp_path, {"eposta": "umut@example.com"})
    assert cli.main(["uret", str(ayar), "--cikti", str(tmp_path / "s")]) == 0


def test_uret_baska_eposta_4_ve_hicbir_sey_yazilmaz(tmp_path, monkeypatch, capsys):
    _sahte_eposta_sayfasi(monkeypatch)
    ayar = _ayar_yaz(tmp_path, {"eposta": "umut@example.com"},
                     [{**REPO, "aciklama": "baska@example.com"}])
    cikti = tmp_path / "s2"
    assert cli.main(["uret", str(ayar), "--cikti", str(cikti)]) == 4
    assert not cikti.exists()
    err = capsys.readouterr().err
    assert err.count("[eposta]") == 1  # yalnız başka adres bulgu; kendi adresi sayılmadı
    assert "baska@" not in err  # ham adres sızmaz (maskeli)


def test_uret_eposta_alani_yokken_kapi_eskisi_gibi(tmp_path, monkeypatch):
    """`eposta` verilmediyse sayfadaki her e-posta bulgu (izinli liste boş)."""
    _sahte_eposta_sayfasi(monkeypatch)
    ayar = _ayar_yaz(tmp_path, {}, [{**REPO, "aciklama": "umut@example.com"}])
    assert cli.main(["uret", str(ayar), "--cikti", str(tmp_path / "s3")]) == 4
    assert not (tmp_path / "s3").exists()


def test_kontrol_ciktisi_degismedi(tmp_path, capsys):
    assert cli.main(["kontrol", str(_ayar_yaz(tmp_path, {"eposta": "umut@example.com"}))]) == 0
    assert "Yapılandırma geçerli: 1 repo" in capsys.readouterr().out