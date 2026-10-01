"""portfolyo.denetim testleri."""

from __future__ import annotations

import pytest

from portfolyo.denetim import Bulgu, tara


class TestTara:
    """tara() fonksiyonu testleri."""

    def test_temiz_metin_bos_donus(self):
        """Temiz metinde boş liste dönmeli."""
        assert tara("Merhaba dünya, bu temiz bir metin.") == []

    def test_api_anahtari_pozitif(self):
        """OpenAI API anahtarı tespit edilmeli."""
        metin = "api_key = 'sk-abcdefghijklmnopqrstuvwxyz123456'"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "api-anahtari"
        assert bulgular[0].ornek.startswith("sk-a")
        assert bulgular[0].ornek.endswith("…")

    def test_jwt_pozitif(self):
        """JWT token tespit edilmeli."""
        metin = "token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dGhpcyBpcyBhIHRlc3Q'"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "jwt"
        assert bulgular[0].ornek.startswith("eyJh")

    def test_aws_pozitif(self):
        """AWS access key ID tespit edilmeli."""
        metin = "AKIAIOSFODNN7EXAMPLE"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "aws"
        assert bulgular[0].ornek == "AKIA…"

    def test_github_token_pozitif(self):
        """GitHub token tespit edilmeli (ghp_, gho_, ghu_, ghs_, ghr_)."""
        for prefix in ("ghp_", "gho_", "ghu_", "ghs_", "ghr_"):
            metin = f"token = '{prefix}{'a' * 30}'"
            bulgular = tara(metin)
            assert len(bulgular) == 1, f"Prefix {prefix} tespit edilemedi"
            assert bulgular[0].tur == "github-token"

    def test_telegram_token_pozitif(self):
        """Telegram bot token tespit edilmeli."""
        metin = "bot_token = '123456789:ABCdefGHIjklMNOpqrSTUvwxYZ1234567890'"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "telegram-token"

    def test_ozel_anahtar_pozitif(self):
        """Private key başlığı tespit edilmeli."""
        metin = "-----BEGIN RSA PRIVATE KEY-----"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "ozel-anahtar"

    def test_yerel_yol_pozitif(self):
        """Yerel dosya yolları tespit edilmeli."""
        for yol in (
            "/home/umut/proje",
            "/Users/umut/proje",
            "C:\\Users\\umut\\proje",
            "/root/.ssh/id_rsa",
        ):
            bulgular = tara(yol)
            assert any(b.tur == "yerel-yol" for b in bulgular), f"Yol tespit edilemedi: {yol}"

    def test_eposta_pozitif(self):
        """E-posta adresi tespit edilmeli."""
        metin = "İletişim: umut@example.com"
        bulgular = tara(metin)
        assert len(bulgular) == 1
        assert bulgular[0].tur == "eposta"
        assert bulgular[0].ornek == "umut…"

    def test_eposta_izinli_hariç(self):
        """İzinli e-posta listesi hariç tutulmalı (büyük/küçük harf duyarsız)."""
        metin = "Email: UMUT@EXAMPLE.COM ve diger@test.com"
        bulgular = tara(metin, izinli_eposta=["umut@example.com"])
        assert len(bulgular) == 1
        assert bulgular[0].ornek == "dige…"

    def test_ozel_ag_pozitif(self):
        """Özel IP aralıkları ve localhost:port tespit edilmeli."""
        for ip in (
            "10.0.0.1",
            "192.168.1.100",
            "172.16.0.5",
            "172.31.255.255",
            "localhost:3000",
            "127.0.0.1:8080",
        ):
            bulgular = tara(f"server = {ip}")
            assert any(b.tur == "ozel-ag" for b in bulgular), f"IP tespit edilemedi: {ip}"

    def test_dis_kaynak_pozitif(self):
        """Dış kaynak yüklemeleri tespit edilmeli."""
        for desen in (
            "<script src='https://evil.com/x.js'></script>",
            "<link rel='stylesheet' href='https://cdn.com/style.css'>",
            "<iframe src='https://tracker.com'></iframe>",
            "@import url('https://fonts.googleapis.com/css');",
            'url("https://cdn.com/image.png")',
            'src="https://cdn.com/script.js"',
        ):
            bulgular = tara(desen)
            assert any(b.tur == "dis-kaynak" for b in bulgular), f"Desen tespit edilemedi: {desen}"

    def test_maskeleme_calisir(self):
        """Çıktıda ham sır asla görünmemeli (sadece maske)."""
        metin = "sk-abcdefghijklmnopqrstuvwxyz123456"
        bulgular = tara(metin)
        assert bulgular[0].ornek == "sk-a…"
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(bulgular)

    def test_tekillestirme_ayni_tur_ornek(self):
        """Aynı (tur, ornek) çifti bir kez raporlanmalı."""
        sir = "sk-" + "a" * 24
        metin = f"{sir} {sir} {sir}"
        bulgular = tara(metin)
        assert len(bulgular) == 1

    def test_konum_siralamasi(self):
        """Bulgular metindeki konum sırasına göre sıralanmalı."""
        metin = "sk-" + "a" * 24 + " bbb@example.com AKIA" + "A" * 16
        bulgular = tara(metin)
        assert [b.tur for b in bulgular] == ["api-anahtari", "eposta", "aws"]


class TestBulguDataclass:
    """Bulgu dataclass testleri."""

    def test_esitlik_ve_siralama(self):
        """Bulgu eşitlik ve sıralama (order=True) çalışmalı."""
        b1 = Bulgu(tur="api-anahtari", ornek="sk-a…")
        b2 = Bulgu(tur="api-anahtari", ornek="sk-a…")
        b3 = Bulgu(tur="eposta", ornek="test…")
        assert b1 == b2
        assert b1 < b3  # tur alfabetik sıralama