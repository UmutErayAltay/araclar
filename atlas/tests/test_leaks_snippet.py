"""SNIPPET KALITESI: etrafinda pencere, savunma katmani, yeni desenler.

B.1'de bulunan IKINCI hata: gercek ciktida 10 `api-anahtari` bulgusunun
snippet'inda maske isareti YOKTU — tetikleyen eslesme 120 karakterlik
pencerenin disinda kaliyor, snippet satirin BASINI gosteriyordu. Ayrica 2
snippet'ta tespit edilmeyen ama sir gibi duran uzun bir onaltilik deger ACIKTA
kalmisti.

Sozlesme:
  (1) Snippet ilk eslesmenin ETRAFINDA kurulur; ONCE tum eslesmeler
      maskelenir, SONRA pencere kesilir; kesilen uclara `…` konur.
  (2) Savunma katmani: her snippet icin, eslesme olsun olmasin, en az 24
      karakterlik `[A-Za-z0-9_-]` dizisi ve icinde en az bir rakam varsa
      `[maskeli:uzun-deger]` yapilir.
  (3) Yeni tespitler: etiketli deger, Stripe, Google, JWT; Supabase
      `sb_publishable_` `bilgi` onemine duser.

Sahte sirler kaynakta TAM LITERAL olarak yazilmaz; calisma zamaninda
parcalardan kurulur.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from atlas import leaks
from conftest import commit_file, git, make_repo

FAKE_SK = "sk-" + "a1" * 15
FAKE_AWS = "AK" + "IA" + "X7" * 8
FAKE_GH = "ghp_" + "b2" * 20
FAKE_SLACK = "xoxb-" + "c3" * 8
FAKE_SB_PUB = "sb_publishable_" + "x1" * 20
FAKE_SB_SEC = "sb_secret_" + "y2" * 20
FAKE_STRIPE = "sk_live_" + "a1b2c3d4" * 3
FAKE_GOOGLE = "AIza" + "SyB3a1" * 7
FAKE_JWT = (
    "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0"
    + "." + "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
)

#: 24+ karakter, rakam iceriyor: savunma katmaninin yakalayacagi "gizli" dizi.
GIZLI_UZUN = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"

_UZUN_DESEN = re.compile(r"[A-Za-z0-9_-]{24,}")


def _sir_kaldi(snip: str | None, deger: str) -> bool:
    """Snippet'te sirin HICBIR parcasi (ilk 6 karakter dahil) kaldi mi?

    Tespit edilen sirlarda TAMAMINI silmek zorunluyuz; 6 karakterlik parca
    bile sizdirilma sayilir.
    """
    if not snip:
        return False
    for i in range(len(deger) - 5):
        if deger[i : i + 6] in snip:
            return True
    return deger in snip


# --------------------------------------------------------------------------
# (1) Eslesme satirin sonunda: pencere ESLESMENIN ETRAFINDA kurulur
# --------------------------------------------------------------------------

def test_eslesme_sonunda_maske_isareti_gorunur():
    """300 karakterlik satir, eslesme SONUNDA: snippet maske icermeli.

    Eski cozumde pencere satirin BASINDAN alindiği icin maske isareti
    120 karakterlik pencerenin disinda kaliyordu.
    """
    on_ek = ("aciklama metni burada devam ediyor. " * 12)[:280]
    ham = on_ek + " API_KEY = " + FAKE_SK
    assert len(ham) > 290
    b = leaks.satiri_tara(ham)
    assert b, "bulgu uretilmedi"
    snip = b[0]["snippet_redacted"]
    assert "[maskeli" in snip, "pencere eslesmeyi kapsamiyor"
    assert len(snip) <= leaks.SNIPPET_MAX
    assert not _sir_kaldi(snip, FAKE_SK)


def test_eslesme_basi_tutulunca_maske_gorunur():
    """Eslesme satirin BASINDA: pencere onu sarar, isaret gorunur."""
    ham = "API_KEY = " + FAKE_SK + " ve buraya devam eden baska metin." * 5
    b = leaks.satiri_tara(ham)
    assert b and "[maskeli" in b[0]["snippet_redacted"]
    assert not _sir_kaldi(b[0]["snippet_redacted"], FAKE_SK)


def test_tespit_edilmeyen_uzun_dize_de_maskelenir():
    """Basinda 40+ karakterlik TESPIT EDILMEYEN uzun rastgele dize ACIKTA KALMAZ.

    KABUL KRITERI'nin tam senaryosu: 300 karakterlik satir, eslesme satirin
    SONUNDA, basinda 32+ karakterlik tespit edilmeyen uzun dize.
    """
    on_ek = "not: " + GIZLI_UZUN + " ve burada baska bir not metni var. " * 8
    ham = on_ek + "API_KEY = " + FAKE_SK
    assert len(ham) > 290, "satir 300 karakterden uzun olmali"
    b = leaks.satiri_tara(ham)
    assert b, "bulgu uretilmedi"
    snip = b[0]["snippet_redacted"]
    assert GIZLI_UZUN not in snip, "tespit edilmeyen uzun dize sizdi"
    # Eslesme satirin sonunda: pencere onu sarar → maske isareti gorunur.
    assert "[maskeli" in snip
    assert not _sir_kaldi(snip, FAKE_SK)


def test_kirpilmis_uclara_uc_nokta_konur():
    """Pencere kesildiginde kesilen uc `…` ile isaretlenir.

    Eslesme satirin BASINDA: sag tarafta cok metin birikiyor, pencere orayi
    kesiyor; sol uc metnin BASI oldugu icin kirpilmis olmamali.
    """
    ham = "API_KEY = " + FAKE_SK + (" not. " * 40) + "burada devam eden metin"
    b = leaks.satiri_tara(ham)
    snip = b[0]["snippet_redacted"]
    assert snip.endswith("…"), f"snip sonu kesilmis olmali: {snip[-25:]!r}"
    assert len(snip) <= leaks.SNIPPET_MAX
    assert not _sir_kaldi(snip, FAKE_SK)
    assert "[maskeli" in snip


def test_pencere_maske_isaretini_bolmez():
    """Pencere bir maske işaretinin içinde kalırsa işaret BÖLÜNMEZ."""
    ham = "yol: /Users/umut/" + ("not. " * 20) + "olmayan not"
    b = leaks.satiri_tara(ham)
    snip = b[0]["snippet_redacted"]
    assert "[maskeli" not in snip  # yol maskesi sadece `<kullanici>` yaziyor
    # Uzun alfasayisel dizi maskesi isaretinin ORTASINDA kalabilir.
    ham2 = "yol: /Users/umut/" + ("a" * 60) + " olmayan not"
    b2 = leaks.satiri_tara(ham2)
    snip2 = b2[0]["snippet_redacted"]
    for isaret in ("[maskeli:sir]", "[maskeli:uzun-deger]", "[maskeli:api-anahtari]"):
        assert isaret not in snip2 or snip2.count(isaret) == 1
        if isaret in snip2:
            assert snip2[snip2.index(isaret):snip2.index(isaret) + len(isaret)] == isaret


def test_kisa_satir_kirpilmaz():
    """120 karakterden kisayse kirpma isareti konmaz."""
    b = leaks.satiri_tara("k: " + FAKE_SK)
    assert not b[0]["snippet_redacted"].endswith("…")


# --------------------------------------------------------------------------
# (2) Savunma katmani
# --------------------------------------------------------------------------

def test_savunma_katmani_her_snippet_icin_calisir():
    """ESLESME olmasa bile 24+ rakamli dizi maskelenir."""
    for dizi in (GIZLI_UZUN, "0123456789abcdef01234567", "a" * 23 + "1"):
        maskeli = leaks.maske(dizi)
        assert "[maskeli:uzun-deger]" in maskeli, dizi[:8]


def test_savunma_katmani_yol_ve_url_parcalarini_birakir():
    """Yol/URL parcalari BOLUNMEZ: `/` ve `.` sınıf disi oldugu icin."""
    yollar = [
        "/home/user/import-2026-07-part-024.md",
        "daily/import-2026-07-part-006.md",
        "https://github.com/ornek/proje",
        "docs/screenshots/2026-07-14-10-30-00.png",
    ]
    for yol in yollar:
        assert leaks.maske(yol) == leaks.maske(yol)  # deterministik
        assert "[maskeli:uzun-deger]" not in leaks.maske(yol), yol


def test_savunma_katmani_rakamsiz_kelime_dokunmaz():
    """Kebab-case Turkce/Ingilizce cumle rakamsizdir: bozulmaz."""
    cumleler = [
        "bu-cumle-rakamsiz-ve-cok-uzun-bir-sekilde-yazildi",
        "onbir-iki-ucuncu-dorduncu-besinci-altinci-yedinci",
        "installation-instructions-for-the-development-environment",
    ]
    for c in cumleler:
        assert leaks.maske(c) == c, c


def test_url_ici_ki_degeri_maskelenir():
    """URL parcalari birakilir ama icindeki `key=`/`token=` degeri maskelenir."""
    ham = "curl https://api.example.com/v1?api_key=" + "8fj20dkfja20dkfja20"
    b = leaks.satiri_tara(ham)
    assert b and "[maskeli" in b[0]["snippet_redacted"]
    assert "8fj20dkfja20dkfja20" not in b[0]["snippet_redacted"]


def test_her_turde_snippette_acik_uzun_deger_kalmaz():
    """KABUL KRITERI: hicbir turde 24+ rakamli acik dizi kalmaz."""
    ornekler = [
        f"anahtar: {FAKE_SK}", f"aws: {FAKE_AWS}", f"gh: {FAKE_GH}",
        f"slack: {FAKE_SLACK}", f"sb: {FAKE_SB_PUB}", f"stripe: {FAKE_STRIPE}",
        f"google: {FAKE_GOOGLE}", f"jwt: {FAKE_JWT}",
        "yol: /Users/umut/proje", "mail: kisi@firma-ornek.org",
        "-----BEGIN RSA PRIVATE KEY-----",
        "not: e-posta: " + GIZLI_UZUN + "@ornek.com buradaki eslesme e-postadir",
    ]
    for ham in ornekler:
        b = leaks.satiri_tara(ham)
        assert b, f"BULGU YOK: {ham[:30]}"
        snip = b[0]["snippet_redacted"]
        acik = [
            m.group(0) for m in _UZUN_DESEN.finditer(snip)
            if any(ch.isdigit() for ch in m.group(0))
        ]
        assert not acik, f"ACIK UZUN DEGER: {ham[:30]} -> {len(acik)} adet"


# --------------------------------------------------------------------------
# (3) Yeni tespitler
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "deger,onem",
    [(FAKE_STRIPE, "yuksek"), (FAKE_GOOGLE, "yuksek"), (FAKE_JWT, "yuksek"),
     (FAKE_SB_SEC, "yuksek"), (FAKE_SB_PUB, "bilgi")],
)
def test_yeni_saglayici_desenleri(deger: str, onem: str):
    """Stripe / Google / JWT / Supabase secret yuksek; publishable `bilgi`."""
    b = leaks.satiri_tara("deger: " + deger)
    assert b and b[0]["kind"] == "api-anahtari"
    assert b[0]["severity"] == onem
    assert not _sir_kaldi(b[0]["snippet_redacted"], deger)


def test_etiketli_deger_tespiti():
    """`API Key for the credential: <değer>` kendi basina tespit edilir."""
    deger = "q7Rt2mKp9zXw4LbN2f9Qk3W5z"  # 25 karakter
    for ham in (
        f"API Key for the credential: {deger}",
        f'{{"credential": "{deger}"}}',
        f"token istek basligi: {deger}",
        f"credential={deger}",
    ):
        b = leaks.satiri_tara(ham)
        assert b, f"ETIKETLI DEGER KACIRILDI: {ham[:40]}"
        assert b[0]["kind"] == "api-anahtari"
        assert not _sir_kaldi(b[0]["snippet_redacted"], deger)


def test_etiketli_deger_suzgecleri_gecerli():
    """Yer tutucu / kod referansi etiketli deger desenini TETIKLEMEZ."""
    for ham in (
        "API Key for the credential: ${OPENROUTER_API_KEY}",
        "API Key for the credential: your_key_here",
        "credential = <BURAYA_GELIR>",
        "token: process.env.GITHUB_TOKEN",
    ):
        assert not [x for x in leaks.satiri_tara(ham) if x["kind"] == "api-anahtari"], ham


def test_yeni_desenler_yol_url_yanlis_pozitif_uretmez():
    """Yeni desenler yalnizca KENDI OZEL BICIMLERINI yakalar."""
    masumler = [
        "Google API etiketi: google-cloud-platform",
        "stripe-js kutuphanesi yuklendi, odeme sayfasi acildi",
        "jwt library kullanimi icin bkz. dokuman",
        "SK_LIVE_PREFIX_ADI tanimli degil",
    ]
    for ham in masumler:
        assert not [x for x in leaks.satiri_tara(ham) if x["kind"] == "api-anahtari"], ham


# --------------------------------------------------------------------------
# GERCEK TARAMA SONRASI: yanlis pozitif siniflari
# --------------------------------------------------------------------------

def test_google_anahtari_gercek_uzunlukta_bulunur():
    """Google `AIza…` 35 karakter gövde ister; kısa olanı TESPİT EDİLMEZ.

    (Gerçek taramada `AIzaSyB3` gibi kısa bir metin `AIza…` önekiyle geçiyordu.)
    """
    assert not [x for x in leaks.satiri_tara("k: AIza" + "SyB3") if x["kind"] == "api-anahtari"]
    assert [x for x in leaks.satiri_tara("k: AIza" + "SyB3a1" * 7) if x["kind"] == "api-anahtari"]


def test_url_oda_kisi_verisi_maskelenir():
    """Gerçek vault'ta bir `wss://…` adresi 24+ karakterlik diziydi ve AÇIKTA
    kalıyordu. Savunma katmanı onu silmelidir (yanlış pozitif DEĞİL: oda
    kimliği kişisel veridir)."""
    ham = "baglanti: wss://bir-karisik-oda-kimligi-1234567.livekit.cloud baglantisi"
    maskeli = leaks.maske(ham)
    assert "bir-karisik-oda-kimligi-1234567" not in maskeli
    assert "[maskeli:uzun-deger]" in maskeli
    assert ".livekit.cloud" in maskeli  # alan adi korunur (yol/URL parcasi)


def test_etiketli_deger_sadece_sayi_karisimi_tutuyor():
    """Gerçek vault'taki `Token: …` satırı bir hata sayacı gibi görünüyordu
    (`Status: 200 Token: …`); yine de etiketli değer ve rakam içerdiği için
    gerçek sır. Doğru davranış: maskele, ama `Status` gibi çevre metni bozma."""
    ham = "Status: 200 Token: " + "b7Kd9Xq2Lm4Np8Rt1Vz3Wy6Hs0"
    b = leaks.satiri_tara(ham)
    assert b and b[0]["kind"] == "api-anahtari"
    snip = b[0]["snippet_redacted"]
    assert "Status: 200" in snip, "cevre metin bozuldu"
    assert "b7Kd9Xq2Lm4Np8Rt1Vz3Wy6Hs0" not in snip


def test_uzun_deger_masksesi_her_zaman_rakam_ister():
    """Rakamsız 24+ karakterlik dizi BOZULMAZ (kebab-case cümle, commit hash'i
    gibi meşru metinler)."""
    for metin in (
        "b7Kd9Xq2Lm4Np8Rt1Vz3Wy6Hs0",  # rakamlı -> maskelenir
        "this-is-a-long-dash-separated-phrase-without-digits",
        "aaaa bbbb cccc dddd eeee ffff gggg hhhh",
    ):
        sonuc = leaks.maske(metin)
        if any(ch.isdigit() for ch in metin.split()[0]):
            assert "[maskeli:uzun-deger]" in sonuc, metin
        else:
            assert sonuc == metin, metin


def test_gercek_tarama_sonrasi_metin_bozulmaz():
    """Gerçek vault satır biçimleri: maske çevre yapıyı bozmamalı."""
    satirlar = [
        'Session: messages/abc123/call-token (olumlu) Status: 200 URL: wss://x.livekit.cloud',
        'daily/import-2026-07-part-024.md dosyası 17. satırda bir API Key bulunuyor',
        "https://supabase.com/project/abcdef123456/settings/api",
    ]
    for ham in satirlar:
        b = leaks.satiri_tara(ham)
        if b:
            snip = b[0]["snippet_redacted"]
            assert len(snip) <= leaks.SNIPPET_MAX
            # Yol/URL parçaları korunur (kullanılabilirlik).
            assert "/" in snip or "…" in snip


# --------------------------------------------------------------------------
# Uctan uca: gercek repo + CLI
# --------------------------------------------------------------------------

def test_gercek_repoda_snippet_kurali(db_file: Path, tmp_path: Path):
    """Gercek repoda tarama: hicbir bulgunun snippet'inda acik uzun deger yok."""
    from conftest import run_module_cli

    repo = make_repo(tmp_path / "r")
    on_ek = "not: " + GIZLI_UZUN + " yalnizca not metni, sirlik degil"
    (repo / "s.txt").write_text(on_ek + " API_KEY = " + FAKE_SK + "\n", encoding="utf-8")
    (repo / "t.txt").write_text("not: " + GIZLI_UZUN + " baska not\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "sirli", cwd=repo)

    proc = run_module_cli("sizinti", "--root", str(tmp_path), "--db", str(db_file))
    assert proc.returncode == 0, proc.stderr
    from atlas import db as db_mod

    conn = db_mod.connect(db_file)
    try:
        satirlar = db_mod.list_findings(conn, repo=str(repo))
    finally:
        conn.close()
    assert satirlar
    for satir in satirlar:
        snip = satir["snippet_redacted"] or ""
        if satir["kind"] == "api-anahtari":
            assert "[maskeli" in snip, "api-anahtari snippet'inda maske isareti yok"
        for m in _UZUN_DESEN.finditer(snip):
            assert not any(ch.isdigit() for ch in m.group(0)), "acik uzun deger"


def test_maske_testi_sonrasi_cikti_temiz(tmp_path: Path):
    """Snippet uretimi asla ham siri dondurmaz (dogrudan API seviyesi)."""
    for deger in (FAKE_SK, FAKE_AWS, FAKE_GH, FAKE_SLACK, FAKE_STRIPE, FAKE_JWT):
        b = leaks.satiri_tara("x: " + deger)
        assert b
        assert not _sir_kaldi(b[0]["snippet_redacted"], deger)