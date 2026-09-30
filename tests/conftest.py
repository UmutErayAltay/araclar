"""Ortak test yardımcıları.

Tüm not içerikleri KURGUSALDIR; gerçek vault'tan hiçbir veri testlere girmez.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

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
