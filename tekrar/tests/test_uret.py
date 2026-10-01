"""uret.py: istem, yanıt ayrıştırma ve kart üretimi (gerçek ağ yok)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from tekrar import uret
from tekrar.kartlar import Depo
from tekrar.llm import LLMError

BUGUN = date(2026, 10, 1)


class SahteIstemci:
    def __init__(self, yanitlar):
        self.yanitlar = list(yanitlar)
        self.istemler: list[str] = []

    def complete(self, prompt: str) -> str:
        self.istemler.append(prompt)
        yanit = self.yanitlar.pop(0)
        if isinstance(yanit, Exception):
            raise yanit
        return yanit


def _vault(tmp_path: Path, notlar: dict[str, str]) -> Path:
    klasor = tmp_path / "vault" / "knowledge" / "concepts"
    klasor.mkdir(parents=True)
    for ad, icerik in notlar.items():
        (klasor / ad).write_text(icerik, encoding="utf-8")
    return tmp_path / "vault"


def _kartlar(*ciftler: tuple[str, str]) -> str:
    return json.dumps([{"soru": s, "cevap": c} for s, c in ciftler], ensure_ascii=False)


class TestYanitAyristir:
    def test_duz_json(self):
        assert uret.yanit_ayristir(_kartlar(("S?", "C"))) == [("S?", "C")]

    def test_citli_ve_metinli(self):
        yanit = "Tamam:\n```json\n" + _kartlar(("S?", "C")) + "\n```\nBu kadar."
        assert uret.yanit_ayristir(yanit) == [("S?", "C")]

    @pytest.mark.parametrize("yanit", ["", "çöp", "[bozuk", '{"soru": "a"}', "[1, 2]", "]["])
    def test_cop_bos_liste(self, yanit):
        assert uret.yanit_ayristir(yanit) == []

    def test_uzun_bos_ve_eksik_atlanir(self):
        yanit = json.dumps([
            {"soru": "x" * 201, "cevap": "c"},
            {"soru": "s", "cevap": "c" * 401},
            {"soru": "  ", "cevap": "c"},
            {"soru": "s"},
            {"soru": 5, "cevap": "c"},
            {"soru": "geçerli?", "cevap": "evet"},
        ])
        assert uret.yanit_ayristir(yanit) == [("geçerli?", "evet")]

    def test_sir_iceren_kart_atlanir(self):
        sir = "sk-" + "a" * 24
        assert uret.yanit_ayristir(_kartlar(("anahtar?", sir), ("normal?", "c"))) == [("normal?", "c")]

    def test_tekrar_ve_en_fazla(self):
        yanit = _kartlar(("a?", "1"), ("a?", "2"), ("b?", "3"), ("c?", "4"))
        assert uret.yanit_ayristir(yanit, en_fazla=2) == [("a?", "1"), ("b?", "3")]


class TestPrompt:
    def test_sinirlayici_ve_talimata_uyma(self):
        p = uret.prompt_olustur("Başlık", "gövde", 3)
        assert "<<<NOT" in p and "NOT>>>" in p
        assert "UYMA" in p
        assert "en fazla 3" in p

    def test_not_kesilir(self):
        p = uret.prompt_olustur("B", "x" * 20000)
        assert p.count("x") == uret.MAX_NOT_KARAKTER


class TestUret:
    def test_degismeyen_atlanir_degisen_eskiyi_degistirir(self, tmp_path):
        vault = _vault(tmp_path, {"a.md": "Birinci içerik", "b.md": "B içerik"})
        depo = Depo(tmp_path / "d.json")
        ist = SahteIstemci([_kartlar(("a1?", "c")), _kartlar(("b1?", "c"))])
        s1 = uret.uret(vault, depo, ist, BUGUN)
        assert (s1["islenen"], s1["eklenen_kart"]) == (2, 2)

        ist2 = SahteIstemci([])
        s2 = uret.uret(vault, depo, ist2, BUGUN)
        assert s2["islenen"] == 0 and s2["atlanan_degismemis"] == 2 and ist2.istemler == []

        (vault / "knowledge" / "concepts" / "a.md").write_text("Değişti", encoding="utf-8")
        ist3 = SahteIstemci([_kartlar(("yeni?", "c"))])
        s3 = uret.uret(vault, depo, ist3, BUGUN)
        assert s3["islenen"] == 1
        assert sorted(k.soru for k in depo.kartlar) == ["b1?", "yeni?"]  # a'nın eski kartı gitti

    def test_sir_iceren_not_cor_a_gonderilmez(self, tmp_path):
        vault = _vault(tmp_path, {"a.md": "anahtar sk-" + "a" * 30})
        ist = SahteIstemci([])
        s = uret.uret(vault, Depo(tmp_path / "d.json"), ist, BUGUN)
        assert s["atlanan_sir"] == 1 and ist.istemler == []

    def test_private_not_gonderilmez(self, tmp_path):
        vault = _vault(tmp_path, {"a.md": "---\nvisibility: private\n---\ngizli içerik"})
        ist = SahteIstemci([])
        s = uret.uret(vault, Depo(tmp_path / "d.json"), ist, BUGUN)
        assert s["islenen"] == 0 and ist.istemler == []

    def test_en_cok_not_ve_bos(self, tmp_path):
        vault = _vault(tmp_path, {"a.md": "A", "b.md": "B", "c.md": "C"})
        ist = SahteIstemci(["çöp yanıt", _kartlar(("b?", "c"))])
        s = uret.uret(vault, Depo(tmp_path / "d.json"), ist, BUGUN, en_cok_not=2)
        assert s["islenen"] == 2 and s["bos"] == 1 and s["eklenen_kart"] == 1

    def test_llm_hatasi_firlar_oncekiler_kalir(self, tmp_path):
        vault = _vault(tmp_path, {"a.md": "A", "b.md": "B"})
        depo = Depo(tmp_path / "d.json")
        ist = SahteIstemci([_kartlar(("a?", "c")), LLMError("kapalı")])
        with pytest.raises(LLMError):
            uret.uret(vault, depo, ist, BUGUN)
        assert [k.soru for k in depo.kartlar] == ["a?"]
