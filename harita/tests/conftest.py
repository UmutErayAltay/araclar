"""Ortak test yardımcıları.

Tüm not içerikleri KURGUSALDIR; gerçek vault'tan hiçbir veri testlere girmez.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

from harita.index import indeksle

# pytest pythonpath=["."] ayarını kullanmadan da çalışabilsin.
KOK = Path(__file__).resolve().parents[1]
if str(KOK) not in sys.path:
    sys.path.insert(0, str(KOK))


def yaz(vault: Path, goreli: str, icerik: str) -> Path:
    """Kurusal bir not yazar (klasörleri gerekirse oluşturur)."""
    yol = vault / goreli
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(icerik, encoding="utf-8")
    return yol


def vault_hashleri(vault: Path) -> dict[str, str]:
    """Vault'taki TÜM dosyaların SHA256'sı (salt-okunurluk kanıtı)."""
    return {
        yol.relative_to(vault).as_posix(): hashlib.sha256(yol.read_bytes()).hexdigest()
        for yol in sorted(vault.rglob("*"))
        if yol.is_file()
    }


@pytest.fixture
def mini_vault(tmp_path: Path) -> Path:
    """Kurusal mini-vault: Türkçe karakter, emoji klasör, takma ad, kırık link, gömülü."""
    vault = tmp_path / "vault"
    vault.mkdir()

    yaz(
        vault,
        "🧠 Bilgi/ızgara-notu.md",
        """---
title: Izgara Ağı Hakkında
aliases: [ızgara, grid notu, "Izgara, ağ"]
tags: [ağ, gizlilik, proje]
---
# Başlık Satırı

Izgara [[ızgara-notu#Bölüm|görünen ad]] ve [[bilinmeyen-not]] bağlantıları.

![[gömülü-görsel]]

Satır içi #gizlilik etiketi burada. Değil #123 numara değil.

```
Kod: [[sahte-link]] ve #sahte-etiket
```

`[[sahte-satir-kod]]` de sayılmaz.
""",
    )
    yaz(
        vault,
        "📁 Klasör/derin-not.md",
        """---
title: Derin Not
tags: [ağ]
---
# Derin Not

Bir üst klasör notuna: [[ızgara-notu]]
Emoji klasörden: [[../Bilgi/ızgara-notu]]
""",
    )
    yaz(
        vault,
        "gizlilik-sırları.md",
        """---
title: Gizlilik Sırları
---
# Gizlilik Sırları

Bu satır sızdırabilir: sk-abcdefghijklmnopqrstuvwxyz123456
password: gizli-sifre
API_KEY = 1234567890abcdef
-----BEGIN RSA PRIVATE KEY-----

Bu satır güvenli: flask-uygulama-adi burada geçiyor.
""",
    )
    yaz(vault, "bozuk-frontmatter.md", """---
title: "Kapanmayan tırnak
tags: [a, b
---
# Bozuk

Bu metinde [[ızgara-notu]] geçiyor.
""")
    yaz(vault, "📁 Klasör/ayrilmis-not.md", "# Ayrılış Notu\n\n#ayrilmis etiketi\n")
    yaz(vault, "ozet.md", """---
title: Özet
---
Yönlendirme: [[gömülü-görsel]] ve [[ızgara]]
""")
    return vault


def yetim_vault(kok: Path) -> Path:
    """Yalnız notların "gerçek yetim / yok sayılabilir" ayrımını sınayan vault.

    Gerçek yetim: `proje/plan.md` ve `kose/not.md` (alt klasör, hiç bağlantı yok).
    Yok sayılabilir: `daily/` günlüğü, kök dosyaları (`README`, `CLAUDE`).
    `serbest-not.md` link ALDIĞI için yetim değildir — ayrımın sınır burada.
    """
    vault = kok / "yetim-vault"
    vault.mkdir(parents=True, exist_ok=True)
    yaz(vault, "bagli-not.md", "# Bağlı Not\n[[serbest-not]]\n")
    yaz(vault, "serbest-not.md", "# Serbest Not\n")
    yaz(vault, "README.md", "# README\n")
    yaz(vault, "CLAUDE.md", "# CLAUDE\n")
    yaz(vault, "daily/2026-01-01.md", "# Günlük\n")
    yaz(vault, "proje/plan.md", "# Plan\n")
    yaz(vault, "kose/not.md", "# Köşe Not\n")
    return vault


@pytest.fixture
def yetim_vault_fixture(tmp_path: Path) -> Path:
    """Pytest fixture sarmalayıcısı (e2e testleri doğrudan da kurabilir)."""
    return yetim_vault(tmp_path)


# Gerçek kullanıcı verisi sızmaması için XSS yükleri kurgusal; hiçbir gerçek
# yol, e-posta veya anahtar içermez.
XSS_BASLIK = "<script>window.__xss=1</script>"
XSS_BASLIK2 = '"><img src=x onerror=window.__xss2=1>'
# Öyle bir NOT OLMAYAN kırık link yükü: `/kirik` tablosunda kaçışlı basılır.
XSS_HEDEF = "<b>hic-boyle-not</b>"


@pytest.fixture
def xss_vault(tmp_path: Path) -> Path:
    """Başlıkları saldırı yükü içeren kurgusal vault (XSS testleri için).

    Kaçış yüzeyleri:
      * `kutu/kaynak.md` / `kutu/kaynak2.md`: kirli notlara link VERİR, bu yüzden
        bağlantısız kalmazlar ve başlıkları HTML'e girmez.
      * Gövde satırındaki düz `[[XSS_HEDEF]]` yükü: öyle bir not YOKTUR, bu
        yüzden GERÇEK kırık linktir ve `/kirik` tablosunda kaçışlı basılır.
      * `kutu/temiz-not.md`: hiç link vermeyen tek not — `/yetim` listesinde
        KENDİ bağlantısı olmayan not başlığı olarak görünür (ayrım testi).
    """
    vault = tmp_path / "xss-vault"
    vault.mkdir()
    yaz(vault, f"kutu/{XSS_BASLIK}.md", f"---\ntitle: {XSS_BASLIK}\n---\n# Zararli\n")
    yaz(vault, f"kutu/{XSS_BASLIK2}.md", f"---\ntitle: {XSS_BASLIK2}\n---\n# Zararli 2\n")
    yaz(vault, "kutu/hedef.md", "# Hedef\n")
    yaz(vault, "kutu/kaynak.md", f"---\ntitle: Kaynak\n---\nKaynak → [[{XSS_BASLIK}]]\n")
    yaz(vault, "kutu/kaynak2.md", f"---\ntitle: Kaynak 2\n---\nKaynak 2 → [[{XSS_BASLIK2}]]\n")
    # Yalnız bu satır KIRIK link üretir ve yükün kendisini `/kirik` tablosuna taşır.
    yaz(vault, "kutu/kaynak3.md", f"Kaynak 3 → [[{XSS_HEDEF}]]\n[[yok-boyle-not]]\n")
    yaz(vault, "kutu/temiz-not.md", "# Temiz Not\n")
    return vault


def sentetik_vault(kok: Path, not_sayisi: int = 1200, link_ortalamasi: int = 2) -> Path:
    """ÇALIŞMA ZAMANINDA üretilen sentetik vault (performans testi için).

    İçerik tamamen kurgusal ve sayısal; gerçek vault'tan hiçbir şey girmez.
    Klasörler 10 adet, notlar `not-0001.md` biçiminde.
    """
    vault = kok / "sentetik"
    vault.mkdir(parents=True, exist_ok=True)
    for i in range(not_sayisi):
        klasor = vault / f"konu-{i % 10:02d}"
        klasor.mkdir(parents=True, exist_ok=True)
        govde = [f"# Sentetik Not {i:05d}", "", "Bu not performans ölçümü içindir. #sentetik"]
        for k in range(link_ortalamasi):
            hedef = (i * 7 + k * 13 + 1) % not_sayisi
            govde.append(f"Bağlantı: [[not-{hedef:05d}]]")
        (klasor / f"not-{i:05d}.md").write_text("\n".join(govde) + "\n", encoding="utf-8")
    return vault


@pytest.fixture(scope="session")
def buyuk_vault(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Oturum boyunca bir kez üretilen 1200 notluk sentetik vault."""
    return sentetik_vault(tmp_path_factory.mktemp("perf"))


# ---------------------------------------------------------------------------
# Dalga D — arama (BM25) kurgusal vault'ları
# ---------------------------------------------------------------------------

GIZLI_ANAHTAR = "sk-abcdefghijklmnopqrstuvwxyz0123456789"


@pytest.fixture
def arama_vault(tmp_path: Path) -> Path:
    """Kurgusal arama vault'u: Türkçe katlama, kök/ek, alan ağırlığı, gizlilik.

    Sıralama kasıtlıdır ve TESTLERDE NEDEN O NOT ÜSTTE OLDUĞU yorumla yazılır:
      * `baslik-agirligi.md` başlığında aranan sözcük, gövdesinde değil.
      * `uzun-not.md` aynı terimi çok kez içerir ama çok uzundur (`b` cezası).
      * `gizli.md` gizli satır içerir — indeksde ve alıntıda ASLA görünmez.
    """
    vault = tmp_path / "arama-vault"
    vault.mkdir()
    yaz(
        vault,
        "proje/guvenlik.md",
        """---
title: Güvenlik Sırları
tags: [gizlilik, proje]
---
# Güvenlik Sırları

Güvenlik politikası burada. Borsa modeli başarısız oldu.

Bu satır sızdırabilir: sk-abcdefghijklmnopqrstuvwxyz0123456789
password: gizli-sifre
""",
    )
    yaz(
        vault,
        "finans/borsa.md",
        """---
title: Borsa Analizi
aliases: [borsa modeli]
tags: [finans]
---
# Borsa Analizi

Borsanın verisi bozuk. Borsada işlem hacmi düştü.
""",
    )
    yaz(
        vault,
        "isik/isparta.md",
        """---
title: IŞIK Projesi
---
# IŞIK Projesi

Isparta ışık ölçümü yapıldı. Isik haritası çizildi.
""",
    )
    # Aynı terimi ÇOK kez içeren UZUN not: `b` cezasıyla geriye düşmeli.
    yaz(
        vault,
        "uzun-not.md",
        """---
title: Uzun Not
---
# Uzun Not

""" + ("güvenlik güvenlik güvenlik güvenlik güvenlik. " * 12)
        + "\nGüvenlik cümlesi burada biter.\n",
    )
    yaz(vault, "proje/plan.md", "---\ntitle: Plan\n---\n# Plan\n\nGüvenlik planı ve borsa planı.\n")
    # Hariç tutulan klasördeki not: sonuçta GÖRÜNMEMELİ.
    yaz(vault, "receipts/alis-notu.md", "# Alış Notu\n\nGüvenlik özel notu.\n")
    return vault


@pytest.fixture
def arama_db(arama_vault: Path, tmp_path: Path) -> Path:
    """`arama_vault` indekslenmiş DB (arama tabloları dahil)."""
    db = tmp_path / "arama.db"
    indeksle(arama_vault, db)
    return db
