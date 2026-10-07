"""Bu makinede siklik gecen portlar: numara -> kisa ad.

Sadece BIR etiket sozlugu: tarama hangi servisin hangi portu tuttugunu
bilmez, bu yuzden burada bilinen portlara insan okunur bir ad verilir.
Bilinmeyen port `None` etiket alir.
"""

from __future__ import annotations

#: Bu monorepoda (ve kullanicinin localhost servislerinde) sik gorulen portlar.
ETIKETLER: dict[int, str] = {
    8787: "cor",
    8790: "kule",
    8770: "atlas",
    8780: "orkestra",
    8900: "harita",
    8795: "liman",
    3000: "grafana",
    9090: "prometheus",
    9100: "node-exporter",
    8085: "cadvisor",
    5433: "readbunny-postgres",
    5432: "postgres",
    5173: "vite",
    8000: "dev-sunucu",
    8080: "http-alt",
}


def etiket(port: int) -> str | None:
    """Portun kisa adi; bilinmiyorsa `None`."""
    return ETIKETLER.get(port)
