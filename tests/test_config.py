"""kisayol/config.py testleri.

Gerçek dosya sistemi (tmp_path), mock yok. Kule'den farklı olarak burada
`load_config` eksik dosyada raise ETMEZ — boş config döner, panik değil.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from kisayol import config as config_module
from kisayol.config import (
    ConfigError,
    ENV_VAR,
    default_config_path,
    empty_config,
    expand_path,
    help_message,
    load_config,
)


def _write_yaml(path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def test_load_config_missing_file_returns_empty(tmp_path):
    """Bulunmayan config bir hata değil; CLI'nın ilk çalıştırması böyle olmalı."""
    result = load_config(tmp_path / "yok.yaml")

    assert result == {"items": [], "discover_roots": [], "search_roots": []}
    assert result == empty_config()


def test_load_config_missing_file_has_help_pointing_at_example(tmp_path):
    message = help_message(tmp_path / "yok.yaml")

    assert str(tmp_path / "yok.yaml") in message
    assert "config.yaml.example" in message
    assert ENV_VAR in message


def test_load_config_reads_existing_file(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": [{"label": "a", "cwd": "/x", "command": "echo a"}], "discover_roots": ["/y"]})

    result = load_config(cfg)

    assert result["items"] == [{"label": "a", "cwd": "/x", "command": "echo a"}]
    assert result["discover_roots"] == ["/y"]


def test_load_config_empty_file_returns_empty_config(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("", encoding="utf-8")

    assert load_config(cfg) == empty_config()


def test_load_config_partial_config_fills_missing_keys(tmp_path):
    """items ya da discover_roots yoksa anahtarlar yine de döner."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": [{"label": "a", "cwd": "/x", "command": "true"}]})

    result = load_config(cfg)

    assert result["discover_roots"] == []
    assert len(result["items"]) == 1

    _write_yaml(cfg, {"discover_roots": ["/y"]})
    result = load_config(cfg)
    assert result["items"] == []


def test_load_config_expands_tilde(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "projeler").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"discover_roots": ["~/projeler"], "items": [{"label": "k", "cwd": "~/kule", "command": "true"}]})

    result = load_config(cfg)

    assert result["discover_roots"] == [str(fake_home / "projeler")]
    assert result["items"][0]["cwd"] == str(fake_home / "kule")


def test_load_config_expands_env_vars(tmp_path, monkeypatch):
    monkeypatch.setenv("KULE_BIN", "/opt/kule/bin")

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": [{"label": "kule", "cwd": "~/kule", "command": "$KULE_BIN/run"}]})

    result = load_config(cfg)

    assert result["items"][0]["command"] == "/opt/kule/bin/run"


def test_load_config_drops_malformed_items(tmp_path):
    """items içindeki geçersiz girdiler tüm config'i çökertmemeli."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": ["bir metin", 42, None, {"label": "iyi", "cwd": "/x", "command": "true"}]})

    result = load_config(cfg)

    assert result["items"] == [{"label": "iyi", "cwd": "/x", "command": "true"}]


def test_load_config_ignores_wrong_types(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": "olmayan liste", "discover_roots": {"a": 1}})

    result = load_config(cfg)

    assert result["items"] == []
    assert result["discover_roots"] == []


def test_load_config_broken_yaml_raises_config_error(tmp_path):
    """Yazım hatası sessizce yutulursa palet boş görünür; bu bir hata."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("items: [\n  - label: bozuk\n", encoding="utf-8")

    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)

    assert str(cfg) in str(exc_info.value)


def test_load_config_non_mapping_root_raises_config_error(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("- sadece\n- bir\n- liste\n", encoding="utf-8")

    with pytest.raises(ConfigError):
        load_config(cfg)


def test_default_config_path_uses_kisayol_config_env(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "else" / "config.yaml"))

    assert default_config_path() == tmp_path / "else" / "config.yaml"


def test_default_config_path_falls_back_to_xdg_home(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert default_config_path() == tmp_path / ".config" / "kisayol" / "config.yaml"


def test_load_config_uses_env_override_when_path_is_none(tmp_path, monkeypatch):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": [{"label": "env'den", "cwd": "/x", "command": "true"}]})
    monkeypatch.setenv(ENV_VAR, str(cfg))

    result = load_config()

    assert result["items"][0]["label"] == "env'den"


def test_load_config_accepts_string_path(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"discover_roots": ["/x"]})

    assert load_config(str(cfg))["discover_roots"] == ["/x"]


def test_help_message_points_to_an_example_file_that_exists(tmp_path):
    """Yardım mesajı var olmayan bir dosyayı gösteriyorsa talimat işe yaramaz."""
    message = help_message(tmp_path / "config.yaml")

    example = next(part for part in message.split() if part.endswith(config_module.EXAMPLE_FILENAME))

    assert Path(example).is_file()


# --- search_roots (Dalga B) ------------------------------------------------


def test_load_config_reads_search_roots(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"search_roots": ["/vault", "/projeler"]})

    assert load_config(cfg)["search_roots"] == ["/vault", "/projeler"]


def test_search_roots_expand_tilde_and_env(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    (fake_home / "Mt3Ui55OS").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("PROJELER", "/opt/projeler")

    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"search_roots": ["~/Mt3Ui55OS", "$PROJELER/kule"]})

    assert load_config(cfg)["search_roots"] == [
        str(fake_home / "Mt3Ui55OS"),
        "/opt/projeler/kule",
    ]


def test_search_roots_defaults_to_empty_list(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"items": [{"label": "a", "cwd": "/x", "command": "true"}]})

    assert load_config(cfg)["search_roots"] == []


def test_search_roots_drops_malformed_entries(tmp_path):
    """Tek bir bozuk girdi diğer kökleri düşürmemeli."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"search_roots": ["/iyi", "", "   ", None, {"a": 1}, 42]})

    assert load_config(cfg)["search_roots"] == ["/iyi", "42"]


def test_search_roots_ignores_wrong_type(tmp_path):
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"search_roots": "tek string"})

    assert load_config(cfg)["search_roots"] == []


def test_expand_paths_is_shared_by_both_path_fields(tmp_path, monkeypatch):
    """`discover_roots` ve `search_roots` aynı yardımcıdan geçer: aynı `~`
    genişletme kuralı, iki alanda da geçerli olmalı."""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"discover_roots": ["~/a"], "search_roots": ["~/a"]})

    result = load_config(cfg)

    assert result["discover_roots"] == result["search_roots"] == [str(tmp_path / "a")]


def test_expand_path_expands_tilde_and_env(monkeypatch):
    monkeypatch.setenv("HOME", "/home/test")
    monkeypatch.setenv("VAR", "/opt/x")

    assert expand_path("~/kule") == "/home/test/kule"
    assert expand_path("$VAR/yol") == "/opt/x/yol"
    assert expand_path("") == ""
    assert expand_path("   ") == ""
    assert expand_path(42) == "42"
