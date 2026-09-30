"""ClaudeRunner: gerçek bir SAHTE `claude` betiğiyle alt süreç davranışı.

`claude` hiçbir testte gerçekten çağrılmaz; `ORKESTRA_CLAUDE_CMD` ile tmp altındaki
GERÇEK bir çalıştırılabilir betik kullanılır. Gerçek anahtar test kaynağında tam
literal olarak YAZILMAZ (çalışma zamanında parçalardan kurulur).
"""

import os
import stat
import sys
import time
from pathlib import Path

import pytest

from orkestra.models import Durum, RunSonuc, Task
from orkestra.runner import (
    EN_FAZLA_DENEME,
    MAX_CIKTI,
    ClaudeRunner,
    FakeRunner,
    Runner,
    ajan_tanimi_yolu,
    frontmatter_kaldir,
    onbellek_sifirla,
    yardim_bayragi_var,
)

GIZLI_ANAHTAR = "sk-" + "a1" * 15


# -- sahte claude betigi -----------------------------------------------

# `--help` ciktisi `--agent` bayragini ICERIR: gercek `cor claude --help` ile ayni.
BETIK = '''
import os, signal, subprocess, sys, time

MOD = os.environ.get("FAKE_MODE", "basari")
SAYAC = os.environ.get("FAKE_SAYAC")
STDIN_DOSYA = os.environ.get("FAKE_STDIN")
ARGV_DOSYA = os.environ.get("FAKE_ARGV")
COCUK_DOSYA = os.environ.get("FAKE_COCUK")
BOYUT = int(os.environ.get("FAKE_BOYUT", "0"))

if "--help" in sys.argv:
    print("Usage: claude [options]")
    print("  --agent <agent>   Agent for the current session.")
    print("  --permission-mode <mode>   choices: acceptEdits, plan")
    sys.exit(0)

if ARGV_DOSYA:
    with open(ARGV_DOSYA, "w", encoding="utf-8") as f:
        f.write("\\n".join(sys.argv[1:]))

istem = sys.stdin.read()
if STDIN_DOSYA:
    with open(STDIN_DOSYA, "w", encoding="utf-8") as f:
        f.write(istem)

# Ajan tanimi govdesi sistem istemine eklendiyse burada gorunur.
ek = [a for a in sys.argv if "SEN_SISTEM_ISTEMI" in a or "ajan" in a.lower()]
if ek:
    print("EK-ARG: " + "|".join(ek))

if MOD == "uyu":
    if COCUK_DOSYA:
        cocuk = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
        with open(COCUK_DOSYA, "w", encoding="utf-8") as f:
            f.write(str(cocuk.pid))
    if os.environ.get("FAKE_SIGTERM_YOKSA"):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(300)

if MOD == "buyuk":
    sys.stdout.write("X" * BOYUT)
    sys.exit(0)

if MOD == "izin":
    print("Error: permission denied by the safety classifier (Irreversible action)")
    sys.exit(3)

if MOD == "sir":
    print("bulunan anahtar: " + os.environ.get("FAKE_SIR", ""))
    sys.exit(0)

if MOD == "hata":
    print("claude patladi: bazi seyler ters gitti")
    sys.exit(4)

if MOD == "ag":
    n = 0
    if SAYAC and os.path.exists(SAYAC):
        n = int(open(SAYAC).read() or "0")
    if SAYAC:
        with open(SAYAC, "w", encoding="utf-8") as f:
            f.write(str(n + 1))
    # Ilk iki deneme 502, ucuncu basarili.
    if n < 2:
        print("upstream 502 Bad Gateway")
        sys.exit(1)
    print("ucuncu denemede basarili")
    sys.exit(0)

print("tamam: " + istem[:40])
sys.exit(0)
'''


@pytest.fixture()
def sahte_claude(tmp_path):
    """tmp altında GERÇEK bir sahte claude betiği + onu çağıran komut listesi."""
    yol = tmp_path / "sahte_claude.py"
    yol.write_text(BETIK, encoding="utf-8")
    return f"{sys.executable} {yol}"


@pytest.fixture(autouse=True)
def _yardim_onbellegi_temizle():
    """`--help` önbelleği testler arasında sızmasın."""
    onbellek_sifirla()
    yield
    onbellek_sifirla()


@pytest.fixture()
def cikti_dizini(tmp_path):
    d = tmp_path / "runs"
    d.mkdir()
    return d


def gorev_yap(ajan: str = "bunny-coder", istem: str = "bir is", gid: int = 1) -> Task:
    return Task(
        id=gid,
        ajan=ajan,
        istem=istem,
        durum=Durum.CALISIYOR,
        olusturma="2026-09-30T00:00:00Z",
    )


def calistir(komut, gorev, cikti_dizini, **ek):
    return ClaudeRunner(
        komut=komut, cikti_dizini=cikti_dizini, uyku=lambda _s: None, **ek
    ).calistir(gorev)


# -- sozlesme / komut satiri --------------------------------------------


def test_claude_runner_runner_protokolunu_karsilar(sahte_claude, cikti_dizini):
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    assert isinstance(r, Runner)
    assert callable(r.calistir)


def test_varsayilan_komut_cor_claude_p(monkeypatch):
    monkeypatch.delenv("ORKESTRA_CLAUDE_CMD", raising=False)
    assert ClaudeRunner().komut == ["cor", "claude", "-p"]


def test_ortam_degiskeni_komutu_shlex_ile_boler(monkeypatch):
    monkeypatch.setenv("ORKESTRA_CLAUDE_CMD", "/opt/bin/claude -p --verbose")
    assert ClaudeRunner().komut == ["/opt/bin/claude", "-p", "--verbose"]


def test_komut_parametresi_ortami_ezer(monkeypatch):
    monkeypatch.setenv("ORKESTRA_CLAUDE_CMD", "/env/yolu")
    assert ClaudeRunner(komut="/verilen/yol").komut == ["/verilen/yol"]


def test_bayraklar_model_izin_ve_aletler(sahte_claude, cikti_dizini):
    r = ClaudeRunner(komut=sahte_claude, model="test-model", cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap())
    assert "--model" in argv and "test-model" in argv
    assert "--permission-mode" in argv
    assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
    assert "--allowedTools" in argv
    assert argv[argv.index("--allowedTools") + 1] == "Read,Write,Edit,Bash,Glob,Grep"


def test_bypassPermissions_komut_satirinda_yok(tmp_path, cikti_dizini):
    """Güvenlik: bypassPermissions ASLA kullanılmaz, komut satırında görünmez.

    Komut yolu test dizini adını taşımasın diye SABİT bir dizin kullanılır.
    """
    yol = tmp_path / "cc"
    yol.mkdir()
    for model in (None, "m"):
        r = ClaudeRunner(komut="/usr/bin/env cor-claude", model=model, cikti_dizini=cikti_dizini)
        argv = r.komut_satiri(gorev_yap())
        joined = " ".join(argv)
        assert "bypassPermissions" not in joined
        assert "dangerously-skip-permissions" not in joined
        assert "allow-dangerously-skip-permissions" not in joined
        # Sabit izin kipi gerçekten acceptEdits.
        assert argv[argv.index("--permission-mode") + 1] == "acceptEdits"
        assert r.komut[0] == "/usr/bin/env"


def test_bypassPermissions_kaynak_kodda_gecmiyor():
    """Çalıştırılabilir kodda (docstring/yorum hariç) geçmemeli."""
    import ast

    kaynak = Path(__file__).resolve().parent.parent / "orkestra" / "runner.py"
    agac = ast.parse(kaynak.read_text(encoding="utf-8"))

    # Yalnizca gercek docstring'leri at (ilk cumle ve get_docstring bos olan).
    def _docstringi_kaldir(dugum):
        if isinstance(dugum, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            govde = dugum.body
            if (
                govde
                and isinstance(govde[0], ast.Expr)
                and isinstance(govde[0].value, ast.Constant)
                and isinstance(govde[0].value.value, str)
                and ast.get_docstring(dugum, clean=False) is not None
            ):
                dugum.body = govde[1:]
        for alt in ast.iter_child_nodes(dugum):
            _docstringi_kaldir(alt)

    _docstringi_kaldir(agac)
    kod = ast.unparse(agac)
    assert "bypassPermissions" not in kod
    assert "dangerously-skip-permissions" not in kod
    assert "allow-dangerously-skip-permissions" not in kod
    # Sabit izin kipi gercekten acceptEdits.
    assert "acceptEdits" in kod


def test_istem_komut_satirinda_gecmez(sahte_claude, cikti_dizini):
    """İstem yalnızca STDIN'den gider; argv'de görünmez (ps'te sızmasın)."""
    istem = "COK GIZLI ISTEM METNI 12345"
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap(istem=istem))
    assert not any(istem in a for a in argv)
    assert "COK GIZLI" not in " ".join(argv)


def test_model_verilmezse_model_bayragi_yok(sahte_claude, cikti_dizini):
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini)
    assert "--model" not in r.komut_satiri(gorev_yap())


# -- ajan tanimi --------------------------------------------------------


@pytest.mark.parametrize(
    "yardim,bayrak,var",
    [
        ("  --agent <agent>  Agent for", "--agent", True),
        ("  --append-system-prompt <p>  x", "--agent", False),
        ("  -p, --print  Print", "--agent", False),
        ("", "--agent", False),
    ],
)
def test_yardim_bayragi_tespiti(yardim, bayrak, var):
    assert yardim_bayragi_var(yardim, bayrak) is var


def test_ajan_tanimi_yolu_cwd_ve_home(tmp_path, monkeypatch):
    """Önce `<cwd>`, sonra `~/.claude/agents` (HOME test altında yönlendirilir)."""
    ev = tmp_path / "ev"
    proje = tmp_path / "proje"
    (ev / ".claude" / "agents").mkdir(parents=True)
    (proje / ".claude" / "agents").mkdir(parents=True)
    (ev / ".claude" / "agents" / "a.md").write_text("ev", encoding="utf-8")
    (proje / ".claude" / "agents" / "a.md").write_text("proje", encoding="utf-8")
    monkeypatch.setenv("HOME", str(ev))
    assert ajan_tanimi_yolu("a", proje).read_text(encoding="utf-8") == "proje"
    assert ajan_tanimi_yolu("a", tmp_path).read_text(encoding="utf-8") == "ev"


def test_ajan_tanimi_yolu_yoksa_none(tmp_path):
    assert ajan_tanimi_yolu("olmayan", tmp_path) is None


@pytest.mark.parametrize("kotu", ["../kacis", "a/b", "A", "", "-x", "a b", "a\n"])
def test_ajan_tanimi_yolu_yol_gezmeyi_engeller(kotu, tmp_path):
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    assert ajan_tanimi_yolu(kotu, tmp_path) is None


def test_frontmatter_kaldir():
    assert frontmatter_kaldir("---\nname: x\n---\nGovde") == "Govde"
    assert frontmatter_kaldir("frontmatter yok") == "frontmatter yok"
    assert frontmatter_kaldir("---\nkapanmamis") == "---\nkapanmamis"


def test_tanim_dosyasi_varsa_agent_bayragi(sahte_claude, cikti_dizini, tmp_path):
    """`--agent` destekleniyorsa dosya YOLU değil AJAN ADI geçilir."""
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "bunny-coder.md").write_text("---\nname: bunny\n---\nGOVDE", encoding="utf-8")
    r = ClaudeRunner(komut=sahte_claude, cwd=tmp_path, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap())
    assert "--agent" in argv
    assert argv[argv.index("--agent") + 1] == "bunny-coder"
    # Gövde komut satırına sızmaz.
    assert not any("GOVDE" in a for a in argv)


def test_agent_desteklenmezse_append_system_prompt(tmp_path, cikti_dizini):
    """`--agent` yoksa gövde (frontmatter hariç) `--append-system-prompt` ile verilir."""
    yol = tmp_path / "sadece_help.py"
    yol.write_text(
        'import sys\nif "--help" in sys.argv:\n'
        '    print("Usage: claude\\n  --permission-mode <mode>  x")\n    sys.exit(0)\n'
        'import os\nsys.stdin.read()\nprint("ok")\n',
        encoding="utf-8",
    )
    ajanlar = tmp_path / ".claude" / "agents"
    ajanlar.mkdir(parents=True)
    (ajanlar / "bunny-coder.md").write_text("---\nname: bunny\n---\nSEN_SISTEM_ISTEMI", encoding="utf-8")
    r = ClaudeRunner(komut=f"{sys.executable} {yol}", cwd=tmp_path, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap())
    assert "--agent" not in argv
    assert "--append-system-prompt" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == "SEN_SISTEM_ISTEMI"


def test_tanim_dosyasi_yoksa_sadece_istem(sahte_claude, cikti_dizini, tmp_path):
    r = ClaudeRunner(komut=sahte_claude, cwd=tmp_path, cikti_dizini=cikti_dizini)
    argv = r.komut_satiri(gorev_yap(ajan="hic-yok"))
    assert "--agent" not in argv
    assert "--append-system-prompt" not in argv


# -- temel calistirma ---------------------------------------------------


def test_basarili_calisma(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "basari")
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    assert sonuc.cikis_kodu == 0
    assert sonuc.hata is None
    assert not sonuc.onay_gerekli
    assert sonuc.kanit_yollari == []  # D dalgasinda ayristirilacak


def test_cikti_dosyasi_olusur_ve_0600(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "basari")
    sonuc = calistir(sahte_claude, gorev_yap(gid=7), cikti_dizini)
    log = Path(sonuc.cikti)
    assert sonuc.cikti == str(log)
    assert log.is_file()
    assert log.name.startswith("7-") and log.suffix == ".log"
    assert stat.S_IMODE(log.stat().st_mode) == 0o600
    assert "tamam" in log.read_text(encoding="utf-8")


def test_cikti_dizini_0700_olusur(sahte_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "basari")
    yeni = tmp_path / "yeni-runs"
    calistir(sahte_claude, gorev_yap(), yeni)
    assert stat.S_IMODE(yeni.stat().st_mode) == 0o700


def test_sifirdan_farkli_cikis_kodu(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hata")
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    assert sonuc.cikis_kodu == 4
    assert sonuc.hata == "claude cikis kodu 4"
    assert not sonuc.onay_gerekli


def test_istem_stdin_uzerinden_gider(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "basari")
    stdin_dosya = tmp_path / "alinan-istem.txt"
    argv_dosya = tmp_path / "alinan-argv.txt"
    monkeypatch.setenv("FAKE_STDIN", str(stdin_dosya))
    monkeypatch.setenv("FAKE_ARGV", str(argv_dosya))
    istem = "merhaba orkestra, bu bir test istemidir"
    sonuc = calistir(sahte_claude, gorev_yap(istem=istem), cikti_dizini)
    assert stdin_dosya.read_text(encoding="utf-8") == istem
    # Komut satiri argumanlarinda istem GECMEZ.
    assert istem not in argv_dosya.read_text(encoding="utf-8")
    assert sonuc.cikis_kodu == 0


def test_turkce_karakterli_istem_yuvarlak_trip(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "basari")
    stdin_dosya = tmp_path / "istem.txt"
    monkeypatch.setenv("FAKE_STDIN", str(stdin_dosya))
    istem = "Şu ızgara ğğğ öüç dosyasını kontrol et; 'tırnak' ve İstanbul"
    sonuc = calistir(sahte_claude, gorev_yap(istem=istem), cikti_dizini)
    assert sonuc.cikis_kodu == 0
    assert stdin_dosya.read_text(encoding="utf-8") == istem


def test_komut_bulunamaz(cikti_dizini):
    sonuc = calistir("/yok/boyle/bir/komut/yok", gorev_yap(), cikti_dizini)
    assert sonuc.hata == "claude-bulunamadi"
    assert sonuc.cikis_kodu != 0


def test_komut_bulunamaz_yeniden_denemez(cikti_dizini, monkeypatch):
    uykalar = []
    r = ClaudeRunner(
        komut="/yok/boyle/bir/komut/yok", cikti_dizini=cikti_dizini, uyku=uykalar.append
    )
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "claude-bulunamadi"
    assert uykalar == []  # yeniden deneme YOK


# -- log gizlilik -------------------------------------------------------


def test_log_dosyasinda_sir_yok(sahte_claude, cikti_dizini, monkeypatch):
    """Sahte betik sır basar; log'da MASKELENMİŞ olarak durur."""
    monkeypatch.setenv("FAKE_MODE", "sir")
    monkeypatch.setenv("FAKE_SIR", GIZLI_ANAHTAR)
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert GIZLI_ANAHTAR not in metin
    assert "[maskeli]" in metin


def test_log_temiz_ciktida_bozulmaz(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "basari")
    sonuc = calistir(sahte_claude, gorev_yap(istem="flask-sqlalchemy-migrate-extension kur"), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert "flask-sqlalchemy-migrate-extension" in metin  # yanlış pozitif yok


# -- ag hatasi: yalnizca ag yeniden denenir ----------------------------


def test_ag_hatasi_ucuncu_denemede_basarir(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    """Sayac dosyasi: ilk 2 deneme 502, 3. deneme basarili."""
    monkeypatch.setenv("FAKE_MODE", "ag")
    sayac = tmp_path / "sayac.txt"
    monkeypatch.setenv("FAKE_SAYAC", str(sayac))
    uykalar = []
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=uykalar.append)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.cikis_kodu == 0 and sonuc.hata is None
    assert int(sayac.read_text(encoding="utf-8")) == 3
    assert uykalar == [2, 4]  # ustel geri cekilme


def test_ag_hatasi_hep_502_ise_basarisiz(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    yol = tmp_path / "hep502.py"
    yol.write_text(
        'import os,sys\ns=os.environ["FAKE_SAYAC"]\n'
        'n=int(open(s).read()) if os.path.exists(s) else 0\n'
        'open(s,"w").write(str(n+1))\nprint("502 Bad Gateway")\nsys.exit(1)\n',
        encoding="utf-8",
    )
    sayac = tmp_path / "sayac.txt"
    monkeypatch.setenv("FAKE_SAYAC", str(sayac))
    uykalar = []
    r = ClaudeRunner(
        komut=f"{sys.executable} {yol}", cikti_dizini=cikti_dizini, uyku=uykalar.append
    )
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "ag-hatasi (3 deneme)"
    assert int(sayac.read_text(encoding="utf-8")) == EN_FAZLA_DENEME
    assert len(uykalar) == 2
    assert not sonuc.onay_gerekli


def test_ag_denemeleri_ayni_loga_eklenir(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "ag")
    monkeypatch.setenv("FAKE_SAYAC", str(tmp_path / "s.txt"))
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert "--- deneme 2 ---" in metin and "--- deneme 3 ---" in metin
    assert metin.count("502 Bad Gateway") == 2
    assert "ucuncu denemede basarili" in metin


@pytest.mark.parametrize(
    "metin",
    [
        "Error: 502 Bad Gateway",
        "HTTP 503 Service Unavailable",
        "504 gateway timeout",
        "read ECONNRESET",
        "connect ETIMEDOUT",
        "getaddrinfo ENOTFOUND api.example",
        "EAI_AGAIN",
        "socket hang up",
        "Unable to connect to server",
        "network error occurred",
        "fetch failed",
        "bIR BaD gAtEwAy 502",
    ],
)
def test_ag_hatasi_desenleri(cikti_dizini, monkeypatch, tmp_path, metin):
    """Her ağ kalıbı yeniden denemeyi tetikler (3 deneme, ag-hatasi)."""
    yol = tmp_path / "hata.py"
    yol.write_text(
        f"import sys\nprint({metin!r})\nsys.exit(1)\n", encoding="utf-8"
    )
    uykalar = []
    r = ClaudeRunner(komut=f"{sys.executable} {yol}", cikti_dizini=cikti_dizini, uyku=uykalar.append)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "ag-hatasi (3 deneme)", metin
    assert len(uykalar) == 2


def test_ag_disi_hata_yeniden_denemez(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hata")
    uykalar = []
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=uykalar.append)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "claude cikis kodu 4"
    assert uykalar == []  # ağ hatası değil -> YOK


def test_uyku_enjekte_edilir_testler_beklemez(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_MODE", "ag")
    monkeypatch.setenv("FAKE_SAYAC", str(tmp_path / "s.txt"))
    uykalar = []
    bas = time.monotonic()
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=uykalar.append)
    r.calistir(gorev_yap())
    assert time.monotonic() - bas < 2.0  # 6 sn beklemedi
    assert uykalar == [2, 4]


# -- izin reddi: YENIDEN DENEMEZ ---------------------------------------


def test_izin_reddi_onay_bekliyor(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "izin")
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    assert sonuc.onay_gerekli is True
    assert sonuc.hata is None
    assert sonuc.cikis_kodu == 3  # gercek cikis kodu


def test_izin_reddi_yeniden_denemez(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    """Sayaç dosyası TAM 1 çağrı göstermeli."""
    monkeypatch.setenv("FAKE_MODE", "izin")
    argv_dosya = tmp_path / "argv.txt"
    monkeypatch.setenv("FAKE_ARGV", str(argv_dosya))
    uykalar = []
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=uykalar.append)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.onay_gerekli
    assert uykalar == []


@pytest.mark.parametrize(
    "metin",
    [
        "Error: Permission denied",
        "Permission for this action was denied",
        "request denied by the safety classifier",
        "Git Destructive action blocked",
        "This Irreversible operation requires user approval",
        "tool not allowed in this mode",
    ],
)
def test_izin_reddi_desenleri(metin, cikti_dizini, tmp_path):
    yol = tmp_path / "izin.py"
    yol.write_text(f"import sys\nprint({metin!r})\nsys.exit(5)\n", encoding="utf-8")
    uykalar = []
    r = ClaudeRunner(komut=f"{sys.executable} {yol}", cikti_dizini=cikti_dizini, uyku=uykalar.append)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.onay_gerekli is True, metin
    assert sonuc.cikis_kodu == 5
    assert uykalar == []


def test_izin_reddi_logda_kalir(sahte_claude, cikti_dizini, monkeypatch):
    """Reddi anlatan satırlar log'da kalır (kanıt)."""
    monkeypatch.setenv("FAKE_MODE", "izin")
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert "permission denied" in metin.lower()
    assert "classifier" in metin


def test_izin_reddi_kuyrukta_onay_bekliyor(kuyruk, sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "izin")
    kuyruk.ekle("bunny-coder", "is")
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    gorev, kosu = kuyruk.calistir_bir(r)
    assert gorev.durum is Durum.ONAY_BEKLIYOR
    assert kosu.hata is None
    assert kosu.cikti_yolu and Path(kosu.cikti_yolu).is_file()


# -- zaman asimi --------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX sinyal davranisi")
def test_zaman_asimi_surec_grubunu_oldurur(sahte_claude, cikti_dizini, monkeypatch, tmp_path):
    """Uuyan betik: süreç GRUBU öldürülür, ÇOCUK SÜREÇ BIRAKILMAZ."""
    monkeypatch.setenv("FAKE_MODE", "uyu")
    cocuk_dosya = tmp_path / "cocuk.pid"
    monkeypatch.setenv("FAKE_COCUK", str(cocuk_dosya))
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None, zaman_asimi=2)
    bas = time.monotonic()
    sonuc = r.calistir(gorev_yap())
    sure = time.monotonic() - bas
    assert sonuc.hata == "zaman-asimi"
    assert sonuc.cikis_kodu == 124
    assert sure < 30
    # Çocuk süreç de ölmüş olmalı.
    for _ in range(40):
        if not cocuk_dosya.exists():
            break
        time.sleep(0.25)
    assert cocuk_dosya.is_file()
    pid = int(cocuk_dosya.read_text(encoding="utf-8"))
    with pytest.raises((ProcessLookupError, PermissionError)):
        for _ in range(20):
            os.kill(pid, 0)
            time.sleep(0.25)


@pytest.mark.skipif(os.name == "nt", reason="POSIX sinyal davranisi")
def test_zaman_asimi_sonrasi_sigkill(sahte_claude, cikti_dizini, monkeypatch):
    """SIGTERM'i yok sayan süreç: 5 sn sonra SIGKILL ile öldürülür."""
    monkeypatch.setenv("FAKE_MODE", "uyu")
    monkeypatch.setenv("FAKE_SIGTERM_YOKSA", "1")
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None, zaman_asimi=1)
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "zaman-asimi"
    assert sonuc.cikis_kodu == 124


def test_zaman_asimi_yeniden_denemez(cikti_dizini, monkeypatch, tmp_path):
    yol = tmp_path / "uyu.py"
    yol.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    uykalar = []
    r = ClaudeRunner(
        komut=f"{sys.executable} {yol}", cikti_dizini=cikti_dizini, uyku=uykalar.append, zaman_asimi=1
    )
    sonuc = r.calistir(gorev_yap())
    assert sonuc.hata == "zaman-asimi"
    assert uykalar == []  # kullanici `tekrar` diyebilir


def test_zaman_asimi_log_dosyasi_yazilir(cikti_dizini, tmp_path):
    yol = tmp_path / "uyu.py"
    yol.write_text("import sys,time\nprint('basladi')\nsys.stdout.flush()\ntime.sleep(60)\n", encoding="utf-8")
    r = ClaudeRunner(
        komut=f"{sys.executable} {yol}", cikti_dizini=cikti_dizini, uyku=lambda _s: None, zaman_asimi=1
    )
    sonuc = r.calistir(gorev_yap())
    log = Path(sonuc.cikti)
    assert log.is_file() and stat.S_IMODE(log.stat().st_mode) == 0o600


# -- buyuk cikti --------------------------------------------------------


def test_buyuk_cikti_kirpilmasi(sahte_claude, cikti_dizini, monkeypatch):
    """5 MiB üstü çıktı: dosyanın SONU tutulur, başa kırpıldı notu."""
    monkeypatch.setenv("FAKE_MODE", "buyuk")
    monkeypatch.setenv("FAKE_BOYUT", str(MAX_CIKTI + 500_000))
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert metin.startswith("[kırpıldı]")
    assert len(metin.encode("utf-8")) <= MAX_CIKTI + 100
    assert sonuc.cikis_kodu == 0


def test_kucuk_cikti_kirpilmaz(sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "buyuk")
    monkeypatch.setenv("FAKE_BOYUT", "1000")
    sonuc = calistir(sahte_claude, gorev_yap(), cikti_dizini)
    metin = Path(sonuc.cikti).read_text(encoding="utf-8")
    assert not metin.startswith("[kırpıldı]")
    assert metin.count("X") == 1000


# -- kuyruk entegrasyonu ------------------------------------------------


def test_kuyrukta_basari(kuyruk, sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "basari")
    kuyruk.ekle("bunny-coder", "is")
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    gorev, kosu = kuyruk.calistir_bir(r)
    assert gorev.durum is Durum.BITTI
    assert kosu.cikti_yolu and Path(kosu.cikti_yolu).is_file()


def test_kuyrukta_hata(kuyruk, sahte_claude, cikti_dizini, monkeypatch):
    monkeypatch.setenv("FAKE_MODE", "hata")
    kuyruk.ekle("bunny-coder", "is")
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini, uyku=lambda _s: None)
    gorev, kosu = kuyruk.calistir_bir(r)
    assert gorev.durum is Durum.HATA
    assert kosu.hata == "claude cikis kodu 4"


def test_kuyrukta_bos_kuyruk_none(kuyruk, sahte_claude, cikti_dizini):
    r = ClaudeRunner(komut=sahte_claude, cikti_dizini=cikti_dizini)
    assert kuyruk.calistir_bir(r) is None


def test_fake_runner_hala_calisir(kuyruk):
    """Dalga A'nın FakeRunner'ı bozulmadı."""
    kuyruk.ekle("bunny-coder", "is")
    gorev, kosu = kuyruk.calistir_bir(FakeRunner("basari"))
    assert gorev.durum is Durum.BITTI
    assert isinstance(kosu, RunSonuc) or kosu.cikis_kodu == 0
