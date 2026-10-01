"""Telegram bot mesaj gönderimi (MarkdownV2).

Asla raise etmez; token/chat_id hiçbir yere (log, hata mesajı, stderr) sızmaz.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Sequence

TOKEN_ENV = "TEKRAR_TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TEKRAR_TELEGRAM_CHAT_ID"
MAX_MESAJ = 4096

_ESCAPE_RE = re.compile(r'([_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.!\\])')


def kacis(metin: str) -> str:
    """Telegram MarkdownV2 için özel karakterleri kaçışlı hale getirir."""
    return _ESCAPE_RE.sub(r'\\\1', metin)


def kart_mesaji(
    ciftler: Sequence[tuple[str, str]],
    baslik: str = "Bugünün tekrar kartları",
) -> str:
    r"""Tekrar kartlarından MarkdownV2 mesajı üretir.

    Biçim:
      *<kaçışlı başlık>*

      1\. <kaçışlı soru>
      ||<kaçışlı cevap>||

      2\. <kaçışlı soru>
      ||<kaçışlı cevap>||

    Toplam uzunluk MAX_MESAJ'ı aşmaz; sığmayan kartlar çıkarılır.
    En az bir kart sığmıyorsa o kartın cevabı kısaltılır ve sonuna `…` eklenir.
    Yarım kaçış dizisi asla kalmaz.
    """
    if not ciftler:
        return ""

    baslik_k = kacis(baslik)
    satirlar = [f"*{baslik_k}*", ""]

    def _olustur_mesaj(kartlar: Sequence[tuple[str, str]], son_ek: str = "") -> str:
        parcalar = [f"*{baslik_k}*", ""]
        for i, (soru, cevap) in enumerate(kartlar, 1):
            soru_k = kacis(soru)
            cevap_k = kacis(cevap + son_ek)
            parcalar.append(f"{i}\\. {soru_k}")
            parcalar.append(f"||{cevap_k}||")
            parcalar.append("")
        return "\n".join(parcalar).rstrip()

    mesaj = _olustur_mesaj(ciftler)
    if len(mesaj) <= MAX_MESAJ:
        return mesaj

    # Sığmayan kartları teker teker çıkar
    for i in range(len(ciftler), 0, -1):
        alt_kume = ciftler[:i]
        mesaj = _olustur_mesaj(alt_kume)
        if len(mesaj) <= MAX_MESAJ:
            return mesaj

    # Tek kart bile sığmıyor: kaçış karakterleri uzunluğu artırdığı için KAÇIŞ SONRASI
    # uzunluğa göre ikili aramayla önce cevabı, o da yetmezse soruyu kısalt.
    soru, cevap = ciftler[0]

    def yap(s_: str, c_: str) -> str:
        return f"*{baslik_k}*\n\n1\\. {kacis(s_)}\n||{kacis(c_)}||"

    def en_uzun(n_max: int, uygun) -> int:
        alt, ust = 0, n_max
        while alt < ust:
            orta = (alt + ust + 1) // 2
            if uygun(orta):
                alt = orta
            else:
                ust = orta - 1
        return alt

    n = en_uzun(len(cevap), lambda k: len(yap(soru, cevap[:k] + "…")) <= MAX_MESAJ)
    if len(yap(soru, cevap[:n] + "…")) <= MAX_MESAJ:
        return yap(soru, cevap[:n] + "…")
    m = en_uzun(len(soru), lambda k: len(yap(soru[:k] + "…", "…")) <= MAX_MESAJ)
    return yap(soru[:m] + "…", "…")


def _token_gecerli(token: str) -> bool:
    return bool(re.match(r'^\d{6,12}:[A-Za-z0-9_-]{30,}$', token))


def _chat_id_gecerli(chat_id: str) -> bool:
    return bool(re.match(r'^-?\d{1,20}$', chat_id))


def gonder(
    metin: str,
    token: str | None = None,
    chat_id: str | None = None,
    *,
    zaman_asimi: float = 10.0,
) -> bool:
    """Telegram'a mesaj gönderir.

    Args:
        metin: Gönderilecek metin (MarkdownV2).
        token: Bot token (verilmezse TEKRAR_TELEGRAM_BOT_TOKEN ortamından alınır).
        chat_id: Hedef sohbet kimliği (verilmezse TEKRAR_TELEGRAM_CHAT_ID ortamından alınır).
        zaman_asimi: İstek zaman aşımı (saniye).

    Returns:
        True: 200 + {"ok": true}, False: herhangi bir hata durumunda (ağ hatası,
        zaman aşımı, HTTP hatası, JSON hatası, beklenmedik istisna).
    """
    token = token or os.environ.get(TOKEN_ENV)
    chat_id = chat_id or os.environ.get(CHAT_ENV)

    if not token or not _token_gecerli(token):
        logging.warning("Telegram: geçersiz veya eksik token")
        return False
    if not chat_id or not _chat_id_gecerli(chat_id):
        logging.warning("Telegram: geçersiz veya eksik chat_id")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    veri = {
        "chat_id": chat_id,
        "text": metin,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    veri_json = json.dumps(veri).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=veri_json,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=zaman_asimi) as yanit:
            if yanit.status != 200:
                logging.warning("Telegram: HTTP %s", yanit.status)
                return False
            govde = yanit.read().decode("utf-8")
            try:
                sonuc = json.loads(govde)
            except json.JSONDecodeError:
                logging.warning("Telegram: bozuk JSON yanıtı")
                return False
            return bool(sonuc.get("ok"))
    except urllib.error.HTTPError as e:
        logging.warning("Telegram: HTTP hata %s", e.code)
        return False
    except urllib.error.URLError:
        logging.warning("Telegram: ağ hatası")
        return False
    except TimeoutError:
        logging.warning("Telegram: zaman aşımı")
        return False
    except Exception:
        logging.warning("Telegram: beklenmedik hata")
        return False