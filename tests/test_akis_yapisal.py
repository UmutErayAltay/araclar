"""Dalga E: `--output-format stream-json` akışı + YAPISAL kanıt.

Sahte `claude` betiği SENTETİK stream-json üretir. Fixture'lar KURGUSALDIR:
gerçek yol, oturum kimliği, kullanıcı adı, anahtar veya e-posta YOKTUR.

Sır denemelerinde anahtar çalışma zamanında parçalardan kurulur (kaynak dosyada
tam literal bulunmaz), tıpkı `test_claude_runner.py`'deki gibi.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from orkestra import report, runner
from orkestra.models import Durum, RunSonuc, Task
from orkestra.runner import (
    AKIS_BAYRAKLARI,
    AKIS_TAVAN,
    ARAC_SONUC_TAVAN,
    ClaudeRunner,
    onbellek_sifirla,
)

GIZLI_ANAHTAR = "sk-" + "k3" * 15


# -- sahte claude: SENTETIK stream-json ---------------------------------
# `--help` çıktısı `--agent` bayrağını içerir (gerçek `cor claude --help` ile aynı).

SAHTE_BETIK = r'''
import json, os, sys

MOD = os.environ.get("FAKE_AKIS", "basari")
ARGV_DOSYA = os.environ.get("FAKE_ARGV")

if "--help" in sys.argv:
    print("Usage: claude [options]")
    print("  --agent <agent>   Agent for the current session.")
    print("  --permission-mode <mode>   choices: acceptEdits, plan")
    bosalt()
    sys.exit(0)

if ARGV_DOSYA:
    with open(ARGV_DOSYA, "w", encoding="utf-8") as f:
        f.write("\n".join(sys.argv[1:]))

istem = sys.stdin.read()
OUT = []


def yaz(olay):
    OUT.append(json.dumps(olay, ensure_ascii=False))


def bosalt():
    # Tum olaylar TEK seferde yazilir: tampon yuzunden yarim akis gorunmesin.
    sys.stdout.write("\n".join(OUT) + "\n")
    sys.stdout.flush()


def cagri(kimlik, arac, girdi):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "tool_use", "id": kimlik, "name": arac, "input": girdi}]}}


def sonuc(kimlik, metin, hata=False):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": kimlik, "content": metin,
         "is_error": hata}]}}


def metin_parca(metin):
    return {"type": "assistant", "message": {"role": "assistant",
            "content": [{"type": "text", "text": metin}]}}


def bitis(son, denials=(), hata=False, tur=3, usd=0.0123):
    return {"type": "result", "subtype": "success", "is_error": hata,
            "result": son, "stop_reason": "end_turn", "num_turns": tur,
            "permission_denials": list(denials), "total_cost_usd": usd}


# ---------------------------------------------------------------- senaryolar

if MOD == "basari":
    yaz({"type": "system", "subtype": "init", "session_id": "k3rgusal-0001"})
    yaz(cagri("k1", "Bash", {"command": "python3 -m pytest -q"}))
    yaz(sonuc("k1", "3 passed in 0.42s"))
    yaz(metin_parca("Testler calistirildi, 3 passed diyor."))
    yaz(bitis("Testler calistirildi, 3 passed diyor."))
    bosalt()
    sys.exit(0)

if MOD == "izin":
    # Arac reddedildi ama ajan TEMIZ konusuyor ve CIKIS KODU 0.
    yaz(cagri("k1", "Bash", {"command": "rm -rf /tmp/xxx"}))
    yaz(sonuc("k1", "Command requires approval and was denied", hata=True))
    yaz(metin_parca("Gorevi tamamladim."))
    yaz(bitis("Gorevi tamamladim."))
    bosalt()
    sys.exit(0)

if MOD == "denial":
    yaz(cagri("k1", "Bash", {"command": "git push"}))
    yaz(sonuc("k1", "push yapilmadi"))
    yaz(metin_parca("Git durumu temiz, degisiklik hazir."))
    yaz(bitis("Git durumu temiz.", denials=[
        {"tool_name": "Bash", "tool_use_id": "k1", "reason": "user"}]))
    bosalt()
    sys.exit(0)

if MOD == "basarisiz":
    # Ajan "hepsi gecti" diyor; SON gozlemlenen kosu 2 failed.
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "10 passed"))
    yaz(cagri("k2", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k2", "2 failed, 8 passed"))
    yaz(metin_parca("Tum testler gecti, her sey hazir."))
    yaz(bitis("Tum testler gecti, her sey hazir."))
    bosalt()
    sys.exit(0)

if MOD == "gercek_basarisiz":
    # GERCEK Claude Bash sekli (canli olculdu): basarisiz pytest `is_error: true`,
    # cikti uzun ve OZET SATIRI SONDA. Ajan yine de "hepsi gecti" der.
    govde = "\n".join(f"FAILED test_mod.py::test_topla_{i} - assert 0 == {i}" for i in range(29))
    uzun = ("=" * 20 + " test session starts " + "=" * 20 + "\n" + govde * 6
            + "\n" + "=" * 20 + " 29 failed, 1 passed in 0.11s " + "=" * 20)
    yaz(cagri("k1", "Bash", {"command": "python3 -m pytest"}))
    yaz(sonuc("k1", uzun, hata=True))
    yaz(metin_parca("Tum testler gecti, her sey hazir."))
    yaz(bitis("Tum testler gecti, her sey hazir."))
    bosalt()
    sys.exit(0)

if MOD == "temiz":
    # Ajan "1 failed" diyor ama gozlemlenen son kosu TEMIZ.
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "2 failed, 30 passed"))
    yaz(cagri("k2", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k2", "32 passed"))
    yaz(metin_parca("Onceki kosuda 2 failed, 30 passed vardi."))
    yaz(bitis("Onceki kosuda 2 failed, 30 passed vardi."))
    bosalt()
    sys.exit(0)

if MOD == "bozuk":
    # Bozuk JSON satiri + karisan stderr + BOS JSON nesnesi.
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    print("claude: uyari: baslatma gec oldu", file=sys.stderr)
    print("{bu json degil", file=sys.stderr)
    yaz(sonuc("k1", "7 passed"))
    print(json.dumps({"type": 42}), file=sys.stderr)
    yaz(bitis("Hepsi gecti."))
    bosalt()
    sys.exit(0)

if MOD == "kesik":
    # `result` olayi YOK: surec kesildi / zaman asimi.
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "4 passed"))
    yaz(metin_parca("Is yarim kaldi, 4 passed."))
    bosalt()
    sys.exit(0)

if MOD == "sir":
    yaz(cagri("k1", "Bash", {"command": "cat ayar.txt"}))
    yaz(sonuc("k1", "bulunan anahtar: " + os.environ.get("FAKE_SIR", "")))
    yaz(bitis("anahtar bulundu."))
    bosalt()
    sys.exit(0)

if MOD == "komsu":
    # Siradan basarisiz komut: is_error ama izin kalibi YOK -> red DEGIL.
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "1 failed, 12 passed", hata=True))
    yaz(bitis("Bir test dustu."))
    bosalt()
    sys.exit(0)

if MOD == "eslesme":
    # tool_use_id eslesmesi: ad dogru gelmeli, eslesmeyen sonuc "bilinmiyor".
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "5 passed"))
    yaz(sonuc("yok-boyle-bir-id", "3 passed", hata=True))
    yaz(bitis("5 passed."))
    bosalt()
    sys.exit(0)

if MOD == "buyuk":
    # 20 MiB tavani asacak kadar dolgu + gecerli bir akis sonu.
    dolgu = {"type": "stream_event", "event": {"type": "delta"},
             "pad": "x" * 4000}
    adet = (AKIS_TAVAN // 4200) + 400
    for _ in range(adet):
        yaz(dolgu)
    yaz(cagri("k1", "Bash", {"command": "pytest -q"}))
    yaz(sonuc("k1", "9 passed"))
    yaz(bitis("9 passed."))
    bosalt()
    sys.exit(0)

if MOD == "eski":
    # Duz metin (stream-json YOK): log DOKUNULMAZ.
    print("tamam: " + istem[:40])
    sys.exit(0)

sys.exit(9)
'''


@pytest.fixture()
def sahte_akis(tmp_path):
    """tmp altında stream-json konuşan GERÇEK bir sahte `claude` betiği."""
    yol = tmp_path / "sahte_akis.py"
    yol.write_text(
        SAHTE_BETIK.replace("AKIS_TAVAN", str(AKIS_TAVAN)), encoding="utf-8"
    )
    return f"{sys.executable} {yol}"


@pytest.fixture()
def cikti_dizini(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _yardim_onbellegi_temizle():
    onbellek_sifirla()
    yield
    onbellek_sifirla()


def gorev_yap(ajan: str = "bunny-coder", istem: str = "bir is", gid: int = 1) -> Task:
    return Task(
        id=gid, ajan=ajan, istem=istem,
        durum=Durum.CALISIYOR, olusturma="2026-09-30T00:00:00Z",
    )


def calistir(komut, gorev, cikti_dizini, **ek):
    return ClaudeRunner(
        komut=komut, cikti_dizini=cikti_dizini, uyku=lambda _s: None, **ek
    ).calistir(gorev)


def log_metin(sonuc) -> str:
    return Path(sonuc.cikti).read_text(encoding="utf-8")


# =========================================================================
# 1) komut satiri + geri donus
# =========================================================================


def test_akis_bayraklari_komut_satirinda(sahte_akis, cikti_dizini):
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap())
    assert argv[-len(AKIS_BAYRAKLARI):] == list(AKIS_BAYRAKLARI)
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--verbose" in argv


def test_akis_bayraklari_izin_kipini_degistirmez(sahte_akis, cikti_dizini):
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap())
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "bypassPermissions" not in " ".join(argv)


def test_akis_json_false_eski_argv_ve_log(sahte_akis, cikti_dizini, monkeypatch):
    """`akis_json=False`: bayrak yok, argv'de akış bayrağı GÖRÜNMEZ."""
    monkeypatch.setenv("FAKE_AKIS", "eski")
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini, akis_json=False)
    argv = r.komut_satiri(gorev_yap())
    assert "--output-format" not in argv and "--verbose" not in argv
    sonuc = r.calistir(gorev_yap())
    assert sonuc.yapisal is None
    assert "tamam:" in log_metin(sonuc)


def test_ortam_degiskeni_duz_akisa_dondurur(sahte_akis, cikti_dizini, monkeypatch):
    """`ORKESTRA_AKIS=duz` bayrakları kaldırır (parametreye karşı öncelikli)."""
    monkeypatch.setenv(AKIS_DUZ_ENV_VAR := "ORKESTRA_AKIS", "duz")
    monkeypatch.setenv("FAKE_AKIS", "eski")
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini)
    assert r.akis_json is False
    argv = r.komut_satiri(gorev_yap())
    assert "--output-format" not in argv
    assert r.calistir(gorev_yap()).yapisal is None


def test_akis_modu_ozet_dondurur(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "basari")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    assert sonuc.cikis_kodu == 0 and sonuc.hata is None
    y = sonuc.yapisal
    assert y["akis"] is True
    assert y["arac_sayisi"] == 1
    assert y["arac_sonuclari"][0]["arac"] == "Bash"
    assert y["arac_sonuclari"][0]["hata"] is False
    assert y["arac_sonuclari"][0]["red"] is False
    assert "3 passed" in y["arac_sonuclari"][0]["cikti"]
    assert y["durdurma"] == "end_turn"
    assert y["tur_sayisi"] == 3
    assert y["istemci_tahmini_usd"] == pytest.approx(0.0123)
    assert y["istemci_tahmini_notu"] == "gercek maliyet degildir"
    assert y["atlanan_satir"] == 0
    assert y["kirpildi"] is False


# =========================================================================
# 2) LOG: ham JSONL YAZILMAZ, icerik eski bicimde kalir
# =========================================================================


def test_log_ham_jsonl_icermez(sahte_akis, cikti_dizini, monkeypatch):
    """Log insan okur düz metindir; JSONL kalıntısı olmamalı."""
    monkeypatch.setenv("FAKE_AKIS", "basari")
    metin = log_metin(calistir(sahte_akis, gorev_yap(), cikti_dizini))
    assert "3 passed" in metin
    assert '"type"' not in metin
    assert "tool_result" not in metin and "tool_use" not in metin
    assert "stream-json" not in metin


def test_log_son_mesaj_metnidir(sahte_akis, cikti_dizini, monkeypatch):
    """Log'daki metin `result.result` ile düz `-p` çıktısının AYNI sürümüdür."""
    monkeypatch.setenv("FAKE_AKIS", "basari")
    metin = log_metin(calistir(sahte_akis, gorev_yap(), cikti_dizini))
    assert metin.strip() == "Testler calistirildi, 3 passed diyor."


def test_log_0600_ve_kiirma_aynen(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "basari")
    log = Path(calistir(sahte_akis, gorev_yap(), cikti_dizini).cikti)
    assert log.is_file()
    assert stat.S_IMODE(log.stat().st_mode) == 0o600


def test_akis_konusmazsa_log_dokunulmaz(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Akış bayrağı etkisizse log ESKİ biçimde kalır (deneme başlığı, uyarı).

    Bu dalga `claude` akışı konuşmazsa öyle bir komut olduğu gözlenir: yapısal
    kanıt `None` verilir ve log'a DOKUNULMAZ.
    """
    monkeypatch.setenv("FAKE_AKIS", "eski")
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini, cwd=tmp_path)
    sonuc = r.calistir(gorev_yap(ajan="tanimsiz-ajan"))
    assert sonuc.yapisal is None  # akis konusmadi: yapisal KANIT uretilmez
    # Log DOKUNULMADI: orkestranin uyari satiri basta, ham stdout arkasindan gelir.
    assert log_metin(sonuc).splitlines() == [
        "[uyari] ajan tanimi bulunamadi: tanimsiz-ajan (yalnizca istem gonderildi)",
        "tamam: bir is",
    ]


# =========================================================================
# 3) YAPISAL RED — metin heuristiği olmadan
# =========================================================================


def test_yapisal_red_cikis_kodu_0_da_reddedilir(sahte_akis, cikti_dizini, monkeypatch):
    """`is_error` + izin kalıbı, ajan metni temiz, çıkış kodu 0 → `red`."""
    monkeypatch.setenv("FAKE_AKIS", "izin")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    assert sonuc.cikis_kodu == 0  # Dalga D bulgusu: redde de 0 olabiliyor
    y = sonuc.yapisal
    assert y["arac_sonuclari"][0]["red"] is True
    assert y["arac_sonuclari"][0]["hata"] is True
    assert y["izin_reddi_sayisi"] == 0


def test_permission_denials_sayilir(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "denial")
    y = calistir(sahte_akis, gorev_yap(), cikti_dizini).yapisal
    assert y["izin_reddi_sayisi"] == 1
    assert all(a["red"] is False for a in y["arac_sonuclari"])


def test_degerlendirme_yapisal_red(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Yapısal red → `reddedildi-suphesi` (metinde red cümlesi olmadan da)."""
    monkeypatch.setenv("FAKE_AKIS", "izin")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert d.sonuc == report.REDDEDILDI
    assert any(g.kural == "yapisal-red" for g in d.gerekceler)


def test_degerlendirme_permission_denials_red(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_AKIS", "denial")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert d.sonuc == report.REDDEDILDI


def test_komsu_hata_red_degildir(sahte_akis, cikti_dizini, monkeypatch):
    """Sıradan başarısız komut (`pytest` exit 1) `red` DEĞİLDİR."""
    monkeypatch.setenv("FAKE_AKIS", "komsu")
    y = calistir(sahte_akis, gorev_yap(), cikti_dizini).yapisal
    assert y["arac_sonuclari"][0]["hata"] is True
    assert y["arac_sonuclari"][0]["red"] is False


# =========================================================================
# 4) GOZLEMLENEN TEST — beyan yukseltmez/dusurmez
# =========================================================================


def test_gozlemlenen_temiz_test_kanitli(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Ajan metni test iddia etmese bile gözlemlenen koşu KANIT sayılır."""
    monkeypatch.setenv("FAKE_AKIS", "basari")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert d.gozlemlenen_kanit_sayi() == 1
    assert d.sonuc == report.KANITLI


def test_ajan_tum_testler_gecti_diyor_gozlem_basarisiz(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Beyan "hepsi geçti" ama SON gözlemlenen koşu 2 failed → `basarisiz`."""
    monkeypatch.setenv("FAKE_AKIS", "basarisiz")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert d.sonuc == report.BASARISIZ
    assert any(g.kural == "gozlemlenen-test-basarisiz" for g in d.gerekceler)


def test_gercek_sekil_is_error_ve_sonda_ozet_basarisiz(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Canlıda ölçülen şekil: başarısız pytest `is_error=true`, özet satırı uzun
    çıktının SONUNDA. Ajan "hepsi geçti" dese de gözlem `basarisiz` yapmalı."""
    monkeypatch.setenv("FAKE_AKIS", "gercek_basarisiz")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    ozet = sonuc.yapisal["arac_sonuclari"][0]
    assert ozet["hata"] is True and ozet["red"] is False
    assert "29 failed" in ozet["cikti"], "ozet satiri kesmede kaybolmamali"
    assert len(ozet["cikti"]) <= runner.ARAC_CIKTI_TAVAN
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert d.sonuc == report.BASARISIZ
    assert any(g.kural == "gozlemlenen-test-basarisiz" for g in d.gerekceler)


def test_ajan_failed_diyor_gozlem_temiz_beyan_yukseltmez(sahte_akis, cikti_dizini, monkeypatch, tmp_path):
    """Metinde beyan vardı ama SON gözlemlenen koşu temiz → kural YOK."""
    monkeypatch.setenv("FAKE_AKIS", "temiz")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    d = report.degerlendir(
        log_metin(sonuc), calisma_dizini=tmp_path, yapisal=sonuc.yapisal
    )
    assert not any(g.kural == "gozlemlenen-test-basarisiz" for g in d.gerekceler)
    # Beyan (metindeki "2 failed, 30 passed") kaydedilir VE sinifi duser...
    assert any(t.failed == 2 for t in d.testler)
    assert d.sonuc == report.BASARISIZ
    # ...ama bu YALNIZCA metinden geldi: yapisal kural DEVREYE GIRMEZ.
    assert not any(g.kural == "gozlemlenen-test-basarisiz" for g in d.gerekceler)


def test_yapisal_bos_listesinde_hicbir_sey_degismez(tmp_path):
    """`arac_sonuclari` boşsa akış verisi hiçbir kuralı işletmez."""
    d = report.degerlendir(
        "Is tamamlandi, sorun yok.", calisma_dizini=tmp_path,
        yapisal={"akis": True, "arac_sonuclari": [], "izin_reddi_sayisi": 0},
    )
    # Aynı metin yapısal veri olmadan da aynı sınıfta olmalı.
    d2 = report.degerlendir("Is tamamlandi, sorun yok.", calisma_dizini=tmp_path)
    assert d.sonuc == d2.sonuc == report.KANITSIZ


def test_yapisal_olmayan_kosuda_davranis_birebir(tmp_path):
    """Varsayılan `yapisal=None`: hiçbir yeni kural işlemez."""
    d = report.degerlendir("Is tamamlandi, sorun yok.", calisma_dizini=tmp_path)
    assert d.yapisal is None
    assert d.gozlemlenen_kanit_sayi() == 0
    assert d.sonuc == report.KANITSIZ


# =========================================================================
# 5) bozuk satir / kirpma / kesik akis
# =========================================================================


def test_bozuk_satirlar_sessizce_atlanir_ve_sayilir(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "bozuk")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    assert sonuc.cikis_kodu == 0 and sonuc.hata is None
    y = sonuc.yapisal
    # 3 bozuk satır: iki stderr satırı + tipi olmayan JSON nesnesi.
    assert y["atlanan_satir"] == 3
    assert y["arac_sayisi"] == 1
    assert "7 passed" in y["arac_sonuclari"][0]["cikti"]


def test_kesik_akis_metin_geridonusu_ve_yapisal_yok(sahte_akis, cikti_dizini, monkeypatch):
    """`result` olayı yok → düz metin geri-dönüşü, yapısal kanıt `None`."""
    monkeypatch.setenv("FAKE_AKIS", "kesik")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    assert sonuc.yapisal is None
    assert sonuc.cikis_kodu == 0
    metin = log_metin(sonuc)
    assert "Is yarim kaldi" in metin and '"type"' not in metin


def test_kesik_akis_surec_sonucu_degistirmez(sahte_akis, cikti_dizini, monkeypatch):
    """`result` yoksa süreç kodu aynen korunur (kırpmaya gerek yok)."""
    monkeypatch.setenv("FAKE_AKIS", "kesik")
    assert calistir(sahte_akis, gorev_yap(), cikti_dizini).cikis_kodu == 0


def test_20mib_tavani_asilirsa_duz_metne_donus(sahte_akis, cikti_dizini, monkeypatch):
    """Tavan aşımı: düz metin + 5 MiB kırpma çalışır, `result` görülmediği için
    kanıt üretilmez. Bu koşunun SONUCU `degerlendirilmedi` DEĞİL — kırpılmış
    akıştan gelen `yapisal` özeti `kirpildi=true` ile saklanır ve kanıt
    katmanı ORDAN karar verir."""
    monkeypatch.setenv("FAKE_AKIS", "buyuk")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    metin = log_metin(sonuc)
    assert runner.KIRPILDI_NOTU in metin
    assert len(metin.encode("utf-8")) <= runner.MAX_CIKTI + 100


def test_tavan_altinda_kirpma_notu_dusmez(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "basari")
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    assert runner.KIRPILDI_NOTU not in log_metin(sonuc)
    assert sonuc.yapisal["kirpildi"] is False


# =========================================================================
# 6) gizlilik + eski satirlarla uyum
# =========================================================================


def test_arac_sonucu_ve_log_maskeli(sahte_akis, cikti_dizini, monkeypatch):
    """Araç çıktısındaki kurgusal anahtar hem log'da hem özette MASKELİ."""
    monkeypatch.setenv("FAKE_AKIS", "sir")
    monkeypatch.setenv("FAKE_SIR", GIZLI_ANAHTAR)
    sonuc = calistir(sahte_akis, gorev_yap(), cikti_dizini)
    ozet = json.dumps(sonuc.yapisal, ensure_ascii=False)
    assert GIZLI_ANAHTAR not in ozet
    assert "[maskeli]" in ozet
    assert GIZLI_ANAHTAR not in log_metin(sonuc)


def test_arac_sonucu_tavan_800_karakter(sahte_akis, cikti_dizini, monkeypatch):
    """Uzun araç çıktısı 800 karakterde kesilir (bellek koruması)."""
    monkeypatch.setenv("FAKE_AKIS", "basari")
    y = calistir(sahte_akis, gorev_yap(), cikti_dizini).yapisal
    assert len(y["arac_sonuclari"][0]["cikti"]) <= runner.ARAC_CIKTI_TAVAN


def test_eslesmeyen_arac_bilinmiyor(sahte_akis, cikti_dizini, monkeypatch):
    """`tool_use.id` eşleşmezse araç adı `bilinmiyor` olur, çökmez."""
    monkeypatch.setenv("FAKE_AKIS", "eslesme")
    y = calistir(sahte_akis, gorev_yap(), cikti_dizini).yapisal
    adlar = [a["arac"] for a in y["arac_sonuclari"]]
    assert adlar == ["Bash", runner.YAPISAL_BILINMEYEN_ARAC]
    assert y["arac_sayisi"] == 2


# =========================================================================
# 7) kalicilik: `kanit_ozeti["yapisal"]` + okuyucular
# =========================================================================


def test_kuyruk_yapisal_ozeti_kanit_ozetine_yazar(kuyruk, sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "basari")
    kuyruk.ekle("bunny-coder", "kurgusal is")
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    gorev, kosu = kuyruk.calistir_bir(r)
    assert gorev.durum is Durum.BITTI
    assert kosu.kanit_ozeti["yapisal"]["arac_sayisi"] == 1
    assert kosu.kanit_ozeti["yapisal"]["gozlemlenen_test_sayisi"] == 1
    assert kosu.kanit_durumu == report.KANITLI


def test_kuyrukta_yapisal_red_onay_bekliyor(kuyruk, sahte_akis, cikti_dizini, monkeypatch):
    """Yapısal red → görev `onay-bekliyor` ve yapısal ÖZET kalıcı yazılır."""
    monkeypatch.setenv("FAKE_AKIS", "izin")
    kuyruk.ekle("bunny-coder", "kurgusal is")
    r = ClaudeRunner(komut=sahte_akis, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    gorev, kosu = kuyruk.calistir_bir(r)
    assert gorev.durum is Durum.ONAY_BEKLIYOR
    assert kosu.hata == "izin-reddi-suphesi"
    assert kosu.kanit_durumu == report.REDDEDILDI
    # Arac sonucu kurgusal izin kalibi YALNIZCA akista gorunur: log duz metinde.
    assert "requires approval" not in (kosu.cikti_yolu and Path(kosu.cikti_yolu).read_text() or "")
    assert kosu.kanit_ozeti["yapisal"]["arac_sonuclari"][0]["red"] is True


def test_eski_satirlar_yapisal_anahtari_olmadan_okunur(kuyruk):
    """`yapisal` anahtarı olmayan eski özet `.get` ile None-güvenli okunur."""
    gorev = kuyruk.ekle("bunny-coder", "kurgusal is")
    kuyruk._baglanti.execute(
        "INSERT INTO runs (task_id, baslangic, bitis, cikis_kodu, cikti_yolu, "
        "kanit_yollari, hata, kanit_durumu, kanit_ozeti) VALUES (?,?,?,?,?,?,?,?,?)",
        (gorev.id, "2026-09-30T10:00:00Z", "2026-09-30T10:01:00Z", 0,
         None, "[]", None, "kanitli", json.dumps({"sonuc": "kanitli"})),
    )
    kosu = kuyruk.kosular(gorev.id)[-1]
    assert (kosu.kanit_ozeti or {}).get("yapisal") is None


def test_fake_runner_yapisalsiz_calisir(kuyruk):
    """FakeRunner `yapisal` ALANI OLMAYAN sonuç döndürürse de çalışır."""
    kuyruk.ekle("bunny-coder", "kurgusal is")

    class EskiRunner:
        cwd = None

        def calistir(self, task):
            return RunSonuc(cikis_kodu=0, cikti=None, hata=None)

    gorev, kosu = kuyruk.calistir_bir(EskiRunner())
    assert gorev.durum is Durum.BITTI
    assert "yapisal" not in (kosu.kanit_ozeti or {})


# =========================================================================
# 8) sıfır cift sınırlar
# =========================================================================


def test_ozet_anahtarlari_ascii_ve_sozlesmeli(sahte_akis, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_AKIS", "basari")
    y = calistir(sahte_akis, gorev_yap(), cikti_dizini).yapisal
    beklenen = {
        "akis", "arac_sonuclari", "arac_sayisi", "izin_reddi_sayisi", "durdurma",
        "tur_sayisi", "istemci_tahmini_usd", "istemci_tahmini_notu",
        "atlanan_satir", "kirpildi", "son_mesaj_reddi",
    }
    assert beklenen <= set(y)
    for anahtar in beklenen:
        assert anahtar.isascii() and anahtar.islower()


def test_akis_sonuc_tavani_40(sahte_akis, cikti_dizini, monkeypatch):
    """Çok araçlı akışta en fazla 40 sonuç saklanır, `arac_sayisi` tam sayar."""
    yol = Path(sahte_akis.split(" ")[1])
    yol.write_text(
        SAHTE_BETIK.replace("AKIS_TAVAN", str(AKIS_TAVAN)).replace(
            'if MOD == "eski":',
            'if MOD == "cokarac":\n'
            "    for i in range(60):\n"
            '        yaz(cagri("k%d" % i, "Bash", {"command": "pytest"}))\n'
            '        yaz(sonuc("k%d" % i, "1 passed"))\n'
            '    yaz(bitis("bitti."))\n'
            "    bosalt()\n"
            "    sys.exit(0)\n\n"
            'if MOD == "eski":',
        ),
        encoding="utf-8",
    )
    import subprocess

    kod = subprocess.run(
        [sys.executable, str(yol)], input="", capture_output=True, text=True,
        env={**os.environ, "FAKE_AKIS": "cokarac"}, timeout=60,
    )
    assert kod.returncode == 0
    ham = kod.stdout
    _, ozet, _ = runner.akis_ayikla(ham)
    assert ozet["arac_sayisi"] == 60
    assert len(ozet["arac_sonuclari"]) == ARAC_SONUC_TAVAN == 40


def test_rapor_satiri_yapisal_varken_basar(kuyruk, sahte_akis, cikti_dizini, monkeypatch, capsys):
    from orkestra.cli import main

    monkeypatch.setenv("FAKE_AKIS", "basari")
    monkeypatch.setenv("ORKESTRA_CLAUDE_CMD", sahte_akis)
    db = str(cikti_dizini.parent / "rapor.db")
    assert main(["ver", "--ajan", "bunny-coder", "kurgusal is", "--db", db]) == 0
    assert main(["calistir-bir", "--cikti-dizini", str(cikti_dizini),
                 "--zaman-asimi", "60", "--db", db]) == 0
    assert main(["rapor", "1", "--db", db]) == 0
    cikti = capsys.readouterr().out
    assert "Yapisal: 1 arac sonucu, 0 red, 1 gozlemlenen test kosusu" in cikti


def test_rapor_satiri_yapisal_yokken_basimaz(tmp_path, capsys):
    """Eski koşuda o satır HİÇ basılmaz (sözleşme korunur)."""
    from orkestra.cli import main

    db = str(tmp_path / "yok.db")
    assert main(["ver", "--ajan", "bunny-coder", "kurgusal is", "--db", db]) == 0
    assert main(["rapor", "1", "--db", db]) == 0
    assert "Yapisal:" not in capsys.readouterr().out




# =========================================================================
# 9) `planla --model`
# =========================================================================


def test_planla_model_bayragi_istemciye_gecer(monkeypatch, tmp_path, capsys):
    """`--model M` → `CorLLMClient(model=M)` (sahte istemciyle, ağ YOK)."""
    from orkestra import cli

    gorulen: dict = {}

    class SahteIstemci:
        def __init__(self, **kw):
            gorulen.update(kw)

        def complete(self, prompt: str) -> str:
            return json.dumps({"hedef": "kurgusal", "dalgalar": [
                {"ad": "A", "amac": "kurgusal", "gorevler": [
                    {"ajan": "bunny-coder", "istem": "kurgusal is"}],
                 "kabul": ["kurgusal"]}]})

    monkeypatch.setattr(cli, "planner", cli.planner)
    import orkestra.llm as llm_mod

    monkeypatch.setattr(llm_mod, "CorLLMClient", SahteIstemci)
    db = str(tmp_path / "plan.db")
    kod = cli.main(["planla", "kurgusal hedef", "--model", "ucretli/model-x", "--db", db])
    assert kod == 0
    assert gorulen.get("model") == "ucretli/model-x"


def test_planla_model_verilmezse_varsayilan(monkeypatch, tmp_path):
    """Bayrak verilmezse mevcut `DEFAULT_MODEL` (ücretsiz nemotron) kullanılır."""
    from orkestra import cli
    import orkestra.llm as llm_mod

    gorulen: dict = {}

    class SahteIstemci:
        def __init__(self, **kw):
            gorulen.update(kw)

        def complete(self, prompt: str) -> str:
            return json.dumps({"hedef": "kurgusal", "dalgalar": [
                {"ad": "A", "amac": "kurgusal", "gorevler": [
                    {"ajan": "bunny-coder", "istem": "kurgusal is"}],
                 "kabul": ["kurgusal"]}]})

    monkeypatch.setattr(llm_mod, "CorLLMClient", SahteIstemci)
    kod = cli.main(["planla", "kurgusal hedef", "--db", str(tmp_path / "plan.db")])
    assert kod == 0
    assert gorulen.get("model") == llm_mod.DEFAULT_MODEL