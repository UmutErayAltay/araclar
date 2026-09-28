"""kisayol/discovery.py testleri.

Mock yok: tmp_path altında gerçek `.git` klasörleri kuruluyor. `.git` bir
dosya olabilir (worktree/submodule) ama bu katman yalnızca varlığına bakar,
`git init` çalıştırmaya gerek yok.
"""
from __future__ import annotations

from pathlib import Path

from kisayol import discovery
from kisayol.discovery import find_repos


def _make_repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


def test_find_repos_finds_top_level_repo(tmp_path):
    repo = _make_repo(tmp_path / "kule")

    assert [i["cwd"] for i in find_repos([tmp_path])] == [str(repo)]


def test_find_repos_finds_nested_repo(tmp_path):
    repo = _make_repo(tmp_path / "projeler" / "is" / "altinda")

    assert [i["cwd"] for i in find_repos([tmp_path])] == [str(repo)]


def test_find_repos_does_not_descend_into_repo(tmp_path):
    """Bir repo bulununca içine inilmez — iç içe repo taraması olmaz."""
    outer = _make_repo(tmp_path / "outer")
    _make_repo(outer / "vendor" / "ic-repo")

    found = [i["cwd"] for i in find_repos([tmp_path])]

    assert found == [str(outer)]


def test_find_repos_respects_max_depth(tmp_path):
    """max_depth = kökten seçilebilir en derin seviye; kökün kendisi 0."""
    _make_repo(tmp_path / "a" / "b")             # 2 -> max_depth=2'de bulunur
    _make_repo(tmp_path / "x" / "y" / "z" / "w")  # 4 -> bulunamaz
    root_repo = _make_repo(tmp_path / "kule")   # 0 -> her zaman bulunur

    found = [i["cwd"] for i in find_repos([tmp_path], max_depth=2)]

    assert found == [str(tmp_path / "a" / "b"), str(root_repo)]


def test_find_repos_skips_heavy_and_hidden_dirs(tmp_path):
    """`.venv`/node_modules içindeki .git'ler de repo sayılmaz."""
    for heavy in (".venv", "node_modules", "__pycache__", ".cache"):
        _make_repo(tmp_path / heavy / "sahte-repo")
    real = _make_repo(tmp_path / "gercek")

    found = [i["cwd"] for i in find_repos([tmp_path])]

    assert found == [str(real)]


def test_find_repos_detects_git_file(tmp_path):
    """worktree/submodule'de .git bir dosyadır; varlığı yeterli."""
    repo = tmp_path / "worktree-repo"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /else/yol\n", encoding="utf-8")

    assert [i["cwd"] for i in find_repos([tmp_path])] == [str(repo)]


def test_find_repos_missing_root_is_skipped_silently(tmp_path):
    """Yoksa/erişilemiyorsa raise etmez, diğer köklerle devam eder."""
    repo = _make_repo(tmp_path / "gercek")

    found = [i["cwd"] for i in find_repos([tmp_path / "yok", tmp_path])]

    assert found == [str(repo)]


def test_find_repos_on_file_root_is_skipped(tmp_path):
    plain = tmp_path / "not-a-dir.txt"
    plain.write_text("x", encoding="utf-8")

    assert find_repos([plain]) == []


def test_find_repos_empty_inputs(tmp_path):
    assert find_repos([]) == []
    assert find_repos(None) == []
    assert find_repos(["", "   ", None, 42]) == []


def test_find_repos_item_shape(tmp_path):
    repo = _make_repo(tmp_path / "kule")

    item = find_repos([tmp_path])[0]

    assert item["label"] == "kule"
    assert item["cwd"] == str(repo)
    assert item["tags"] == ["repo"]
    assert item["command"] == discovery.default_shell()
    assert item["command"]  # hiçbir koşulda boş komut üretilmez


def test_find_repos_dedupes_overlapping_roots(tmp_path):
    repo = _make_repo(tmp_path / "kule")

    found = [i["cwd"] for i in find_repos([tmp_path, tmp_path / "kule", repo])]

    assert found == [str(repo)]


def test_find_repos_sorts_deterministically(tmp_path):
    _make_repo(tmp_path / "zeta")
    _make_repo(tmp_path / "alpha")
    _make_repo(tmp_path / "mid")

    first = [i["label"] for i in find_repos([tmp_path])]
    second = [i["label"] for i in find_repos([tmp_path])]

    assert first == second == ["alpha", "mid", "zeta"]


def test_find_repos_expands_tilde_in_roots(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    repo = _make_repo(fake_home / "projeler" / "kule")
    monkeypatch.setenv("HOME", str(fake_home))

    found = [i["cwd"] for i in find_repos(["~/projeler"])]

    assert found == [str(repo)]


def test_find_repos_uses_shell_env_for_command(tmp_path, monkeypatch):
    _make_repo(tmp_path / "kule")
    monkeypatch.setenv("SHELL", "/bin/fish")

    assert find_repos([tmp_path])[0]["command"] == "/bin/fish"
