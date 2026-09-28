"""kisayol/cli.py testleri.

questionary'nin interaktif seçim döngüsü burada test EDİLMEZ — UI katmanı.
`main()` yalnızca subprocess çalıştırmadan önce durur: soru sorulmadan
`--list` çıktısına, boş palet mesajına ve komutun cwd'de çalıştırılmasına
bakılır.
"""
from __future__ import annotations

import yaml

from kisayol import cli


def _write_config(tmp_path, data: dict):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(yaml.safe_dump(data), encoding="utf-8")
    return cfg


def _config_with_repo(tmp_path):
    """Geçerli ama çalıştırmayacak bir config: cwd var, komut `true` değil."""
    workdir = tmp_path / "work"
    workdir.mkdir()
    return _write_config(
        tmp_path,
        {"items": [{"label": "kule testleri", "cwd": str(workdir), "command": "echo merhaba"}]},
    )


def test_list_prints_items_and_exits_zero(tmp_path, capsys):
    cfg = _config_with_repo(tmp_path)

    assert cli.main(["--config", str(cfg), "--list"]) == 0

    out = capsys.readouterr().out
    assert "kule testleri" in out
    assert "echo merhaba" in out


def test_list_output_has_one_line_per_item(tmp_path, capsys):
    """Her item ayrı cwd'de olmalı — aynı cwd'li ikinci item tekrar edilmez."""
    for name in ("bir", "iki"):
        (tmp_path / name).mkdir()
    cfg = _write_config(
        tmp_path,
        {
            "items": [
                {"label": "bir", "cwd": str(tmp_path / "bir"), "command": "true"},
                {"label": "iki", "cwd": str(tmp_path / "iki"), "command": "true"},
            ]
        },
    )

    cli.main(["--config", str(cfg), "--list"])

    assert len(capsys.readouterr().out.strip().splitlines()) == 2


def test_list_includes_discovered_repos(tmp_path, capsys):
    (tmp_path / "kule" / ".git").mkdir(parents=True)
    cfg = _write_config(tmp_path, {"discover_roots": [str(tmp_path)]})

    assert cli.main(["--config", str(cfg), "--list"]) == 0

    assert "kule" in capsys.readouterr().out


def test_empty_config_exits_one_with_help(tmp_path, capsys):
    cfg = _write_config(tmp_path, {"items": [], "discover_roots": []})

    assert cli.main(["--config", str(cfg), "--list"]) == 1

    err = capsys.readouterr().err
    assert "config.yaml.example" in err
    assert str(cfg) in err


def test_missing_config_exits_one_with_help(tmp_path, capsys):
    """Config hiç yoksa da aynı yönlendirme: örnekten kopyalanmalı."""
    missing = tmp_path / "yok.yaml"

    assert cli.main(["--config", str(missing), "--list"]) == 1

    assert "config.yaml.example" in capsys.readouterr().err


def test_unreachable_discover_root_does_not_crash(tmp_path, capsys):
    """Keşif kökü yok diye program çökmemeli; palet boşsa temiz çıkış."""
    cfg = _write_config(tmp_path, {"discover_roots": [str(tmp_path / "yok")]})

    assert cli.main(["--config", str(cfg), "--list"]) == 1
    assert "Palet boş" in capsys.readouterr().err


def test_broken_config_exits_one(tmp_path, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("items: [\n", encoding="utf-8")

    assert cli.main(["--config", str(cfg), "--list"]) == 1
    assert "Hata" in capsys.readouterr().err


def test_runs_command_in_item_cwd(tmp_path, monkeypatch):
    """Seçim questionary'ye sorulur, ama çalıştırma katmanı test edilebilir."""
    captured = {}

    def fake_run(command, shell, cwd):
        captured.update(command=command, shell=shell, cwd=cwd)
        return type("Result", (), {"returncode": 0})()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_pick", lambda items: items[0])

    workdir = tmp_path / "projeler" / "kule"
    workdir.mkdir(parents=True)
    cfg = _write_config(
        tmp_path, {"items": [{"label": "kule", "cwd": str(workdir), "command": "pytest -v"}]}
    )

    assert cli.main(["--config", str(cfg)]) == 0
    assert captured == {"command": "pytest -v", "shell": True, "cwd": str(workdir)}


def test_command_exit_code_is_propagated(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_pick", lambda items: items[0])
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 7})()
    )

    cfg = _write_config(tmp_path, {"items": [{"label": "x", "cwd": "", "command": "false"}]})

    assert cli.main(["--config", str(cfg)]) == 7


def test_pick_maps_selected_label_back_to_item(tmp_path, monkeypatch):
    """questionary seçilen `value`yi döner; liste düz metin olduğu için
    geri eşleme şart — yapılmazsa `_run` bir string üzerinde `.get` çağırır."""
    items = [
        {"label": "bir", "cwd": "/a", "command": "true", "tags": []},
        {"label": "iki", "cwd": "/b", "command": "false", "tags": []},
    ]

    class FakeQuestion:
        def __init__(self, answer):
            self._answer = answer

        def ask(self):
            return self._answer

    monkeypatch.setattr(
        cli.questionary, "select", lambda *a, **k: FakeQuestion(cli.format_item(items[1]))
    )

    assert cli._pick(items) == items[1]


def test_pick_uses_typing_to_filter_without_jk_navigation(tmp_path, monkeypatch):
    """`use_search_filter` j/k ile birlikte kabul edilmiyor; ikisi de yanlış
    ayarlanırsa questionary her `kp` çağrısında çöküyordu."""
    captured = {}

    class FakeQuestion:
        def ask(self):
            return None

    def fake_select(message, **kwargs):
        captured.update(kwargs)
        return FakeQuestion()

    monkeypatch.setattr(cli.questionary, "select", fake_select)
    cli._pick([{"label": "x", "cwd": "", "command": "true", "tags": []}])

    assert captured["use_search_filter"] is True
    assert captured["use_jk_keys"] is False
    # use_shortcuts varsayılan olarak kapalı; rakamlar arama karakteri olmalı.
    assert captured.get("use_shortcuts", False) is False


def test_cancelled_selection_runs_nothing(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("seçim iptal edilmişken komut çalışmamalı")

    monkeypatch.setattr(cli, "_pick", lambda items: None)
    monkeypatch.setattr(cli.subprocess, "run", explode)

    cfg = _write_config(tmp_path, {"items": [{"label": "x", "cwd": "", "command": "echo"}]})

    assert cli.main(["--config", str(cfg)]) == cli.CANCELLED_EXIT
