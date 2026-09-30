"""`shell/danis.sh` testleri — GERÇEK bash alt süreçleri, mock yok.

`PROMPT_COMMAND` yalnızca ETKİLEŞİMLİ bir shell'de çalıştığı için testler
`bash -i` ile açılan gerçek bir alt süreç kullanır.

Üç tasarım kuralı bu testleri hem okunur hem dürüst kılar:

1. Kanca HER komutu kaydeder; değişkenler `echo` ile okunursa okuma komutu
   kendi kendini kaydeder ve gözlenen değer `echo ...` olur. Bu yüzden
   gözlem `_danis_*` adlı bir yardımcı fonksiyon içinde yapılır: hook kendi
   çağrılarını `_danis*` önekiyle zaten dışlıyor, yani gözlem komutu durumu
   bozmaz — ve bu, istisna listesinin gerçekten çalıştığını da kanıtlar.
2. `===BEGIN===` / `===END===` blokları komutun kendi stdout'unu ayırır.
3. stdout ve stderr AYRI tutulur: ipucunun stderr'e düştüğü böylece kanıtlanır
   (kanca "sessizce" çalışıp yalnızca stdout'a yazmaz).

Not: bu container'da `zsh` kurulu değil, hook'un zsh dalı (`precmd_functions`)
çalıştırılamaz — bash dalı test edilir, zsh dalı elle gözden geçirilir
(bilinen ve kabul edilen sınır).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

HOOK = Path(__file__).resolve().parent.parent / "shell" / "danis.sh"

# API.md'de önerilen kasıntı komutu.
BASARISIZ_KOMUT = "ls /var/olmayan-dizin-xyz-danis-testi"

BASH_EXE = "/bin/bash"

# `_danis*` öneki hook'un kendi çağrılarını dışladığı için bu fonksiyon
# DANIS_LAST_* değişkenlerini bozmadan okur. Son satırdaki `;` şart: bash, `}`
# ile kapanmış bir tanımı satır sonu olmadan `;` ile izlemezse SONRAKİ satırı
# da tanımın parçası sanıp yutar (tanım + komut tek history girdisi olur ve
# komut hiç çalışmaz).
_GOSTER = """
_danis_test_goster() {
  echo "===BEGIN==="
  echo "EXIT=$DANIS_LAST_EXIT"
  echo "CMD=$DANIS_LAST_CMD"
  echo "===END==="
};
"""

# Aynı sebepten noktalıklı: hook'un "hiç komut kaydedilmemiş" korumasını
# sıfırdan başlatarak denemek için gerekiyor.
_SIFIRLA = """
_danis_test_sifirla() { DANIS_LAST_CMD=""; DANIS_LAST_EXIT=""; };
"""


class Sonuc(NamedTuple):
    stdout: str
    stderr: str


def _bash(script: str, path_oneshot: Path | None = None) -> Sonuc:
    """`danis.sh`'ı source eden gerçek bir etkileşimli bash çalıştırır.

    `stdin` bir dosyaya yönlendirildiği için bash bunu ETKİLEŞİMLİ sayar ve
    PROMPT_COMMAND'ı her satır sonunda tetikler. Komutlar stdin'den teker teker
    okunur, böylece "source → komut → gözlem → danis" sırası garanti edilir.
    """
    one_shot = "\nPATH=" + f'"{path_oneshot}":$PATH\n' if path_oneshot is not None else ""
    tam = f"source {HOOK}\n{one_shot}{_GOSTER}{script}\n"
    ham = subprocess.run(
        [BASH_EXE, "-i"],
        input=tam,
        capture_output=True,
        text=True,
        timeout=60,
        env={"PS1": "", "PS2": "", "PATH": "/usr/bin:/bin:/usr/local/bin", "TERM": "dumb"},
    )
    return Sonuc(ham.stdout, ham.stderr)


def _goster(cikti: str) -> dict[str, str]:
    """`===BEGIN===` bloğunu `{"EXIT": ..., "CMD": ...}` sözlüğüne çevirir."""
    blok = re.findall(r"===BEGIN===\n(.*?)===END===", cikti, re.DOTALL)[0].splitlines()
    return dict(line.split("=", 1) for line in blok)


def test_hook_captures_exit_code_and_command() -> None:
    """Kasıtlı başarısız komuttan sonra iki değişken de doğru yakalanmalı."""
    sonuc = _bash(f"{BASARISIZ_KOMUT}\n_danis_test_goster\n")

    degerler = _goster(sonuc.stdout)
    assert degerler["EXIT"] == "2"
    assert degerler["CMD"] == BASARISIZ_KOMUT


def test_hook_prints_hint_to_stderr_only() -> None:
    """Başarısızlıkta ipucu basılır — ama YALNIZCA stderr'e, otomatik LLM çağrısı YAPILMAZ.

    stdout'un kirli kalması önemlidir: kullanıcı `ls ... > cikti.txt` yaptığında
    ipucu dosyaya karışmamalıdır.
    """
    sonuc = _bash(f"{BASARISIZ_KOMUT}\n_danis_test_goster\n")

    assert "❌ (çıkış 2) — danis" in sonuc.stderr
    assert "❌" not in sonuc.stdout
    assert "TEŞHİS" not in sonuc.stdout + sonuc.stderr, "otomatik LLM çağrısı yapılmamalıydı"


def test_successful_command_does_not_print_hint() -> None:
    """Çıkış kodu 0 ise ne ipucu basılır ne de LLM çağrısı yapılır."""
    sonuc = _bash("true\n_danis_test_goster\n")

    assert "❌" not in sonuc.stdout + sonuc.stderr
    assert _goster(sonuc.stdout) == {"EXIT": "0", "CMD": "true"}


def test_hook_excludes_its_own_commands() -> None:
    """`danis`/`history`/`fc` çağrıları kaydedilmez — sonsuz döngü/gürültü olmasın."""
    degerler = _goster(
        _bash(f"{BASARISIZ_KOMUT}\ndanis\nhistory\nfc -l\n_danis_test_goster\n").stdout
    )

    assert degerler["CMD"] == BASARISIZ_KOMUT, "kanca kendi çağrılarını kaydetti"
    assert degerler["EXIT"] == "2"


def _sahte_danis_yaz(klasor: Path) -> Path:
    """PATH'e konacak sahte `danis` scripti: aldığı argümanları basar."""
    yol = klasor / "danis"
    yol.write_text('#!/bin/bash\nprintf "ARG:[%s]\\n" "$@"\n', encoding="utf-8")
    yol.chmod(0o755)
    return yol


def test_danis_function_calls_hata_subcommand_with_captured_values(
    tmp_path: Path,
) -> None:
    """Uçtan uca: `danis` fonksiyonu `hata` alt komutuna doğru argümanları götürür.

    PATH'in başına konan sahte `danis` executable'ı, fonksiyonun onu gölgeleyip
    gerçekten çağırdığını kanıtlar. Argümanlar ayrı ayrı basılır ki "argümanlar
    tırnak içinde tek string olarak mı geçti" sorusu da yanıtlanmış olsun.
    """
    _sahte_danis_yaz(tmp_path)

    sonuc = _bash(
        f"{BASARISIZ_KOMUT}\n"
        "danis\n"
        "_danis_test_goster\n",
        path_oneshot=tmp_path,
    )

    assert "ARG:[hata]" in sonuc.stdout
    assert f"ARG:[{BASARISIZ_KOMUT}]" in sonuc.stdout
    assert "ARG:[2]" in sonuc.stdout
    # `danis` çağrısından sonra durum BOZULMAMIŞ olmalı (dışlama çalışıyor).
    assert _goster(sonuc.stdout)["CMD"] == BASARISIZ_KOMUT


def test_danis_function_forwards_explicit_arguments(tmp_path: Path) -> None:
    """Argümanlı çağrı olduğu gibi alt komuta geçer (`danis dosya ...`)."""
    _sahte_danis_yaz(tmp_path)

    sonuc = _bash(
        'danis dosya "rapor.pdf" "özetle"\n',
        path_oneshot=tmp_path,
    )

    for arg in ["dosya", "rapor.pdf", "özetle"]:
        assert f"ARG:[{arg}]" in sonuc.stdout


def test_danis_without_recorded_command_is_a_clear_noop(tmp_path: Path) -> None:
    """Hiç komut kaydedilmemişken `danis` argparse hatası değil, net mesaj verir."""
    _sahte_danis_yaz(tmp_path)

    sonuc = _bash(
        f"{_SIFIRLA}_danis_test_sifirla\n"
        "danis\n"
        'echo "STATUS=$?"\n',
        path_oneshot=tmp_path,
    )

    assert "analiz edilecek komut yok" in sonuc.stderr
    assert "ARG:" not in sonuc.stdout, "CLI'ye gitmemeliydi"
    assert "STATUS=1" in sonuc.stdout


def test_hook_is_idempotent_when_sourced_twice() -> None:
    """İki kez source edilirse ikinci yükleme hiçbir şey yapmaz (geri dönüş koruması)."""
    sonuc = _bash(
        f"source {HOOK}\n"
        f"source {HOOK}\n"
        f"{BASARISIZ_KOMUT}\n"
        "_danis_test_goster\n"
    )

    assert _goster(sonuc.stdout)["EXIT"] == "2"


def test_hook_file_is_syntactically_valid() -> None:
    """bash -n: sözdizimi denetimi."""
    subprocess.run([BASH_EXE, "-n", str(HOOK)], check=True, timeout=30)


def test_hook_contains_zsh_branch() -> None:
    """zsh dalı (precmd) SİLİNMEMELİ — çalıştırılamadığı için varlığı korunur."""
    assert "precmd_functions" in HOOK.read_text(encoding="utf-8")


def test_hook_works_in_zsh() -> None:
    """zsh dalı gerçekten çalışıyor mu? zsh kuruluysa test eder.

    Bu container'da `zsh` YOK → test atlanır (bilinen ve kabul edilen sınır:
    hook'un zsh dalı yalnızca elle gözden geçirilmiştir).
    """
    if shutil.which("zsh") is None:
        pytest.skip("zsh kurulu değil; zsh dalı bu container'da test edilemez")

    ham = subprocess.run(
        ["zsh", "-i"],
        input=f"source {HOOK}\n{BASARISIZ_KOMUT}\n_danis_test_goster\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert "EXIT=2" in ham.stdout, ham.stdout + ham.stderr
