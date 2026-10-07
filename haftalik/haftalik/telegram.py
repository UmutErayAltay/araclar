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

TOKEN_ENV = "HAFTALIK_TELEGRAM_BOT_TOKEN"
CHAT_ENV = "HAFTALIK_TELEGRAM_CHAT_ID"
MAX_MESAJ = 4096

_ESCAPE_RE = re.compile(r'([_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.!\\])')


def kacis(metin: str) -> str:
    """Telegram MarkdownV2 için özel karakterleri kaçışlı hale getirir."""
    return _ESCAPE_RE.sub(r'\\\1', metin)


def ozet_mesajlari(metin: str, *, baslik: str = "Haftalık özet") -> list[str]:
    r"""Markdown özetini 4096 sınırına uyan MarkdownV2 mesajlarına böler.

    Biçim:
      *<kaçışlı başlık>*

      <kaçışlı özet satırları>

    Uzun özet satır BOUNDARY'DE kesilir; hiçbir mesaj MAX_MESAJ'ı aşmaz.
    Bir blok (başlık + ilk parça) tek başına sığmıyorsa o satır kısaltılır ve
    sonuna `…` eklenir. Yarım kaçış dizisi asla kalmaz.
    """
    metin = (metin or "").strip()
    if not metin:
        return []

    baslik_k = kacis(baslik)
    girinti = f"*{baslik_k}*"

    def _baslikli(paras: Sequence[str]) -> str:
        return "\n\n".join([girinti, *paras]).rstrip()

    # 1) Tam blok hâlinde sığıyorsa tek mesaj.
    tumu = _baslikli([kacis(metin)])
    if len(tumu) <= MAX_MESAJ:
        return [tumu]

    # 2) Boşluklardan böl; sığmayan parça olursa yarım kaldığı satırdan kes.
    parcalar: list[str] = []
    mevcut = ""
    for paragraf in metin.split("\n\n"):
        denenen = paragraf if not mevcut else f"{mevcut}\n\n{paragraf}"
        if len(_baslikli([kacis(denenen)])) <= MAX_MESAJ:
            mevcut = denenen
            continue
        if mevcut:
            parcalar.append(mevcut)
            mevcut = ""
        # Bu paragraf tek başına sığmıyor: satır satır doldur.
        for satir in paragraf.split("\n"):
            denenen_satir = satir if not mevcut else f"{mevcut}\n{satir}"
            if len(_baslikli([kacis(denenen_satir)])) <= MAX_MESAJ:
                mevcut = denenen_satir
                continue
            if mevcut:
                parcalar.append(mevcut)
                mevcut = ""
            parcalar.append(_kisalt(satir))
    if mevcut:
        parcalar.append(mevcut)

    # Her mesaja baslik zaten ekleniyor; icerik tasimayan parca (yalniz baslik
    # satiri) tek basina mesaj olmaya deger degil -- bos bir "ozet" mesaji birakirdi.
    dolu = [p for p in parcalar if _icerik_var(p)]
    return [_baslikli([kacis(p)]) for p in (dolu or parcalar)]


def _icerik_var(paragraf: str) -> bool:
    """Paragrafta baslik disinda gercek bir icerik satiri var mi?"""
    return any(
        satir.strip() and not satir.lstrip().startswith("#")
        for satir in paragraf.split("\n")
    )


def _kisalt(satir: str) -> str:
    """Sığmayan tek satırı `…` ile kısaltır (kaçış SONRASI uzunluğa göre)."""
    def yap(s: str) -> str:
        return f"*{kacis('Haftalık özet')}*\n\n{kacis(s)}"

    if len(yap(satir)) <= MAX_MESAJ:
        return satir
    alt, ust = 0, len(satir)
    while alt < ust:
        orta = (alt + ust + 1) // 2
        if len(yap(satir[:orta] + "…")) <= MAX_MESAJ:
            alt = orta
        else:
            ust = orta - 1
    return satir[:alt].rstrip() + "…"


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
        token: Bot token (verilmezse HAFTALIK_TELEGRAM_BOT_TOKEN ortamından alınır).
        chat_id: Hedef sohbet kimliği (verilmezse HAFTALIK_TELEGRAM_CHAT_ID ortamından).
        zaman_asimi: İstek zaman aşımı (saniye).

    Returns:
        True: 200 + {"ok": true}, False: herhangi bir hata durumunda.
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
