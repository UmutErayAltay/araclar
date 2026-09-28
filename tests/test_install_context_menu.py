"""Sağ-tık menüsü kurulum mantığının testleri — saf metin işlemesi.

Windows'a, `pwsh`'a veya kayıt defterine bağımlı DEĞİLDİR: test edilen şey
`danis/context_menu.py` içindeki yer tutucu doldurma + `.reg` içerik üretme
mantığıdır. `shell/install-context-menu.ps1` yalnızca bu modülü çağıran ince
bir sarmalayıcıdır ve bu container'da PowerShell olmadığı için ÇALIŞTIRILAMAZ
(bilinen sınır; README'de belirtilir).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from danis.context_menu import (
    ANAHTAR_ADI,
    ETIKET,
    YER_TUTUCU,
    SablonHatasi,
    exe_yolu_coz,
    reg_dosyasi_yaz,
    reg_icerigi_uret,
    sablon_yolu,
    sablonu_oku,
)

SHELL_DIZINI = Path(__file__).resolve().parent.parent / "shell"

# Windows'ta `Get-Command` çıktısı gerçekten böyle gelir.
GET_COMMAND_CIKTISI = r"""
Application  C:\Users\umut\Tools\danis.exe
"""


# --------------------------------------------------------------------- #
# exe yolu çözümleme
# --------------------------------------------------------------------- #


def test_exe_yolu_coz_parses_get_command_output() -> None:
    assert exe_yolu_coz(GET_COMMAND_CIKTISI) == r"C:\Users\umut\Tools\danis.exe"


def test_exe_yolu_coz_accepts_bare_path() -> None:
    assert exe_yolu_coz(r"C:\tools\danis.exe") == r"C:\tools\danis.exe"


def test_exe_yolu_coz_strips_quotes() -> None:
    assert exe_yolu_coz('Application  "C:\\tools\\danis.exe"') == r"C:\tools\danis.exe"


def test_exe_yolu_coz_keeps_spaces_inside_quotes() -> None:
    """`C:\\Program Files\\...` — tırnaklı yolda boşluklar KORUNMALI."""
    tirmakli = 'Application  "C:\\Program Files\\danis\\danis.exe"'
    assert exe_yolu_coz(tirmakli) == r"C:\Program Files\danis\danis.exe"


def test_exe_yolu_coz_rejects_unquoted_command_name() -> None:
    """Tırnaksız, yol olmayan bir satır (fonksiyon/cmdlet adı) reddedilir.

    Tırnaksız gelen yolun içinde boşluk olamaz (Get-Command tırnaklar), bu
    yüzden ilk boşlukta kesmek doğru; "Function  danis" gibi bir komut türü
    adı da böylece exe sanılmaz.
    """
    with pytest.raises(SablonHatasi, match="Function"):
        exe_yolu_coz("Function  danis")


def test_exe_yolu_coz_takes_first_line_only() -> None:
    coklu = GET_COMMAND_CIKTISI + "\nExternal  C:\\other\\thing.exe\n"
    assert exe_yolu_coz(coklu) == r"C:\Users\umut\Tools\danis.exe"


def test_exe_yolu_coz_rejects_function_shaped_line() -> None:
    """Profil tanımlı bir `danis` FONKSİYONU exe sanılıp kaydedilmemeli.

    Get-Command -CommandType Application bunu zaten eler; savunma amaçlı,
    yanlış türde bir satır gelirse sessizce yanlış yola yazmayı reddediyoruz.
    """
    with pytest.raises(SablonHatasi, match="Function"):
        exe_yolu_coz("Function  danis")


def test_exe_yolu_coz_rejects_non_exe() -> None:
    with pytest.raises(SablonHatasi, match=r"\.exe"):
        exe_yolu_coz(r"C:\tools\danis.cmd")


def test_exe_yolu_coz_rejects_empty() -> None:
    with pytest.raises(SablonHatasi):
        exe_yolu_coz("   ")


def test_exe_yolu_coz_rejects_none() -> None:
    with pytest.raises(SablonHatasi, match="PATH"):
        exe_yolu_coz(None)


# --------------------------------------------------------------------- #
# .reg içerik üretimi
# --------------------------------------------------------------------- #


def test_shipped_template_has_placeholder_and_command() -> None:
    """Depodaki gerçek şablon sözleşmeyi karşılamalı."""
    sablon = sablonu_oku(SHELL_DIZINI)

    assert YER_TUTUCU in sablon
    assert "Windows Registry Editor Version 5.00" in sablon
    # Menü girdisi .exe dosyalarında görünsün (tüm dosyalarda değil).
    assert ANAHTAR_ADI.startswith("HKEY_CLASSES_ROOT\\*\\shell\\exefile\\")
    assert ANAHTAR_ADI.count("DanisaSor") == 1


def test_reg_icerigi_fills_placeholder() -> None:
    icerik = reg_icerigi_uret(sablonu_oku(SHELL_DIZINI), r"C:\tools\danis.exe")

    assert YER_TUTUCU not in icerik
    assert '"C:\\tools\\danis.exe" dosya "%1"' in icerik
    assert f"@=\"{ETIKET}\"" in icerik


def test_reg_icerigi_rejects_empty_exe_path() -> None:
    """Boş yol sessizce geçilmez: içeriksiz .reg menüyü bozardı."""
    with pytest.raises(SablonHatasi, match="boş"):
        reg_icerigi_uret(sablonu_oku(SHELL_DIZINI), "   ")


def test_reg_icerigi_rejects_template_without_placeholder() -> None:
    with pytest.raises(SablonHatasi, match="yer tutucusu"):
        reg_icerigi_uret("[HKEY_CLASSES_ROOT]\n@=\"yok\"\n", r"C:\tools\danis.exe")


def test_reg_icerigi_rejects_multiple_placeholders() -> None:
    """İki farklı exe yolunun karışmasını yakalar."""
    sablon = f'@="{YER_TUTUCU}" dosya "%1"\n@="{YER_TUTUCU}"\n'
    icerik = reg_icerigi_uret(sablon, r"C:\tools\danis.exe")
    # Aynı yol iki kez geçer, artık yer tutucu kalmaz.
    assert icerik.count(r"C:\tools\danis.exe") == 2


# --------------------------------------------------------------------- #
# Dosya yazma
# --------------------------------------------------------------------- #


def test_reg_dosyasi_yaz_uses_ascii_name_and_bom(tmp_path: Path) -> None:
    """reg.exe, ASCII olmayan dosya adlı .reg dosyalarını bozuk yol ile açar.

    Bu yüzden hedef ad sabit ASCII'dir ve içerik UTF-8 BOM ile yazılır.
    """
    shell = tmp_path / "shell"
    shell.mkdir()
    (shell / sablon_yolu(SHELL_DIZINI).name).write_text(
        sablonu_oku(SHELL_DIZINI), encoding="utf-8"
    )

    yazilan = reg_dosyasi_yaz(shell, r"C:\tools\danis.exe")

    assert yazilan.name == "danis-context-menu.reg"
    assert yazilan.name.isascii()
    assert yazilan.read_bytes().startswith(b"\xef\xbb\xbf"), "BOM eksik"
    icerik = yazilan.read_text(encoding="utf-8-sig")
    assert '"C:\\tools\\danis.exe" dosya "%1"' in icerik


def test_reg_dosyasi_yaz_requires_template(tmp_path: Path) -> None:
    shell = tmp_path / "shell"
    shell.mkdir()
    with pytest.raises(SablonHatasi, match="Şablon bulunamadı"):
        reg_dosyasi_yaz(shell, r"C:\tools\danis.exe")


def test_sablonu_oku_tolerates_bom(tmp_path: Path) -> None:
    """Elle düzenlenen şablonda BOM olmasın istemiyoruz ama olursa da patlamasın."""
    shell = tmp_path / "shell"
    shell.mkdir()
    (shell / sablon_yolu(SHELL_DIZINI).name).write_text(
        f"Windows Registry Editor Version 5.00\n{YER_TUTUCU}\n", encoding="utf-8-sig"
    )
    assert sablonu_oku(shell).startswith("Windows Registry Editor")


# --------------------------------------------------------------------- #
# .ps1 dosyalarının statik kontrolleri (PowerShell YOK, çalıştırılamaz)
# --------------------------------------------------------------------- #

INSTALL_PS1 = SHELL_DIZINI / "install-context-menu.ps1"
DANIS_PS1 = SHELL_DIZINI / "danis.ps1"


def test_install_script_delegates_to_tested_module() -> None:
    """Asıl mantık test edilmiş Python modülünde olmalı, .ps1'de tekrarlanmamalı."""
    metin = INSTALL_PS1.read_text(encoding="utf-8-sig")
    assert "danis.context_menu" in metin
    assert "reg_dosyasi_yaz" in metin and "exe_yolu_coz" in metin


def test_install_script_supports_dryrun_without_importing() -> None:
    """-DryRun içeriği basmalı ama `reg import` ÇALIŞTIRMAMALI."""
    metin = INSTALL_PS1.read_text(encoding="utf-8-sig")
    dryrun_donus = metin.index("if ($DryRun)")
    import_dan = metin.index("reg.exe import")
    assert dryrun_donus < import_dan, "DryRun çıkışı import'tan ÖNCE olmalı"
    assert "reg.exe import" not in metin[:dryrun_donus]


def test_danis_ps1_is_utf8_bom() -> None:
    """Windows PowerShell 5.1, BOM'suz UTF-8 .ps1'i ANSI sanıp bozar."""
    assert DANIS_PS1.read_bytes().startswith(b"\xef\xbb\xbf")


def test_danis_ps1_warns_it_is_untested() -> None:
    """Kullanıcı yanlış güvenmesin: script kendini test edilmemiş olarak ilan eder."""
    ilk_satirlar = DANIS_PS1.read_text(encoding="utf-8-sig").splitlines()[:3]
    assert any("test edilmedi" in satir for satir in ilk_satirlar)


def test_danis_ps1_is_symmetric_with_bash_hook() -> None:
    """PowerShell hook, bash hook ile aynı sözleşmeyi sunmalı."""
    metin = DANIS_PS1.read_text(encoding="utf-8-sig")
    for parca in [
        "$global:DANIS_LAST_EXIT",
        "$global:DANIS_LAST_CMD",
        "function global:prompt",
        "function global:danis",
        "Get-History",
        "çıkış",
    ]:
        assert parca in metin, f"PowerShell hook eksik: {parca}"
