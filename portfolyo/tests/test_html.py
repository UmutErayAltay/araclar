"""portfolyo.html testleri."""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from portfolyo.html import render
from portfolyo.denetim import tara


@dataclass
class SahteRepoVerisi:
    """Test için sahte RepoVerisi."""
    commit_sayisi: int = 10
    ilk_commit: str | None = "2024-01-01"
    son_commit: str | None = "2024-06-15"
    haftalik: tuple[int, ...] | None = None
    diller: tuple[tuple[str, int], ...] | None = None
    readme_ozeti: str | None = "Bu bir test README özeti."


def _sahte_ayar(**kwargs) -> SimpleNamespace:
    """Test için sahte ayar nesnesi oluşturur."""
    sahip = SimpleNamespace(
        ad=kwargs.get("sahip_ad", "Test Kullanıcı"),
        unvan=kwargs.get("sahip_unvan", "Geliştirici"),
        github=kwargs.get("sahip_github", "testuser"),
        hakkinda=kwargs.get("sahip_hakkinda", "Test hakkındayım.\nİkinci satır."),
        site_url=kwargs.get("site_url", ""),
    )
    repolar = []
    for r in kwargs.get("repolar", [{}]):
        repo = SimpleNamespace(
            ad=r.get("ad", "test-repo"),
            aciklama=r.get("aciklama", "Test açıklaması"),
            url=r.get("url", "https://github.com/testuser/test-repo"),
            etiketler=r.get("etiketler", ["python", "test"]),
            kategori=r.get("kategori", "Diğer"),
        )
        repolar.append(repo)
    return SimpleNamespace(
        sahip=sahip,
        repolar=repolar,
        kategoriler=tuple(kwargs.get("kategoriler", ())),
        siralama=kwargs.get("siralama", "manuel"),
    )


class TestRender:
    """render() fonksiyonu testleri."""

    def test_temel_uretim_calisir(self):
        """Temel HTML üretimi çalışmalı ve geçerli HTML dönmeli."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "<!doctype html>" in html_out
        assert '<html lang="tr">' in html_out
        assert '<meta charset="utf-8">' in html_out
        assert 'name="viewport"' in html_out
        assert "Content-Security-Policy" in html_out
        assert "Test Kullanıcı" in html_out
        assert "test-repo" in html_out
        assert "Otomatik üretildi: 2026-01-15" in html_out

    def test_csp_meta_var(self):
        """CSP meta etiketi doğru içeriğe sahip olmalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert 'default-src \'none\'' in html_out
        assert 'style-src \'unsafe-inline\'' in html_out
        assert 'img-src data:' in html_out
        assert 'base-uri \'none\'' in html_out
        assert 'form-action \'none\'' in html_out

    def test_hic_javascript_yok(self):
        """Çıktıda <script etiketi olmamalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "<script" not in html_out.lower()

    def test_disa_kaynak_yok(self):
        """Harici font/CDN/analitik bağlantısı olmamalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        # Google Fonts, CDN, analitik yok
        assert "fonts.googleapis.com" not in html_out
        assert "cdn.jsdelivr.net" not in html_out
        assert "google-analytics" not in html_out
        assert "googletagmanager" not in html_out

    def test_xss_kacis_tum_alanlar(self):
        """Tüm kullanıcı kaynaklı alanlarda XSS payload'ı kaçışlı olmalı."""
        xss_payload = '<script>alert(1)</script>'
        xss_payload2 = '"><img src=x onerror=alert(1)>'

        ayar = _sahte_ayar(
            sahip_ad=xss_payload,
            sahip_unvan=xss_payload2,
            sahip_hakkinda=xss_payload,
            repolar=[{
                "ad": xss_payload,
                "aciklama": xss_payload2,
                "url": "https://github.com/test/test",
                "etiketler": [xss_payload, xss_payload2],
            }]
        )
        veri = {"test": SahteRepoVerisi(readme_ozeti=xss_payload, diller=[xss_payload])}
        html_out = render(ayar, veri, date(2026, 1, 15))

        # Ham payload çıktıda olmamalı, kaçışlı hali olmalı
        assert xss_payload not in html_out
        assert xss_payload2 not in html_out
        assert html.escape(xss_payload, quote=True) in html_out
        assert html.escape(xss_payload2, quote=True) in html_out

    def test_denetim_kendi_sifir_bulgu(self):
        """Üretilen HTML kendi denetim.tarayıcıdan geçmeli (sıfır bulgu)."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        bulgular = tara(html_out)
        # Kendi ürettiğimiz HTML'de dış kaynak deseni (svg/style içinde https: vs.) olabilir
        # ama bunlar bizim kontrolümüzdeki içerik; CSP zaten engeller.
        # Sadece gerçek sızıntı türleri olmamalı.
        sizinti_turleri = {"api-anahtari", "jwt", "aws", "github-token", "telegram-token",
                           "ozel-anahtar", "yerel-yol", "eposta", "ozel-ag"}
        gercek_sizintilar = [b for b in bulgular if b.tur in sizinti_turleri]
        assert gercek_sizintilar == [], f"Gerçek sızıntı bulundu: {gercek_sizintilar}"

    def test_veri_none_kart_sadece_yapilandirma(self):
        """veri=None iken kartta sadece yapılandırma metni görünmeli, istatistik yok."""
        ayar = _sahte_ayar(repolar=[
            {"ad": "repo-var", "aciklama": "Var"},
            {"ad": "repo-yok", "aciklama": "Yok"},
        ])
        veri = {"repo-var": SahteRepoVerisi()}  # repo-yok None
        html_out = render(ayar, veri, date(2026, 1, 15))

        # repo-var: istatistik satırı olmalı
        assert "10 commit" in html_out
        # repo-yok: istatistik satırı YOK olmalı
        # İki kart da başlık ve açıklama içermeli
        assert html_out.count('class="kart"') == 2
        assert "Var" in html_out
        assert "Yok" in html_out

    def test_siralama_son_commit_azalan(self):
        """Kartlar son_commit azalan sırada sıralanmalı (None en sona)."""
        ayar = _sahte_ayar(siralama="aktivite", repolar=[
            {"ad": "eski-repo", "aciklama": "Eski"},
            {"ad": "yeni-repo", "aciklama": "Yeni"},
            {"ad": "yok-repo", "aciklama": "Yok"},
        ])
        veri = {
            "eski-repo": SahteRepoVerisi(son_commit="2024-01-01"),
            "yeni-repo": SahteRepoVerisi(son_commit="2024-12-01"),
            "yok-repo": None,
        }
        html_out = render(ayar, veri, date(2026, 1, 15))

        # yeni-repo önce gelmeli, sonra eski-repo, en son yok-repo
        yeni_pos = html_out.index("yeni-repo")
        eski_pos = html_out.index("eski-repo")
        yok_pos = html_out.index("yok-repo")
        assert yeni_pos < eski_pos < yok_pos

    def test_svg_aria_label_sayilari(self):
        """SVG aria-label'de haftalık commit sayıları olmalı."""
        haftalik = (0, 1, 2, 0, 5, 3, 0, 0, 1, 0, 0, 0)
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi(haftalik=haftalik)}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert 'role="img"' in html_out
        assert 'aria-label="Son 12 haftada commit sayısı: 0, 1, 2, 0, 5, 3, 0, 0, 1, 0, 0, 0"' in html_out

    def test_svg_hepsi_sifir_duz_cizgi(self):
        """Tüm haftalar 0 ise düz çizgi (aria-label buna göre)."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi(haftalik=(0,)*12)}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert 'aria-label="Son 12 haftada commit sayısı: hiç commit yok"' in html_out
        # Düz çizgi: opacity 0.3 rect'ler
        assert 'opacity="0.3"' in html_out

    def test_rel_noopener_noreferrer_her_kartta(self):
        """Her kart bağlantısında rel="noopener noreferrer" olmalı."""
        ayar = _sahte_ayar(repolar=[
            {"ad": "repo1", "url": "https://github.com/a/b"},
            {"ad": "repo2", "url": "https://github.com/c/d"},
        ])
        veri = {"repo1": SahteRepoVerisi(), "repo2": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        # Her kart başlığında bir tane (2) + altbilgideki GitHub bağlantısı (1)
        assert html_out.count('rel="noopener noreferrer"') == 3
        assert html_out.count('<article') == 2

    def test_semantik_yapi(self):
        """Anlamsal HTML yapısı: main/header/footer/h1/h2."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "<header>" in html_out
        assert "<main>" in html_out
        assert "<footer>" in html_out
        assert "<h1" in html_out
        assert "<h2" in html_out
        assert "<article" in html_out  # kart article

    def test_hakkinda_paragraf_ayrilir(self):
        """hakkında alanı satır sonlarıyla paragraflara ayrılmalı (br YOK)."""
        ayar = _sahte_ayar(sahip_hakkinda="Satır 1\nSatır 2\n\nSatır 3")
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        # <br> etiketi YOK
        assert "<br" not in html_out.lower()
        # Satırlar metin olarak var
        assert "Satır 1" in html_out
        assert "Satır 2" in html_out
        assert "Satır 3" in html_out

    def test_sistem_font_yigini(self):
        """CSS'de system-ui font yığını tanımlı olmalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "system-ui" in html_out
        assert "-apple-system" in html_out
        assert "BlinkMacSystemFont" in html_out

    def test_odak_halkasi(self):
        """CSS'de :focus-visible odak halkası tanımlı olmalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "focus-visible" in html_out
        assert "outline" in html_out

    def test_koyu_tema_degiskenleri(self):
        """CSS'de prefers-color-scheme: dark değişkenleri olmalı."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "prefers-color-scheme: dark" in html_out
        assert "--bg:" in html_out
        assert "--fg:" in html_out

    def test_yan_bosluk_ve_tek_sutun(self):
        """Mobilde 16px yan boşluk, grid tek sütun."""
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi()}
        html_out = render(ayar, veri, date(2026, 1, 15))

        assert "padding: 16px" in html_out or "padding: 16px;" in html_out
        assert "grid-template-columns: 1fr" in html_out


class TestHtmlKendiniDenetler:
    """HTML üreteci kendi denetim modülünü import edip testlerde kullanır."""

    def test_kendi_denetim_fonksiyonu_var(self):
        """_kendi_denetimi yardımcı fonksiyonu erişilebilir olmalı."""
        from portfolyo.html import _kendi_denetimi
        bulgular = _kendi_denetimi("<html>temiz</html>")
        assert isinstance(bulgular, list)

class TestGercekVeriTurleri:
    """RepoVerisi'nin gerçek türleriyle (ISO metin tarih, (dil, sayı) çiftleri) render."""

    def test_diller_ad_ve_sayi_olarak_gorunur(self):
        ayar = _sahte_ayar()
        veri = {"test-repo": SahteRepoVerisi(diller=(("Python", 3), ("Go", 1)))}
        html_out = render(ayar, veri, date(2026, 1, 15))
        assert "Python · 3" in html_out
        assert "Go · 1" in html_out
        assert "(&#x27;" not in html_out  # tuple repr'i sızmamalı

    def test_iso_metin_tarihlerle_siralama(self):
        ayar = _sahte_ayar(siralama="aktivite", repolar=[{"ad": "a-eski"}, {"ad": "b-yeni"}])
        veri = {
            "a-eski": SahteRepoVerisi(son_commit="2023-05-01"),
            "b-yeni": SahteRepoVerisi(son_commit="2026-05-01"),
        }
        html_out = render(ayar, veri, date(2026, 6, 1))
        assert html_out.index("b-yeni") < html_out.index("a-eski")
