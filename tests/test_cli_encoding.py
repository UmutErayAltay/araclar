"""Türkçe CLI çıktısı kısıtlı kod sayfasında ÇÖKMEMELİ — GERÇEK alt süreç.

Bu modül bir regresyon testidir. `danis --help` metni Türkçe olduğu için
("başarısız bir komutu analiz ettir", "soru (varsayılan: ...)"), stdout Windows'ta
bir KONSOLA değil bir BORUYA bağlandığında (yönlendirme, CI log toplama) varsayılan
ANSI kod sayfasına (cp1252) düşer. cp1252'de Türkçe noktasız "ı" (U+0131) yoktur;
argparse `--help`'i basarken `UnicodeEncodeError` fırlatıp süreci çökertir. Bu,
GitHub Actions `Build Windows` işinin smoke test adımını düşüren gerçek hataydı
ve normal `danis --help` yazan her kullanıcıyı da etkiliyordu.

Neden alt süreç: hata stdout/stderr'ın ENCODING'iyle ilgili. Aynı süreçte
`sys.stdout` zaten pytest tarafından yakalanıp yeniden yapılandırılmıştır;
orada `reconfigure()` çağırmak hatayı taklit etmez. Gerçek bir alt süreç, CI'ın
yaptığı şeyin (ayrı süreç + kısıtlı kod sayfası) aynısıdır.

Neden `PYTHONIOENCODING=cp1252`: normal (donmamış) `python3`'te stream kodlamasını
belirleyen tek şey budur. Donmuş PyInstaller ikilisinde bootloader bu değişkeni
YOK SAYAR (bkz. .wave_d_report.md), o yüzden ikili doğrulaması ayrıca yapılır.

Mock yok: cor için gerçek soket üzerinden çalışan sahte proxy (conftest deseni).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Iterator, NamedTuple

import pytest
from conftest import FIXTURE_DIR, FakeCorServer, messages_response

REPO_KOKU = Path(__file__).resolve().parent.parent

# Sahte cor'un döndüreceği yanıt bilerek Türkçe noktasız "ı" İÇERİYOR: bu
# karakter cp1252'de kodlanamaz, dolayısıyla hatanın gerçekten sınandığı yol
# budur (LLM'in döndürdüğü metin + CLI'nin bastığı "TEŞHİS" satırı).
TURKCE_YANIT = (
    "TEŞHİS: 'ı' karakteri noktasız yazılmış; komut kaydı eksik olabilir.\n"
    "DÜZELTME: yok"
)


class Sonuc(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def _calistir(*args: str, cor_url: str | None = None, timeout: int = 120) -> Sonuc:
    """CLI'yı GERÇEK bir alt süreç olarak, cp1252 stream kodlamasıyla çalıştırır.

    Çıktı UTF-8 olarak çözülür: düzeltme sonrası CLI utf-8 yazdığı için bu
    çözme temiz geçmeli. `errors="replace"` yalnızca testin kendi okuması için —
    testin konusu olan "çökme" ayrıca `returncode` ve stderr'da aranır.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_KOKU)
    env["PYTHONIOENCODING"] = "cp1252"
    # Python 3.7+ UTF-8 modu açık olsaydı PYTHONIOENCODING'ı EZER ve test
    # sessizce hiçbir şey sınamazdı.
    env.pop("PYTHONUTF8", None)
    if cor_url is not None:
        env["COR_BASE_URL"] = cor_url

    ham = subprocess.run(
        [sys.executable, "-m", "danis.cli", *args],
        capture_output=True,
        cwd=REPO_KOKU,
        env=env,
        timeout=timeout,
    )
    return Sonuc(
        ham.returncode,
        ham.stdout.decode("utf-8", errors="replace"),
        ham.stderr.decode("utf-8", errors="replace"),
    )


def _cokmemis(sonuc: Sonuc) -> None:
    """Çökme varlığını gösteren üç koşulu birlikte doğrular."""
    assert "UnicodeEncodeError" not in sonuc.stderr, sonuc.stderr
    assert "charmap" not in sonuc.stderr, sonuc.stderr
    assert "Traceback" not in sonuc.stderr, sonuc.stderr


@pytest.fixture
def turkce_cor() -> Iterator[FakeCorServer]:
    """Türkçe (ve kodlanamayan karakterli) yanıt veren sahte cor proxy."""
    sunucu = FakeCorServer(responses=[(200, messages_response(TURKCE_YANIT))])
    try:
        yield sunucu
    finally:
        sunucu.close()


def test_help_survives_cp1252() -> None:
    """CI'ın smoke test adımının birebir karşılığı: `danis --help` ÇÖKMEMELİ.

    Bu, düzeltmeden önce `UnicodeEncodeError` ile ölen komut.
    """
    sonuc = _calistir("--help")

    _cokmemis(sonuc)
    assert sonuc.returncode == 0
    assert "usage: danis" in sonuc.stdout
    # Türkçe alt komut yardımı basıldı mı? (düzeltmeden önce buraya ulaşılamıyordu)
    assert "başarısız bir komutu analiz ettir" in sonuc.stdout


def test_hata_command_prints_turkce_llm_answer_without_crashing(
    turkce_cor: FakeCorServer,
) -> None:
    """Gerçek `danis hata` yolu: LLM'den gelen Türkçe metin cp1252'de basılır."""
    sonuc = _calistir(
        "hata", "git psh origin main", "127", cor_url=turkce_cor.base_url
    )

    _cokmemis(sonuc)
    assert sonuc.returncode == 0
    assert "TEŞHİS" in sonuc.stdout
    # LLM yanıtındaki "ı" ya doğru basıldı ya da `errors="replace"` ile yer
    # tutucuya düştü — ikisinde de YER TUTMUŞ olmalı, hiçbiri çökmemeli.
    assert ("ı" in sonuc.stdout) or ("?" in sonuc.stdout), sonuc.stdout


def test_dosya_command_turkce_output_without_crashing(
    turkce_cor: FakeCorServer,
) -> None:
    """`danis dosya` yolu: dosya metni + LLM cevabı Türkçe basılır."""
    sonuc = _calistir(
        "dosya", str(FIXTURE_DIR / "ornek.txt"), "Tek kelimeyle özetle.",
        cor_url=turkce_cor.base_url,
    )

    _cokmemis(sonuc)
    assert sonuc.returncode == 0
    assert sonuc.stdout.strip()


def test_turkce_error_message_to_stderr_without_crashing() -> None:
    """Hata YOLU da Türkçe: mesaj stderr'a düşer, süreç çökmez, çıkış kodu 1.

    stderr'ın ayrıca sabitlenmesi gerekir: CLI'nin hata mesajları oraya yazılır
    ve cp1252'ye göre stderr farklı bir kod sayfasına bağlanabilir.
    """
    sonuc = _calistir("dosya", str(REPO_KOKU / "yok-boyle-bir-dosya-xyz.txt"))

    _cokmemis(sonuc)
    assert sonuc.returncode == 1
    assert "Dosya bulunamadı" in sonuc.stderr


def test_argparse_usage_error_without_crashing() -> None:
    """argparse kendi hata/usage metnini de basar — o yol da çökmemeli."""
    sonuc = _calistir("hata")  # eksik zorunlu argümanlar

    _cokmemis(sonuc)
    assert sonuc.returncode == 2
    assert "usage: danis hata" in sonuc.stderr


def test_streams_are_forced_to_utf8_under_cp1252() -> None:
    """Mekanizmanın kendisi: düzeltmeden sonra stream'ler utf-8'e sabitlenir.

    Bu, "çıktı bozulmadı" gözlemesinin arkasındaki gerçek nedeni doğrudan ölçer.
    """
    kod = (
        "import sys\n"
        "from danis.cli import _utf8_akislari_zorla\n"
        "_utf8_akislari_zorla()\n"
        "print(sys.stdout.encoding, sys.stdout.errors)\n"
        "print(sys.stderr.encoding, sys.stderr.errors)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_KOKU)
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)

    ham = subprocess.run(
        [sys.executable, "-c", kod],
        capture_output=True,
        cwd=REPO_KOKU,
        env=env,
        timeout=60,
    )
    assert ham.returncode == 0, ham.stderr.decode("utf-8", errors="replace")
    cikti = ham.stdout.decode("utf-8", errors="replace")
    assert cikti.splitlines() == ["utf-8 replace", "utf-8 replace"], cikti
