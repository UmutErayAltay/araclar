"""kisayol/search.py testleri.

Gereç olarak `tmp_path` üzerinde GERÇEK dosya ve dizinler kurulur, mock
kullanılmaz: aramanın asıl riski I/O katmanı, sahte dosya sistemiyle test
edilemez.

İki motor (ripgrep / saf Python) ayrı ayrı test edilir. "Aynı sonuç şekli"
gereksinimi üç düzeyde doğrulanır:

  1. Yapı: her iki motor da `SearchHit` üretir, alanlar ve tip aynıdır.
  2. Aynı motor, iki kez: sonuç kararlıdır.
  3. İki motor arası: **kabul edilen tek fark** `.gitignore` uygulamasıdır
     (`rg` saygı gösterir, Python taklit etmez — bkz. search.py modül notu).
     Test kullandığı tmp_path'te `.gitignore` **yazmaz**, yani bu fark ortaya
     çıkmaz ve tüm satırlar birebir eşleşir. Gerçek dünyadaki farkı gösteren
     `test_engines_differ_only_on_gitignored_files` ise farkı bilerek üretir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from kisayol import search as search_module
from kisayol.search import SearchHit, search

#: `rg` kurulu değilse "ripgrep var" senaryoları atlanır (ortam bağımlılığı).
needs_rg = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep kurulu değil")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _sample_tree(tmp_path: Path) -> Path:
    """Köklerden biri: git'li bir repo. `.gitignore` YAZILMAZ (yukarıya bak).

    mtime'lar elle sabitlenir: sıralama "en yeni dosya önce" olduğu için test
    beklenen sırayı dosya adına göre değil, mtime'a göre yazmalı — aksi halde
    test kırılganlaşır ve asıl olan şeyi (sıralama) test etmezdi.
    """
    root = tmp_path / "kule"
    _write(root / "app" / "main.py", "import os\n# telegram botu burada\nprint('çıktı')\n")
    _write(root / "app" / "notifier.py", "def send():\n    # Telegram token env'den gelir\n    pass\n")
    _write(root / "README.md", "telegram entegrasyonu var mı? yok.\n")
    (root / ".git").mkdir(parents=True)

    os.utime(root / "README.md", (1_600_000_000, 1_600_000_000))  # en eski
    os.utime(root / "app" / "notifier.py", (1_650_000_000, 1_650_000_000))
    os.utime(root / "app" / "main.py", (1_700_000_000, 1_700_000_000))  # en yeni
    return root


def _vault_tree(tmp_path: Path) -> Path:
    """Köklerden biri: git'li olmayan bir not/vault dizini (emoji'li yol)."""
    return _write(
        tmp_path / "🏰 300-Projects" / "qwen-lab" / "telegram notu.md",
        "Telegram botu notu: buraya yazıldı.\n",
    ).parents[2]


def _both_roots(tmp_path: Path) -> tuple[Path, Path]:
    return _sample_tree(tmp_path), _vault_tree(tmp_path)


def _one_file_root(tmp_path: Path, name: str, text: str) -> tuple[Path, Path]:
    """Tek dosyalık, git'siz bir kök döndürür: (kök, dosya).

    `_write` dosya yolunu döndürür ama aramanın kökü *dizin* olmalı; bu yardımcı
    ikisini karıştırmamak için var.
    """
    root = tmp_path / "kule"
    return root, _write(root / name, text)


# --- temel davranış -------------------------------------------------------


@needs_rg
def test_finds_matching_line_with_number_and_label(tmp_path):
    root, _ = _both_roots(tmp_path)

    hits = search("telegram", [root], use_ripgrep=True)

    assert hits
    first = hits[0]
    assert isinstance(first, SearchHit)
    assert first.path.endswith("main.py")
    assert first.line_number == 2
    assert "telegram" in first.line
    assert first.root_label == "kule"  # git'li kök → repo adı


def test_python_fallback_finds_the_same_thing(tmp_path):
    root, _ = _both_roots(tmp_path)

    hits = search("telegram", [root], use_ripgrep=False)

    assert [h.path for h in hits] == [
        str(root / "app" / "main.py"),
        str(root / "app" / "notifier.py"),
        str(root / "README.md"),
    ]
    assert [h.line_number for h in hits] == [2, 2, 1]
    assert hits[0].root_label == "kule"


@needs_rg
def test_both_engines_agree_on_a_plain_tree(tmp_path):
    """Yapı + içerik eşitliği. tmp_path'te .gitignore yok, tek geçerli fark bu
    testte zaten devre dışı olduğundan iki motor birebir aynı sonucu vermeli."""
    root, _ = _both_roots(tmp_path)

    with_rg = search("telegram", [root], use_ripgrep=True)
    without_rg = search("telegram", [root], use_ripgrep=False)

    assert with_rg == without_rg
    assert with_rg  # yanlışlıkla "ikisi de boş" geçmesin


@needs_rg
def test_vault_root_is_labelled_vault(tmp_path):
    _, vault = _both_roots(tmp_path)

    hits = search("telegram", [vault], use_ripgrep=True)

    assert hits
    assert {h.root_label for h in hits} == {"vault"}
    assert str(vault) in hits[0].path


@needs_rg
def test_hits_from_two_roots_keep_their_own_label(tmp_path):
    root, vault = _both_roots(tmp_path)

    hits = search("telegram", [root, vault], use_ripgrep=True)
    labels = {h.root_label for h in hits}

    assert labels == {"kule", "vault"}


# --- sıralama -------------------------------------------------------------


def test_results_are_sorted_by_mtime_newest_first(tmp_path):
    root = tmp_path / "kule"
    old = _write(root / "eski.py", "telegram eski\n")
    new = _write(root / "yeni.py", "telegram yeni\n")
    # mtime'ı açıkça ayarla: dosya yazılış sırası zaten çoğu yerde çalışsa da
    # test niyetini belirtmek için deterministik olsun.
    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))

    hits = search("telegram", [root], use_ripgrep=False)

    assert [Path(h.path).name for h in hits] == ["yeni.py", "eski.py"]


@needs_rg
def test_mtime_ordering_holds_for_ripgrep_too(tmp_path):
    root = tmp_path / "kule"
    old = _write(root / "eski.py", "telegram eski\n")
    new = _write(root / "yeni.py", "telegram yeni\n")
    os.utime(old, (1_600_000_000, 1_600_000_000))
    os.utime(new, (1_700_000_000, 1_700_000_000))

    hits = search("telegram", [root], use_ripgrep=True)

    assert [Path(h.path).name for h in hits] == ["yeni.py", "eski.py"]


def test_ordering_is_stable_for_equal_mtimes(tmp_path):
    """Eşitlikte yol/satır belirleyici — aynı komut iki kez aynı sırayı basar."""
    root = tmp_path / "kule"
    for name in ("c.py", "a.py", "b.py"):
        _write(root / name, "telegram\ntelegram\n")
        os.utime(root / name, (1_600_000_000, 1_600_000_000))

    first = search("telegram", [root], use_ripgrep=False)
    second = search("telegram", [root], use_ripgrep=False)

    assert first == second
    assert [(Path(h.path).name, h.line_number) for h in first] == [
        ("a.py", 1),
        ("a.py", 2),
        ("b.py", 1),
        ("b.py", 2),
        ("c.py", 1),
        ("c.py", 2),
    ]


# --- eşleştirme kuralları --------------------------------------------------


def test_matching_is_case_insensitive_by_default(tmp_path):
    root, _ = _one_file_root(tmp_path, "a.py", "TELEGRAM bitti\n")

    assert search("telegram", [root], use_ripgrep=False)


@needs_rg
def test_uppercase_query_is_case_sensitive_like_smart_case(tmp_path):
    root, _ = _one_file_root(tmp_path, "a.py", "telegram küçük\nTELEGRAM büyük\n")

    assert search("TELEGRAM", [root], use_ripgrep=True) == search(
        "TELEGRAM", [root], use_ripgrep=False
    )
    assert len(search("TELEGRAM", [root], use_ripgrep=True)) == 1


def test_query_is_literal_text_not_regex(tmp_path):
    """`c++`, `(not)` gibi sorgular regex hatası vermemeli, düz metin aranmalı."""
    root, _ = _one_file_root(tmp_path, "a.py", "dil c++ ve (not) yazısı\n")

    for engine in (True, False):
        hits = search("c++", [root], use_ripgrep=engine)
        assert [h.line_number for h in hits] == [1], engine

    for engine in (True, False):
        assert search("(not)", [root], use_ripgrep=engine), engine


@needs_rg
def test_regex_metacharacters_do_not_widen_the_match(tmp_path):
    """Düz metin kipi: `a.c` deseni `abc` ile eşleşmemeli."""
    root, _ = _one_file_root(tmp_path, "a.py", "abc burada\na.c burada da\n")

    hits = search("a.c", [root], use_ripgrep=True)

    assert [h.line_number for h in hits] == [2]
    assert search("a.c", [root], use_ripgrep=False) == hits


def test_matches_substrings_not_whole_words(tmp_path):
    root, _ = _one_file_root(tmp_path, "a.py", "telegram_bot_token\n")

    assert search("telegram_bot", [root], use_ripgrep=False)


# --- atlama davranışı -----------------------------------------------------


def test_binary_files_are_skipped(tmp_path):
    root = tmp_path / "kule"
    _write(root / "okunur.py", "telegram burada\n")
    # null byte → binary, hangi satır olursa olsun eşleşme sayılmaz.
    (root / "resim.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00telegram\x00" * 10)

    for engine in (True, False):
        hits = search("telegram", [root], use_ripgrep=engine)
        assert [Path(h.path).name for h in hits] == ["okunur.py"], engine


def test_heavy_and_hidden_directories_are_skipped(tmp_path):
    root = tmp_path / "kule"
    _write(root / "app" / "main.py", "telegram\n")
    for skipped in (".git", "node_modules", ".venv", "__pycache__", "dist", "build", ".claude"):
        _write(root / skipped / "bir.py", "telegram\n")

    for engine in (True, False):
        hits = search("telegram", [root], use_ripgrep=engine)
        assert [h.path for h in hits] == [str(root / "app" / "main.py")], engine


@needs_rg
def test_skip_globs_are_passed_to_ripgrep(tmp_path, monkeypatch):
    """`rg` kendiliğinden `build/`'a girmez; skip listesi glob olarak geçmeli,
    yoksa vault gibi repo olmayan köklerde iki motor farklı sonuç verir."""
    root, _ = _both_roots(tmp_path)
    captured = {}

    class FakeProc:
        returncode = 1
        stdout = b""
        stderr = b""

    def spy(argv, **kwargs):
        captured["argv"] = argv
        return FakeProc()

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(search_module.subprocess, "run", spy)

    search("telegram", [root], use_ripgrep=True)

    argv = captured["argv"]
    for name in search_module.SKIP_DIR_NAMES:
        assert f"--glob=!{name}/**" in argv, name
    # Gizli dosyalar zaten varsayılan olarak atlanıyor; bayrak verilirse
    # iki motorun kuralı bozulurdu.
    assert "--hidden" not in argv


def test_max_hits_per_file_caps_a_noisy_file(tmp_path):
    root, _ = _one_file_root(tmp_path, "cok.py", "telegram\n" * 100)

    for engine in (True, False):
        assert len(search("telegram", [root], use_ripgrep=engine, max_per_file=3)) == 3, engine


# --- asla raise etmez ------------------------------------------------------


def test_missing_root_is_skipped_not_raised(tmp_path):
    root, _ = _both_roots(tmp_path)
    other_root = tmp_path / "bos"

    # Bozuk girdiler (sayı, None, boş string) ve var olmayan dizin atlanır.
    hits = search(
        "telegram", [root, tmp_path / "yok", other_root, 42, None, "  "], use_ripgrep=False
    )

    assert hits  # var olan kök yine taranır


def test_file_as_root_is_skipped(tmp_path):
    """Kök bir dosya olursa çökmemeli, sessizce atlanmalı."""
    a_file = _write(tmp_path / "kule" / "a.py", "telegram\n")

    assert search("telegram", [a_file], use_ripgrep=False) == []


def test_unreadable_file_is_skipped_not_raised(tmp_path, monkeypatch):
    """Okunamayan dosya tüm taramayı düşürmemeli; Python motoru sessizce atlar.

    Bu yalnızca Python motorunda test edilir: `rg` dosyaları kendi alt sürecinde
    açıyor, Python'un `Path.open` monkeypatch'ini görmez. Aynı davranış `rg`
    tarafında `--no-messages` + çıkış kodu 1 + fallback zinciriyle sağlanır
    (bkz. test_broken_ripgrep_falls_back_to_python).
    """
    root = tmp_path / "kule"
    _write(root / "okunur.py", "telegram\n")
    _write(root / "kilitli.py", "telegram\n")

    def exploding_open(self, *args, **kwargs):
        if self.name == "kilitli.py":
            raise PermissionError("kilitli")
        return real_open(self, *args, **kwargs)

    real_open = Path.open
    monkeypatch.setattr(Path, "open", exploding_open)

    hits = search("telegram", [root], use_ripgrep=False)

    assert [Path(h.path).name for h in hits] == ["okunur.py"]


def test_empty_query_returns_empty_list(tmp_path):
    root, _ = _both_roots(tmp_path)

    for query in ("", "   ", None):
        assert search(query, [root], use_ripgrep=False) == []
        assert search(query, [root], use_ripgrep=True) == []


def test_no_roots_returns_empty_list():
    for roots in ([], (), None, [None, 42, ""]):
        assert search("telegram", roots, use_ripgrep=False) == []


def test_no_match_returns_empty_list(tmp_path):
    root, _ = _one_file_root(tmp_path, "a.py", "burada telegram yok\n")

    for engine in (True, False):
        assert search("bulunamayan-kelime", [root], use_ripgrep=engine) == []


def test_duplicate_roots_are_searched_once(tmp_path):
    root, _ = _both_roots(tmp_path)

    hits = search("telegram", [root, str(root), root], use_ripgrep=False)

    assert len(hits) == 3  # her dosya bir kez


def test_broken_ripgrep_falls_back_to_python(tmp_path, monkeypatch):
    """`rg` patlarsa kullanıcı boş sonuç görmemeli — Python motoru devreye girer."""
    root, _ = _both_roots(tmp_path)

    class FakeProc:
        returncode = 2
        stdout = b""
        stderr = b"rg: bir hata"

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(
        search_module.subprocess, "run", lambda *a, **k: FakeProc()
    )

    hits = search("telegram", [root], use_ripgrep=True)

    assert hits == search("telegram", [root], use_ripgrep=False)


def test_ripgrep_timeout_falls_back_to_python(tmp_path, monkeypatch):
    root, _ = _both_roots(tmp_path)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="rg", timeout=1)

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(search_module.subprocess, "run", timeout)

    assert search("telegram", [root], use_ripgrep=True) == search(
        "telegram", [root], use_ripgrep=False
    )


def test_missing_ripgrep_binary_falls_back_to_python(tmp_path, monkeypatch):
    """PATH'te `rg` yokken `use_ripgrep=True` zorlansa bile sonuç gelmeli."""
    root, _ = _both_roots(tmp_path)
    monkeypatch.setattr(search_module.shutil, "which", lambda name: None)

    assert search("telegram", [root], use_ripgrep=True) == search(
        "telegram", [root], use_ripgrep=False
    )


def test_garbled_ripgrep_output_is_ignored(tmp_path, monkeypatch):
    """Bozuk satırlar tüm sonucu düşürmemeli, atlanmalı."""
    root, _ = _both_roots(tmp_path)

    class FakeProc:
        returncode = 0
        stdout = b"bu bir duzensiz satir\n./a.py:x:telegram\n./b.py:3:telegram\n"
        stderr = b""

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(search_module.subprocess, "run", lambda *a, **k: FakeProc())

    hits = search("telegram", [root], use_ripgrep=True)

    assert [h.path for h in hits] == [str(root / "b.py")]


# --- motor seçimi ----------------------------------------------------------


@needs_rg
def test_engine_auto_detection_picks_ripgrep_when_available(tmp_path, monkeypatch):
    root, _ = _both_roots(tmp_path)
    calls = []
    real_run = subprocess.run

    def spy(argv, **kwargs):
        calls.append(argv[0])
        return real_run(argv, **kwargs)

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(search_module.subprocess, "run", spy)

    search("telegram", [root])  # use_ripgrep=None → PATH'e bakar

    assert calls and calls[0].endswith("rg")


def test_engine_auto_detection_falls_back_when_rg_absent(tmp_path, monkeypatch):
    root, _ = _both_roots(tmp_path)
    monkeypatch.setattr(search_module.shutil, "which", lambda name: None)

    assert search("telegram", [root]) == search("telegram", [root], use_ripgrep=False)


def test_ripgrep_is_invoked_with_expected_flags(tmp_path, monkeypatch):
    """`--line-number` yoksa satır numarası gelmez; sabit bayraklar regresyonda
    sessizce kaybolmasın."""
    root, _ = _both_roots(tmp_path)
    captured = {}

    class FakeProc:
        returncode = 1
        stdout = b""
        stderr = b""

    def spy(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProc()

    monkeypatch.setattr(search_module.shutil, "which", lambda name: "/usr/bin/rg")
    monkeypatch.setattr(search_module.subprocess, "run", spy)

    search("telegram", [root], use_ripgrep=True)

    argv = captured["argv"]
    assert "--line-number" in argv
    assert "--no-heading" in argv
    assert "--smart-case" in argv
    assert "--fixed-strings" in argv
    # Gizli dosyalar rg'de de varsayılan olarak atlanır → modüller aynı davranır.
    assert "--hidden" not in argv
    # Kökün içinde çalıştırılır ki göreli yollar çözülebilsin.
    assert captured["kwargs"]["cwd"] == str(root)
    assert captured["kwargs"]["timeout"] == search_module.RG_TIMEOUT


# --- .gitignore farkı ------------------------------------------------------


@needs_rg
def test_engines_differ_only_on_gitignored_files(tmp_path):
    """Kabul edilen tek fark: `rg` `.gitignore`'a uyar, Python taklit etmez.
    İzlenen dosya iki motorda da eşleşmeli, izlenmeyen yalnızca Python'da."""
    root = tmp_path / "kule"
    _write(root / ".gitignore", "config.yaml\n")
    (root / ".git").mkdir(parents=True)
    _write(root / "izlenen.py", "telegram izlenen\n")
    _write(root / "config.yaml", "telegram: gizli\n")

    with_rg = search("telegram", [root], use_ripgrep=True)
    without_rg = search("telegram", [root], use_ripgrep=False)

    assert [Path(h.path).name for h in with_rg] == ["izlenen.py"]
    assert [Path(h.path).name for h in without_rg] == ["config.yaml", "izlenen.py"]


# --- kodun iki motoru da gerçekten kullandığı -----------------------------


@needs_rg
def test_python_engine_does_not_shell_out(tmp_path, monkeypatch):
    """Saf Python yolu subprocess çağırmamalı — hız ve bağımlılıksızlık hedefi."""
    root, _ = _both_roots(tmp_path)

    def explode(*args, **kwargs):
        raise AssertionError("python motoru subprocess kullanmamalı")

    monkeypatch.setattr(search_module.subprocess, "run", explode)

    assert search("telegram", [root], use_ripgrep=False)


def test_python_engine_reads_files_and_walks_directories(tmp_path):
    """İç içe dizinlerin tamamı taranır (vault notları böyle yaşar)."""
    root = tmp_path / "vault"
    deep = root / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "not.md").write_text("telegram\n", encoding="utf-8")

    assert search("telegram", [root], use_ripgrep=False)[0].path == str(deep / "not.md")
