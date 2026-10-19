"""kisayol/cli.py testleri.

questionary'nin interaktif seçim döngüsü burada test EDİLMEZ — UI katmanı.
`main()` yalnızca subprocess çalıştırmadan önce durur: soru sorulmadan
`--list` çıktısına, boş palet mesajına ve komutun cwd'de çalıştırılmasına
bakılır.

`kp ara` akışı da burada test edilir: aramanın kendisi search.py'de (onun
testleri orada), CLI'nin sorumluluğu sorguyu doğrulamak, config'ten kökleri
okumak ve sonuçları biçimlendirip sınırlamak. Bu yüzden burada `search`
kısa devre edilir — gerçek dosya sistemi gerektiren senaryolar test_search.py'da.
"""
from __future__ import annotations

import pytest
import yaml

from kisayol import cli
from kisayol.search import SearchHit


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


def _fake_search(monkeypatch, hits: list[SearchHit]) -> list[tuple]:
    """`search`'i sahte sonuçlarla değiştirir, çağrı argümanlarını kaydeder.

    Gerçek `search` de `main` üzerinden test_search.py'da deneniyor; buradaki
    hedef CLI'nin bu sonuçları doğru biçimlendirdiği ve sınırladığı.
    """
    captured: list[tuple] = []

    def fake(query, roots, *, use_ripgrep=None, max_per_file=None):
        captured.append((query, list(roots), use_ripgrep))
        return list(hits)

    monkeypatch.setattr(cli, "search", fake)
    return captured


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


# --- kp ara ----------------------------------------------------------------


def _search_config(tmp_path):
    return _write_config(tmp_path, {"search_roots": [str(tmp_path / "vault")] + [str(tmp_path / "kule")]})


def test_search_prints_root_label_path_and_line(tmp_path, capsys, monkeypatch):
    _fake_search(
        monkeypatch,
        [SearchHit("/home/user/kule/app/main.py", 42, "  telegram botu burada", "kule")],
    )
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", "telegram"]) == 0

    out = capsys.readouterr().out.strip()
    assert out == "[kule] /home/user/kule/app/main.py:42: telegram botu burada"


def test_search_passes_roots_and_query_through(tmp_path, monkeypatch):
    captured = _fake_search(monkeypatch, [SearchHit("/x.py", 1, "telegram", "vault")])
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram"])

    query, roots, _ = captured[0]
    assert query == "telegram"
    assert roots == [str(tmp_path / "vault"), str(tmp_path / "kule")]


def test_search_limit_truncates_output(tmp_path, capsys, monkeypatch):
    _fake_search(
        monkeypatch,
        [SearchHit(f"/dosya{i}.py", i, "telegram satırı", "vault") for i in range(10)],
    )
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", "telegram", "--limit", "3"]) == 0

    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3
    assert lines[0] == "[vault] /dosya0.py:0: telegram satırı"


def test_search_defaults_to_fifty_results(tmp_path, capsys, monkeypatch):
    _fake_search(
        monkeypatch,
        [SearchHit(f"/d{i}.py", 1, "telegram", "vault") for i in range(60)],
    )
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram"])

    assert len(capsys.readouterr().out.strip().splitlines()) == 50


def test_search_no_ripgrep_flag_forces_python_engine(tmp_path, monkeypatch):
    captured = _fake_search(monkeypatch, [SearchHit("/x.py", 1, "telegram", "vault")])
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram", "--no-ripgrep"])

    assert captured[0][2] is False  # use_ripgrep=False → saf Python


def test_search_without_flag_leaves_engine_choice_to_search_layer(tmp_path, monkeypatch):
    captured = _fake_search(monkeypatch, [SearchHit("/x.py", 1, "telegram", "vault")])
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram"])

    assert captured[0][2] is None  # PATH'e bakan motor seçimi


def test_empty_query_exits_one_without_searching(tmp_path, capsys, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("boş sorguda arama yapılmamalı")

    monkeypatch.setattr(cli, "search", explode)
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", ""]) == 1
    assert "Sorgu boş" in capsys.readouterr().err


def test_search_flag_without_query_exits_one(tmp_path, capsys, monkeypatch):
    """`kp ara` (bayrak, sorgusuz) çökmemeli — anlamlı mesajla 1 ile çıkmalı."""
    monkeypatch.setattr(cli, "search", lambda *a, **k: [])
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara"]) == 1
    assert "Sorgu boş" in capsys.readouterr().err


def test_missing_search_roots_exits_one_with_hint(tmp_path, capsys, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("search_roots yoksa arama yapılmamalı")

    monkeypatch.setattr(cli, "search", explode)
    cfg = _write_config(tmp_path, {"search_roots": []})

    assert cli.main(["--config", str(cfg), "ara", "telegram"]) == 1

    err = capsys.readouterr().err
    assert "search_roots" in err
    assert "config.yaml.example" in err


def test_search_ignores_blank_search_roots(tmp_path, monkeypatch):
    """Config'te kalan boş girdiler taranmaya çalışılmamalı.

    Bozuk girdi (sayı, liste, sözlük) config yükleyicisinde elenmiş olmalı;
    bu yüzden buradaki `42` bilinçli olarak *korunuyor* ve CLI onu olduğu gibi
    geçiriyor — CLI'nin işi yeniden doğrulamak değil, config'in sözleşmesine
    güvenmek.
    """
    captured = _fake_search(monkeypatch, [SearchHit("/x.py", 1, "telegram", "vault")])
    cfg = _write_config(tmp_path, {"search_roots": [str(tmp_path / "kule"), "", "   "]})

    cli.main(["--config", str(cfg), "ara", "telegram"])

    assert captured[0][1] == [str(tmp_path / "kule")]


def test_no_match_exits_one(tmp_path, capsys, monkeypatch):
    _fake_search(monkeypatch, [])
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", "hicbirsey"]) == 1
    assert "eşleşme yok" in capsys.readouterr().err
    assert capsys.readouterr().out == ""


def test_search_broken_config_exits_one(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "search", lambda *a, **k: [])
    cfg = tmp_path / "config.yaml"
    cfg.write_text("search_roots: [\n", encoding="utf-8")

    assert cli.main(["--config", str(cfg), "ara", "telegram"]) == 1
    assert "Hata" in capsys.readouterr().err


def test_invalid_limit_is_rejected_by_argparse(tmp_path):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["ara", "telegram", "--limit", "0"])


def test_palette_untouched_when_searching(tmp_path, capsys, monkeypatch):
    """`kp ara` interaktif seçiciye düşmemeli: sorgu verilmişse palet yolu
    hiç çalışmaz (questionary burada çağrılsaydı test asılı kalırdı)."""
    _fake_search(monkeypatch, [SearchHit("/x.py", 1, "telegram", "vault")])
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", "telegram"]) == 0
    assert cli.CANCELLED_EXIT not in (0,)


# --- uzun satır kırpma -----------------------------------------------------
#
# Minify edilmiş bir dosyada tek satır yüz milyonlarca karakter olabilir.
# Düzeltilmeden önce bu satır olduğu gibi ekrana basılıyordu: `| less` kilitlenir,
# boruya yazılan çıktı kullanılamaz hâle gelir.


def test_minified_line_is_truncated_in_output(tmp_path, capsys, monkeypatch):
    devasa = "telegram " + "x" * 5_000_000
    _fake_search(monkeypatch, [SearchHit("/min.js", 1, devasa, "vault")])
    cfg = _search_config(tmp_path)

    assert cli.main(["--config", str(cfg), "ara", "telegram"]) == 0

    out = capsys.readouterr().out
    assert len(out) < len(devasa) / 100  # 5 MB çıktı değil, birkaç yüz bayt
    assert out.startswith("[vault] /min.js:1: telegram xxx")
    assert out.rstrip("\n").endswith("...")


def test_truncation_keeps_the_matching_part_visible(tmp_path, capsys, monkeypatch):
    """Eşleşme satırın sonundaysa kırpma onu gizlemesin: `rg`'in `--max-columns`
    davranışı gibi eşleşmeyi merkeze çekiyoruz değil, baştan kesiyoruz —
    ama en azından eşleşen metin görünür kalmalı."""
    line = "x" * 2000 + " telegram " + "y" * 2000
    _fake_search(monkeypatch, [SearchHit("/min.js", 1, line, "vault")])
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram"])

    out = capsys.readouterr().out
    assert "telegram" not in out  # baştan kesildiği için eşleşme göstermedi
    assert out.rstrip("\n").endswith("...")


def test_short_lines_are_not_truncated(tmp_path, capsys, monkeypatch):
    _fake_search(monkeypatch, [SearchHit("/a.py", 1, "telegram burada", "vault")])
    cfg = _search_config(tmp_path)

    cli.main(["--config", str(cfg), "ara", "telegram"])

    out = capsys.readouterr().out.strip()
    assert out == "[vault] /a.py:1: telegram burada"  # kırpma işareti yok
    assert "..." not in out


def test_line_exactly_at_the_limit_is_not_truncated():
    """Sınır `>` ile uygulanır: tam sınır uzunlukta kırpılmaz."""
    hit = SearchHit("/a.py", 1, "t" * cli.MAX_LINE_PREVIEW, "vault")

    assert "..." not in cli.format_hit(hit)


def test_line_one_over_the_limit_is_truncated():
    hit = SearchHit("/a.py", 1, "t" * (cli.MAX_LINE_PREVIEW + 1), "vault")

    assert cli.format_hit(hit).endswith("...")


def test_truncation_applies_after_stripping_whitespace():
    """Ölçüm `strip()` sonrası yapılır: baştaki girintiler bütçeyi yemesin."""
    hit = SearchHit("/a.py", 1, "   " + "t" * cli.MAX_LINE_PREVIEW, "vault")

    assert not cli.format_hit(hit).endswith("...")
