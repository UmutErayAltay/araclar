"""ayar modülü testleri."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from portfolyo.ayar import Ayar, AyarHatasi, Repo, Sahip, ayar_oku


class TestSahipDogrulama:
    """Sahip doğrulama testleri."""

    def test_gecerli_sahip(self):
        veri = {
            "ad": "Umut",
            "unvan": "Yazılım Geliştirici",
            "github": "umut619",
            "hakkinda": "Kod yazarım.",
        }
        sahip = Sahip(**veri)
        assert sahip.ad == "Umut"
        assert sahip.github == "umut619"

    def test_ad_zorunlu(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.ad: boş olamaz"):
            _sahip_dogrula({"ad": "", "github": "u"}, "sahip")

    def test_ad_uzunluk_80_ustu(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.ad: en fazla 80 karakter"):
            _sahip_dogrula({"ad": "x" * 81, "github": "u"}, "sahip")

    def test_ad_kontrol_karakteri(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.ad: kontrol karakteri"):
            _sahip_dogrula({"ad": "Umut\x00", "github": "u"}, "sahip")

    def test_github_deseni_gecersiz(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.github: geçersiz"):
            _sahip_dogrula({"ad": "U", "github": "umut_619"}, "sahip")

    def test_github_kontrol_karakteri(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.github: "):
            _sahip_dogrula({"ad": "U", "github": "umu\x7ft"}, "sahip")

    def test_unvan_uzunluk(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.unvan: en fazla 80"):
            _sahip_dogrula({"ad": "U", "github": "u", "unvan": "x" * 81}, "sahip")

    def test_hakkinda_uzunluk(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.hakkinda: en fazla 600"):
            _sahip_dogrula({"ad": "U", "github": "u", "hakkinda": "x" * 601}, "sahip")

    def test_hakkinda_yeni_satir_serbest(self):
        veri = {"ad": "U", "github": "u", "hakkinda": "Satır 1\nSatır 2\rSatır 3"}
        sahip = _sahip_dogrula(veri, "sahip")
        assert sahip.hakkinda == "Satır 1\nSatır 2\rSatır 3"

    def test_hakkinda_kontrol_karakteri_yasak(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.hakkinda: kontrol karakteri"):
            _sahip_dogrula({"ad": "U", "github": "u", "hakkinda": "x\x00y"}, "sahip")

    def test_taninmayan_alan(self):
        with pytest.raises(AyarHatasi, match=r"sahip\.bilinmeyen: tanınmayan alan"):
            _sahip_dogrula({"ad": "U", "github": "u", "bilinmeyen": "x"}, "sahip")


class TestRepoDogrulama:
    """Repo doğrulama testleri."""

    def test_gecerli_repo(self):
        repo = _repo_dogrula(
            {"ad": "repo1", "herkese_acik": True, "aciklama": "Açıklama"},
            "repolar[0]",
            "umut619",
            set(),
        )
        assert repo.ad == "repo1"
        assert repo.url == "https://github.com/umut619/repo1"

    def test_ad_zorunlu(self):
        with pytest.raises(AyarHatasi, match=r"repolar\[0\]\.ad: boş olamaz"):
            _repo_dogrula({"ad": "", "herkese_acik": True}, "repolar[0]", "u", set())

    def test_ad_deseni_gecersiz(self):
        with pytest.raises(AyarHatasi, match=r"repolar\[0\]\.ad: geçersiz repo adı"):
            _repo_dogrula({"ad": "repo!", "herkese_acik": True}, "repolar[0]", "u", set())

    def test_ad_tekrar(self):
        gorusulen = {"repo1"}
        with pytest.raises(AyarHatasi, match=r"tekrar eden repo adı"):
            _repo_dogrula({"ad": "repo1", "herkese_acik": True}, "repolar[0]", "u", gorusulen)

    def test_herkese_acik_tam_true_olmali(self):
        # yoksa hata
        with pytest.raises(AyarHatasi, match=r"herkese_acik: tam olarak true"):
            _repo_dogrula({"ad": "r", "herkese_acik": False}, "repolar[0]", "u", set())
        # string "true" hata
        with pytest.raises(AyarHatasi, match=r"herkese_acik: tam olarak true"):
            _repo_dogrula({"ad": "r", "herkese_acik": "true"}, "repolar[0]", "u", set())
        # None hata
        with pytest.raises(AyarHatasi, match=r"herkese_acik: tam olarak true"):
            _repo_dogrula({"ad": "r", "herkese_acik": None}, "repolar[0]", "u", set())

    def test_aciklama_uzunluk(self):
        with pytest.raises(AyarHatasi, match=r"aciklama: en fazla 300"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "aciklama": "x" * 301}, "repolar[0]", "u", set()
            )

    def test_etiketler_maks_8(self):
        with pytest.raises(AyarHatasi, match=r"etiketler: en fazla 8"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "etiketler": ["t"] * 9}, "repolar[0]", "u", set()
            )

    def test_etiket_uzunluk(self):
        with pytest.raises(AyarHatasi, match=r"etiketler\[0\]: 1-24 karakter"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "etiketler": ["x" * 25]}, "repolar[0]", "u", set()
            )

    def test_etiket_kontrol_karakteri(self):
        with pytest.raises(AyarHatasi, match=r"etiketler\[0\]: kontrol karakteri"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "etiketler": ["x\x00y"]}, "repolar[0]", "u", set()
            )

    def test_taninmayan_repo_alani(self):
        with pytest.raises(AyarHatasi, match=r"repolar\[0\]\.url: tanınmayan alan"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "url": "http://x"}, "repolar[0]", "u", set()
            )

    def test_readme_boolean_olmali(self):
        with pytest.raises(AyarHatasi, match=r"readme: boolean bekleniyor"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "readme": "evet"}, "repolar[0]", "u", set()
            )

    def test_url_turetilir_kullanicidan_alınmaz(self):
        """url config'te verilirse tanınmayan alan hatası."""
        with pytest.raises(AyarHatasi, match=r"repolar\[0\]\.url: tanınmayan alan"):
            _repo_dogrula(
                {"ad": "r", "herkese_acik": True, "url": "http://x"}, "repolar[0]", "u", set()
            )


class TestAyarOku:
    """ayar_oku fonksiyonu testleri."""

    def _yaz(self, veri: dict) -> Path:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(veri, f)
            return Path(f.name)

    def test_gecerli_tam_yapılandırma(self):
        veri = {
            "sahip": {
                "ad": "Umut",
                "unvan": "Geliştirici",
                "github": "umut619",
                "hakkinda": "Kod yazar.",
            },
            "repolar": [
                {
                    "ad": "repo1",
                    "herkese_acik": True,
                    "aciklama": "İlk repo",
                    "etiketler": ["python", "web"],
                }
            ],
        }
        yol = self._yaz(veri)
        try:
            ayar = ayar_oku(yol)
            assert isinstance(ayar, Ayar)
            assert ayar.sahip.ad == "Umut"
            assert len(ayar.repolar) == 1
            assert ayar.repolar[0].url == "https://github.com/umut619/repo1"
        finally:
            yol.unlink()

    def test_dosya_yok(self):
        with pytest.raises(AyarHatasi, match=r"Dosya bulunamadı"):
            ayar_oku(Path("/yok/boyle/bir/dosya.json"))

    def test_dosya_degil_dizin(self):
        with tempfile.TemporaryDirectory() as d:
            with pytest.raises(AyarHatasi, match=r"Dosya değil"):
                ayar_oku(Path(d))

    def test_bozuk_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{ bozuk json")
            yol = Path(f.name)
        try:
            with pytest.raises(AyarHatasi, match=r"Geçersiz JSON"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_kok_nesne_degil(self):
        veri = ["array", "değil", "obje"]
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"Kök nesne bir obje olmalı"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_taninmayan_kok_alan(self):
        veri = {"sahip": {"ad": "U", "github": "u"}, "repolar": [], "bilinmeyen": "x"}
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"bilinmeyen: tanınmayan kök alan"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_sahip_eksik(self):
        veri = {"repolar": [{"ad": "r", "herkese_acik": True}]}
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"sahip: zorunlu alan eksik"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_repolar_eksik(self):
        veri = {"sahip": {"ad": "U", "github": "u"}}
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"repolar: liste bekleniyor"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_repolar_bos(self):
        veri = {"sahip": {"ad": "U", "github": "u"}, "repolar": []}
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"repolar: en az 1 repo"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_repolar_maks_24(self):
        veri = {
            "sahip": {"ad": "U", "github": "u"},
            "repolar": [{"ad": f"r{i}", "herkese_acik": True} for i in range(25)],
        }
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi, match=r"repolar: en fazla 24"):
                ayar_oku(yol)
        finally:
            yol.unlink()

    def test_hata_mesajlari_kullanici_degerini_kopyalamaz(self):
        """Hata mesajları yalnız repo adı + alan adı içerir, kullanıcı değerini kopyalamaz."""
        # ad alanında uzun/zararlı değer verilsin
        veri = {
            "sahip": {"ad": "U", "github": "u"},
            "repolar": [{"ad": "r", "herkese_acik": True, "aciklama": "x" * 500}],
        }
        yol = self._yaz(veri)
        try:
            with pytest.raises(AyarHatasi) as exc:
                ayar_oku(yol)
            hata = str(exc.value)
            # Hata mesajında 500 karakterlik değer KOPYALANMAMALI
            assert "x" * 100 not in hata
            # Sadece alan adı ve repo adı olmalı
            assert "repolar[0].aciklama" in hata
        finally:
            yol.unlink()


# Yardımcı fonksiyonları import et (private olduğu için modül içinden çağırıyoruz)
from portfolyo.ayar import _sahip_dogrula, _repo_dogrula