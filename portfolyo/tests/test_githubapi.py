"""githubapi: sahte urlopen ile; gerçek ağa çıkılmaz."""

from __future__ import annotations

import json
import urllib.error

import pytest

from portfolyo import githubapi
from portfolyo.githubapi import repo_verisi_api

TABAN = "https://api.github.com/repos/u/r"
REPO = {"private": False, "visibility": "public", "pushed_at": "2026-09-30T10:00:00Z"}


class Yanit:
    def __init__(self, govde, durum=200, basliklar=None, url=TABAN):
        self.govde = govde if isinstance(govde, bytes) else json.dumps(govde).encode()
        self.status = durum
        self.headers = basliklar or {}
        self._url = url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, n=-1):
        return self.govde[:n] if n and n > 0 else self.govde

    def geturl(self):
        return self._url


class Sahte:
    """Yol sonekine göre yanıt verir; çağrıları kaydeder."""

    def __init__(self, yanitlar):
        self.yanitlar = yanitlar  # {sonek: Yanit | [Yanit,...] | Exception}
        self.istekler = []

    def __call__(self, istek, timeout=None):
        self.istekler.append((istek, timeout))
        url = istek.full_url
        for sonek, y in self.yanitlar.items():
            if url == TABAN + sonek:
                if isinstance(y, list):
                    y = y.pop(0)
                if isinstance(y, Exception):
                    raise y
                return y
        raise urllib.error.HTTPError(url, 404, "yok", {}, None)


def _tam(**degis):
    y = {
        "": Yanit(REPO),
        "/commits?per_page=1": Yanit(
            [{"commit": {"committer": {"date": "2026-09-30T10:00:00Z"}}}],
            basliklar={"Link": '<https://api.github.com/repositories/1/commits?per_page=1&page=2>; rel="next", '
                               '<https://api.github.com/repositories/1/commits?per_page=1&page=57>; rel="last"'},
        ),
        "/stats/commit_activity": Yanit([{"total": i, "week": 0, "days": []} for i in range(52)]),
        "/languages": Yanit({"Python": 7200, "CSS": 2800, "Shell": 0}),
        "/readme": Yanit(b"# Baslik\n\nBu depo, kisisel portfolyo icin gerekli verileri toplayan kucuk bir araclar setidir.\n"),
    }
    y.update(degis)
    return Sahte(y)


def test_tam_veri():
    s = _tam()
    v = repo_verisi_api("u", "r", readme=True, urlopen=s)
    assert v.commit_sayisi == 57
    assert v.son_commit == "2026-09-30"
    assert v.ilk_commit is None
    assert v.haftalik == tuple(range(40, 52))  # son 12 hafta, en eski başta
    assert v.diller == (("Python", 72), ("CSS", 28))  # 0 baytlık dil elenir
    assert v.dil_birimi == "yuzde"
    assert v.readme_ozeti.startswith("Bu depo")


def test_readme_istenmezse_cagrilmaz():
    s = _tam()
    v = repo_verisi_api("u", "r", urlopen=s)
    assert v.readme_ozeti is None
    assert not any(i.full_url.endswith("/readme") for i, _ in s.istekler)


def test_ozel_repo_reddedilir_ve_baska_cagri_yapilmaz():
    s = _tam(**{"": Yanit({**REPO, "private": True})})
    assert repo_verisi_api("u", "r", urlopen=s) is None
    assert len(s.istekler) == 1


@pytest.mark.parametrize("bilgi", [
    {"visibility": "public"},                       # private alanı yok → kanıtlanamadı
    {"private": "false"},                           # string, boolean değil
    {"private": False, "visibility": "internal"},
    {"private": None},
    [],
])
def test_herkese_acik_kanitlanamazsa_reddedilir(bilgi):
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"": Yanit(bilgi)})) is None


@pytest.mark.parametrize("hata", [
    urllib.error.HTTPError(TABAN, 403, "rate", {}, None),
    urllib.error.HTTPError(TABAN, 404, "yok", {}, None),
    urllib.error.URLError("ag yok"),
    TimeoutError(),
    ConnectionResetError(),
])
def test_ag_hatalari_none(hata):
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"": hata})) is None


def test_bozuk_json_none():
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"": Yanit(b"{bozuk")})) is None


def test_commit_okunamazsa_none_bos_repo_sifir():
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"/commits?per_page=1": Yanit(b"x")})) is None
    v = repo_verisi_api("u", "r", urlopen=_tam(**{"/commits?per_page=1": Yanit([])}))
    assert v.commit_sayisi == 0 and v.son_commit is None


def test_link_basligi_yoksa_tek_commit():
    y = Yanit([{"commit": {"committer": {"date": "2026-01-02T00:00:00Z"}}}])
    v = repo_verisi_api("u", "r", urlopen=_tam(**{"/commits?per_page=1": y}))
    assert v.commit_sayisi == 1 and v.son_commit == "2026-01-02"


def test_istatistik_202_bir_kez_bekler_sonra_okur():
    beklemeler = []
    s = _tam(**{"/stats/commit_activity": [Yanit({}, durum=202), Yanit([{"total": 3}] * 52)]})
    v = repo_verisi_api("u", "r", urlopen=s, bekle=beklemeler.append)
    assert beklemeler == [2]
    assert v.haftalik == (3,) * 12


def test_istatistik_hep_202_ise_haftalik_none():
    s = _tam(**{"/stats/commit_activity": [Yanit({}, durum=202), Yanit({}, durum=202)]})
    v = repo_verisi_api("u", "r", urlopen=s, bekle=lambda _: None)
    assert v.haftalik is None and v.commit_sayisi == 57  # geri kalan veri korunur


def test_az_haftalik_veri_basa_sifirla_tamamlanir():
    s = _tam(**{"/stats/commit_activity": Yanit([{"total": 5}, {"total": 6}])})
    assert repo_verisi_api("u", "r", urlopen=s).haftalik == (0,) * 10 + (5, 6)


@pytest.mark.parametrize("veri", [[{"total": "x"}], [{"total": -1}], [{"total": True}], {"a": 1}])
def test_bozuk_istatistik_none(veri):
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"/stats/commit_activity": Yanit(veri)})).haftalik is None


def test_diller_bozuksa_bos():
    for veri in ([], {"Python": "x"}, {"Python": 0}):
        assert repo_verisi_api("u", "r", urlopen=_tam(**{"/languages": Yanit(veri)})).diller == ()


def test_diller_en_cok_bes():
    d = {f"L{i}": 1000 * (i + 1) for i in range(8)}
    v = repo_verisi_api("u", "r", urlopen=_tam(**{"/languages": Yanit(d)}))
    assert len(v.diller) == 5 and v.diller[0][0] == "L7"


def test_sabit_konak_zaman_asimi_ve_basliklar():
    s = _tam()
    repo_verisi_api("u", "r", token="ghp_GIZLI", urlopen=s)
    for istek, zaman in s.istekler:
        assert istek.full_url.startswith("https://api.github.com/repos/u/r")
        assert zaman == 15 and istek.get_method() == "GET"
        assert istek.get_header("Accept") == "application/vnd.github+json"
        assert istek.get_header("User-agent")
        assert istek.get_header("Authorization") == "Bearer ghp_GIZLI"


def test_token_yoksa_authorization_yok():
    s = _tam()
    repo_verisi_api("u", "r", urlopen=s)
    assert all(i.get_header("Authorization") is None for i, _ in s.istekler)


def test_readme_ham_icerik_istegi():
    s = _tam()
    repo_verisi_api("u", "r", readme=True, urlopen=s)
    (okuma,) = [i for i, _ in s.istekler if i.full_url.endswith("/readme")]
    assert okuma.get_header("Accept") == "application/vnd.github.raw"


def test_baska_konaga_yonlendirme_reddedilir():
    kotu = Yanit(REPO, url="https://evil.example/repos/u/r")
    assert repo_verisi_api("u", "r", urlopen=_tam(**{"": kotu})) is None


@pytest.mark.parametrize("sahip,repo", [("../x", "r"), ("u", "r/../../x"), ("u", ""), ("", "r"), ("u v", "r"), ("u", "r?x=1")])
def test_gecersiz_adlar_ag_cagrisi_yapmaz(sahip, repo):
    s = _tam()
    assert repo_verisi_api(sahip, repo, urlopen=s) is None
    assert s.istekler == []


def test_token_hata_ciktisina_sizmaz(capsys, caplog):
    repo_verisi_api("u", "r", token="ghp_GIZLI", urlopen=_tam(**{"": urllib.error.URLError("x")}))
    cikti = capsys.readouterr()
    assert "ghp_GIZLI" not in cikti.out + cikti.err + caplog.text


def test_govde_siniri_uygulanir():
    kayit = {}

    class Dev(Yanit):
        def read(self, n=-1):
            kayit["n"] = n
            return super().read(n)

    repo_verisi_api("u", "r", urlopen=_tam(**{"": Dev(REPO)}))
    assert kayit["n"] == githubapi.MAKS_GOVDE
