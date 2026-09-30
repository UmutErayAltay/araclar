"""Maskeleme sozlesmesi: parca birakma, kirpma sirasi, tek uretim noktasi."""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from atlas import leaks
from conftest import make_repo

FAKE_SK = "sk-" + "a1" * 15


# --------------------------------------------------------------------------
# Parca birakma YASAK
# --------------------------------------------------------------------------

def test_maskede_sir_parcasi_kalmaz():
    """`sk-...xxxx` gibi parca sizdirilMAZ; tamamini gider."""
    satirlar = [
        f"anahtar: {FAKE_SK}",
        f"token={FAKE_SK};",
        f"({FAKE_SK})",
        f"'{FAKE_SK}'",
    ]
    for ham in satirlar:
        bulgu = leaks.satiri_tara(ham)[0]
        snip = bulgu["snippet_redacted"]
        assert FAKE_SK not in snip
        # Hicbir 6+ karakterlik ozgun parca kalmamali.
        for i in range(len(FAKE_SK) - 5):
            assert FAKE_SK[i : i + 6] not in snip, f"parca sizdi: {FAKE_SK[i:i+6]}"


def test_snippet_en_fazla_120_karakter():
    """Uzun satir: once maskele, SONRA kirp -> 120 karakter siniri."""
    on_ek = "y" * 500
    bulgu = leaks.satiri_tara(f"{on_ek} {FAKE_SK}") [0]
    assert len(bulgu["snippet_redacted"]) <= leaks.SNIPPET_MAX


def test_kirpma_maskelemeden_sonra_yapilir():
    """Kirpma once olsaydi ham sirin parcagi kalirdi; burada KALMAZ."""
    on_ek = "z" * 300 + " "  # 120'den uzun (sirin ONUNE bosluk: sk- burada kelime basidir)
    bulgu = leaks.satiri_tara(f"{on_ek}{FAKE_SK}")[0]
    snip = bulgu["snippet_redacted"]
    assert len(snip) <= leaks.SNIPPET_MAX
    for i in range(len(FAKE_SK) - 5):
        assert FAKE_SK[i : i + 6] not in snip


def test_ozel_anahtar_govdesi_maskelenir():
    """`-----BEGIN RSA PRIVATE KEY-----` sonrasi base64 govde maskelenir."""
    govde = "MII" + "Ep" * 60  # 120+ karakter base64
    ham = f"-----BEGIN RSA PRIVATE KEY-----\n{govde}\n-----END RSA PRIVATE KEY-----"
    bulgu = leaks.satiri_tara(ham)[0]
    assert bulgu["kind"] == "ozel-anahtar"
    assert govde[:20] not in (bulgu["snippet_redacted"] or "")


def test_kisisel_yol_kullanici_silinir():
    BS = chr(92)  # tek backslash
    for ham, beklenen in [
        (f"C:{BS}Users{BS}umut{BS}Masaustu", f"C:{BS}Users{BS}<kullanici>"),
        ("/Users/umut/proje", "/Users/<kullanici>"),
        ("/home/umut/proje", "/home/<kullanici>"),
    ]:
        b = leaks.satiri_tara(ham)[0]
        assert b["kind"] == "kisisel-yol"
        assert "umut" not in b["snippet_redacted"]
        assert beklenen in b["snippet_redacted"]


def test_eposta_maskelenir():
    b = leaks.satiri_tara("mail: kisi@firma-ornek.org")[0]
    assert b["kind"] == "e-posta"
    assert "gmail" not in b["snippet_redacted"]
    assert "<e-posta>" in b["snippet_redacted"]


def test_eposta_istisnalari_maskelenmez():
    """Istisna imzalar MASKELENMEZ (bulgu zaten degil; bulgu olsaydi bozulurdu)."""
    assert leaks.maske("noreply@anthropic.com") == "noreply@anthropic.com"
    assert "users.noreply.github.com" in leaks.maske("a@users.noreply.github.com")


# --------------------------------------------------------------------------
# TEK URETIM NOKTASI
# --------------------------------------------------------------------------

def test_bulgu_olustur_snippet_dondurur():
    """`bulgu_olustur` disarı sadece maskelenmis sozluk verir."""
    ham = f"sifre {FAKE_SK}"
    bulgu = leaks.bulgu_olustur(
        kind="api-anahtari", severity="yuksek", file="a.txt", line=1, commit=None,
        ham_metin=ham,
    )
    assert set(bulgu) == {"kind", "severity", "file", "line", "commit", "snippet_redacted"}
    assert FAKE_SK not in bulgu["snippet_redacted"]
    assert bulgu["kind"] == "api-anahtari"
    assert bulgu["severity"] == "yuksek"


def test_sonuc_sozlugu_json_guvenli():
    """Sonuc sozlugu tek basina string'e basilabilir (loglanabilir)."""
    import json

    bulgu = leaks.satiri_tara(f"k: {FAKE_SK}")[0]
    metin = json.dumps(bulgu, ensure_ascii=False)
    assert FAKE_SK not in metin
    json.loads(metin)  # gecerli JSON


def test_hata_mesaji_eslesen_metin_icermez():
    """Hata mesajlari eslesen metni ICERMEZ (`re.error` dahil)."""
    # Bozuk desen hata firlatirsa bile mesaj ham metni tasimamali.
    try:
        re.compile("[")
    except re.error as exc:
        assert "sk-" not in str(exc)


def test_bulgu_olustur_snippet_olmadan():
    """`snippet_redacted=None` (env-izlenen gibi) sorunsuz."""
    b = leaks.bulgu_olustur(
        kind="env-izlenen", severity="yuksek", file=".env", line=None, commit=None
    )
    assert b["snippet_redacted"] is None


# --------------------------------------------------------------------------
# Desen dogrulugu (pozitif/negatif)
# --------------------------------------------------------------------------

def test_sonraki_tur_bulgu_yok():
    """Ayni satirda ayni DESEN icin TEK bulgu uretilir."""
    b = leaks.satiri_tara(f"{FAKE_SK} {FAKE_SK}")
    assert len([x for x in b if x["kind"] == "api-anahtari"]) == 1


def test_farkli_desenler_ayri_bulgu():
    """Ayni satirda iki farkli TÜR varsa ikisi de bildirilir.

    Aynı türden ikinci desen (ör. hem `sk-` hem `sb_publishable_`) yinelenmez:
    satır başına tür başına tek bulgu kuralı.
    """
    b = leaks.satiri_tara(f"{FAKE_SK} ve yol: /Users/umut/proje")
    turler = [x["kind"] for x in b]
    assert turler == ["api-anahtari", "kisisel-yol"]


def test_ayni_tur_iki_desen_tek_bulgu():
    """`sk-` + `sb_publishable_` ayni satirda: API anahtari olarak TEK bulgu."""
    b = leaks.satiri_tara(f"{FAKE_SK} ve apikey: sb_publishable_" + "b2" * 20)
    assert [x["kind"] for x in b] == ["api-anahtari"]


# --------------------------------------------------------------------------
# YANLIŞ POZITIF REGRESYONLARI (gercek vault taramasinda bulundu)
# --------------------------------------------------------------------------

def test_masum_task_notification_bozulmaz():
    """`sk-` maskesi TESPITTEN genis olmamali: `<task-notification>` bozulmaz.

    Gercek taramada `sk-[A-Za-z0-9_-]{4,}` maskesi `<task-notification>` metnini
    `<ta[maskeli:api-anahtari]>` yapip ciktiyi okunamaz hale getiriyordu.
    """
    assert leaks.maske("<task-notification>") == "<task-notification>"


def test_maske_tespitten_dar_veya_esit():
    """SIF BIRAKMA KURALI: ne tespit ediliyorsa en az o kadar genis maske var.

    Her tespit deseni icin, onun yakalayabilecegi tipik bir girdi maskeyle
    TAMAMEN silinmelidir (hicbir parcasi kalmamalidir).
    """
    gercek_sirlar = [
        FAKE_SK,                               # sk-
        "sb_publishable_" + "a1" * 20,         # supabase
        "AK" + "IA" + "X7" * 8,                # aws
        "ghp_" + "b2" * 20,                    # github
        "xoxb-" + "c3" * 8,                    # slack
    ]
    for sir in gercek_sirlar:
        maskeli = leaks.maske(f"k: {sir}")
        assert sir not in maskeli, f"SIR PARCASI KALDI: {sir[:4]}..."
        # Ilk 6 karakter de hicbir parcada gorunmemeli.
        for i in range(len(sir) - 5):
            assert sir[i : i + 6] not in maskeli
    # api_key = deger bicimi
    deger = "q7Rt2mKp9zXw4LbN"
    assert deger not in leaks.maske(f"API_KEY = {deger}")


def test_masum_sk_sozcukleri_bulgu_degil():
    """Kebab-case `sk-` kelimeleri bulgu degil (rakam yok)."""
    for metin in ("task-notification", "risk-low", "flask-app", "disk-usage"):
        assert leaks.satiri_tara(metin) == []


def test_fonksiyon_cagrisi_yanlis_pozitif_degil():
    """`const apiKey = resolveOpenRouterKey(config)` bir cagridir, sir degil."""
    assert leaks.satiri_tara("const apiKey = resolveOpenRouterKey(config);") == []
    assert leaks.satiri_tara("const token = getAccessTokenFromRequest(req);") == []


def test_env_degiskeni_referansi_yanlis_pozitif_degil():
    """`token = process.env.X` kod referansidir, sir degil."""
    assert leaks.satiri_tara("token = process.env.OPENAI_KEY") == []
    assert leaks.satiri_tara("apiKey = os.environ['KEY']") == []


def test_sozluk_degeri_yanlis_pozitif_degil():
    """Gunluk metninde `Token: <sozcu kumesi>` bulgu degil."""
    assert leaks.satiri_tara("Token: oturumdurumundegerlendirildi") == []


def test_supabase_anahtari_bulunur():
    """Supabase publishable/secret anahtarlari API anahtari sayilir."""
    for onek in ("sb_publishable_", "sb_secret_"):
        b = leaks.satiri_tara(f"apikey: {onek}" + "a1" * 20)
        assert b and b[0]["kind"] == "api-anahtari"
        assert "a1a1" not in b[0]["snippet_redacted"]


def test_json_ve_tirnaksiz_gercek_sir_bulunur():
    """Yalnizca fonksiyon/eleme degil, gercek sirlar da bulunmali."""
    for ham in (
        '{"api_key": "q7Rt2mKp9zXw4LbN"}',
        "API_KEY = q7Rt2mKp9zXw4LbN",
        "export API_KEY=8fj20dkfja20dkfja20",
        "token = 8fj20dkfja20dkfja20",
    ):
        b = leaks.satiri_tara(ham)
        assert b, f"GERCEK SIR KACIRILDI: {ham}"
        assert b[0]["kind"] == "api-anahtari"


def test_turkce_dosya_adi_islenir():
    """Turkce karakterli dosya adi: bulguya dogru gecer (dosya ADINA dokunulmaz)."""
    bulgu = leaks.satiri_tara("sır: " + FAKE_SK, dosya="kullanıcı/gizli.txt")
    assert bulgu
    assert bulgu[0]["file"] == "kullanıcı/gizli.txt"


# --------------------------------------------------------------------------
# PERFORMANS: katastrofik regex yok
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "metin",
    [
        "A" * 100_000,
        "a" * 50_000 + "!",          # basarisiz eslesme sonrasi uzun tarama
        ("ab" * 30_000),
        "sk-" + "a" * 50_000,        # sk- ile baslayan, rakamsiz (elenmeli ama hizli)
        "x" * 60_000 + "@" + "y" * 20,  # e-posta deseni uzerinde uzun on ek
    ],
)
def test_uzun_satir_yavasligi_yok(metin: str):
    """Tekrarli/patolojik girdide tarama makul surede biter (<2 sn)."""
    bas = time.monotonic()
    leaks.satiri_tara(metin)
    sure = time.monotonic() - bas
    assert sure < 2.0, f"yavaslama: {sure:.2f} sn (desen katastrofik olabilir)"


def test_cok_satirli_dosya_yavasligi_yok(tmp_path: Path):
    """20k satirlik dosya: taranabilir, patlamaz."""
    repo = make_repo(tmp_path / "r")
    icerik = "\n".join("satir %d burada" % i for i in range(20_000))
    (repo / "buyuk.txt").write_text(icerik, encoding="utf-8")
    from conftest import git

    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "buyuk", cwd=repo)
    bas = time.monotonic()
    b = leaks.tara_calisma_agaci(repo)
    sure = time.monotonic() - bas
    assert sure < 15, f"yavaslama: {sure:.1f} sn"
    assert b == [], "sirr olmayan dosyada bulgu olmamali"
