"""GitHub REST API'sinden herkese açık repo verisi toplar (klon gerektirmez).

Ağ kuralları (bağlayıcı): konak SABİTTİR (`api.github.com`), yalnız GET, 15 sn zaman aşımı.
Özel (private) repo asla yayınlanmaz: yanıt `private: true` ise ya da `private` açıkça
`false` değilse veri DÖNMEZ. Hiçbir hata yükseltilmez (None döner); token hiçbir çıktıya,
hata iletisine ya da günlüğe yazılmaz.
"""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import date

from .git import RepoVerisi, _readme_ozetle

API = "https://api.github.com"
ZAMAN_ASIMI = 15
MAKS_GOVDE = 1_000_000
_JSON = "application/vnd.github+json"
_HAM = "application/vnd.github.raw"
_SAHIP_DESENI = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_REPO_DESENI = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_LINK_SON = re.compile(r'<[^>]*[?&]page=(\d+)[^>]*>\s*;\s*rel="last"')


class _Yanit:
    __slots__ = ("durum", "basliklar", "govde")

    def __init__(self, durum: int, basliklar, govde: bytes) -> None:
        self.durum, self.basliklar, self.govde = durum, basliklar, govde

    def json(self) -> object | None:
        try:
            return json.loads(self.govde.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None


def _al(yol: str, *, token: str | None, urlopen: Callable, kabul: str = _JSON) -> _Yanit | None:
    """Sabit konağa GET atar. Her hata (HTTP, ağ, zaman aşımı) → None."""
    basliklar = {"Accept": kabul, "User-Agent": "portfolyo", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        basliklar["Authorization"] = f"Bearer {token}"
    istek = urllib.request.Request(API + yol, headers=basliklar, method="GET")
    try:
        with urlopen(istek, timeout=ZAMAN_ASIMI) as r:
            if not str(r.geturl()).startswith(API + "/"):
                return None  # konak dışına yönlendirme
            return _Yanit(int(r.status), r.headers, r.read(MAKS_GOVDE))
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return None


def _tarih(deger: object) -> str | None:
    """ISO tarih-saatin gün kısmını döndürür; geçersizse None."""
    if not isinstance(deger, str) or len(deger) < 10:
        return None
    try:
        return date.fromisoformat(deger[:10]).isoformat()
    except ValueError:
        return None


def _commitler(taban: str, token, urlopen) -> tuple[int, str | None] | None:
    """(toplam commit, son commit günü); okunamazsa None."""
    y = _al(taban + "/commits?per_page=1", token=token, urlopen=urlopen)
    if y is None or y.durum != 200:
        return None
    liste = y.json()
    if not isinstance(liste, list):
        return None
    if not liste:
        return 0, None
    ilk = liste[0] if isinstance(liste[0], dict) else {}
    kayit = ilk.get("commit") if isinstance(ilk.get("commit"), dict) else {}
    kimlik = kayit.get("committer") if isinstance(kayit.get("committer"), dict) else {}
    gun = _tarih(kimlik.get("date"))
    link = y.basliklar.get("Link") if y.basliklar is not None else None
    eslesme = _LINK_SON.search(link) if isinstance(link, str) else None
    toplam = int(eslesme.group(1)) if eslesme else len(liste)
    return toplam, gun


def _haftalik(taban: str, token, urlopen, bekle) -> tuple[int, ...] | None:
    """Son 12 haftanın commit sayıları (en eski başta). 202 gelirse bir kez bekleyip dener."""
    for deneme in range(2):
        y = _al(taban + "/stats/commit_activity", token=token, urlopen=urlopen)
        if y is None:
            return None
        if y.durum == 202:
            if deneme == 0:
                bekle(2)
                continue
            return None
        if y.durum != 200:
            return None
        veri = y.json()
        if not isinstance(veri, list):
            return None
        sayilar: list[int] = []
        for hafta in veri[-12:]:
            toplam = hafta.get("total") if isinstance(hafta, dict) else None
            if not isinstance(toplam, int) or isinstance(toplam, bool) or toplam < 0:
                return None
            sayilar.append(toplam)
        return tuple([0] * (12 - len(sayilar)) + sayilar)
    return None


def _diller(taban: str, token, urlopen) -> tuple[tuple[str, int], ...]:
    y = _al(taban + "/languages", token=token, urlopen=urlopen)
    veri = y.json() if y is not None and y.durum == 200 else None
    if not isinstance(veri, dict):
        return ()
    baytlar = {
        ad: b for ad, b in veri.items()
        if isinstance(ad, str) and isinstance(b, int) and not isinstance(b, bool) and b > 0
    }
    toplam = sum(baytlar.values())
    if not toplam:
        return ()
    sirali = sorted(baytlar.items(), key=lambda kv: (-kv[1], kv[0]))[:5]
    return tuple((ad, round(100 * b / toplam)) for ad, b in sirali if round(100 * b / toplam) > 0)


def repo_verisi_api(
    sahip: str,
    repo: str,
    *,
    token: str | None = None,
    readme: bool = False,
    urlopen: Callable = urllib.request.urlopen,
    bekle: Callable[[float], object] = time.sleep,
) -> RepoVerisi | None:
    """Herkese açık bir repo için `RepoVerisi` döndürür; özel/okunamayan repo için None."""
    if not _SAHIP_DESENI.fullmatch(sahip) or not _REPO_DESENI.fullmatch(repo):
        return None
    taban = f"/repos/{urllib.parse.quote(sahip, safe='')}/{urllib.parse.quote(repo, safe='')}"

    y = _al(taban, token=token, urlopen=urlopen)
    bilgi = y.json() if y is not None and y.durum == 200 else None
    # Yalnız açıkça herkese açık olduğu kanıtlanan repo yayınlanır.
    if not isinstance(bilgi, dict) or bilgi.get("private") is not False:
        return None
    if bilgi.get("visibility", "public") != "public":
        return None

    commit = _commitler(taban, token, urlopen)
    if commit is None:
        return None
    toplam, son = commit

    ozet = None
    if readme:
        r = _al(taban + "/readme", token=token, urlopen=urlopen, kabul=_HAM)
        if r is not None and r.durum == 200:
            ozet = _readme_ozetle(r.govde.decode("utf-8", errors="replace"))

    return RepoVerisi(
        commit_sayisi=toplam,
        ilk_commit=None,
        son_commit=son,
        haftalik=_haftalik(taban, token, urlopen, bekle),
        diller=_diller(taban, token, urlopen),
        readme_ozeti=ozet,
        dil_birimi="yuzde",
    )
