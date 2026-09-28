"""kısayol config yükleyici.

Varsayılan yol `~/.config/kisayol/config.yaml`, `KISAYOL_CONFIG` env'i ile
override edilir. Kule'den farklı olarak **eksik config raise etmez**: kullanıcı
tool'u ilk kez çalıştırıyorsa program çökerken değil, boş bir palet gösterip
"şuradan örnek kopyala" diyerek karşılama yapmalı — CLI'nın ilk çalıştırması
her zaman başarılı olmalı. Bu yüzden katman iki parça döner: `load_config()`
(veri) ve `CONFIG_HELP`/`help_message()` (o verinin nereden gelmesi gerektiği).

Config'te üç yol alanı vardır ve hepsi aynı kurallarla normalize edilir:
`cwd` (komutun çalışacağı dizin), `discover_roots` (palete otomatik eklenecek
repoların üst dizinleri) ve `search_roots` (`kp ara`'nın tüm içeriği
tarayacağı kökler — vault notları da buna girer). `~`/`$VAR` genişletme ve bozuk
girdi ayıklama ortak `expand_path`/`expand_paths` yardımcılarındadır, tek yerde.

Bozuk YAML'da ConfigError fırlatılır — bu bir durum hatası, kullanıcının
config'inde gerçek bir yazım hatası vardır ve sessizce yutulursa palet boş
görünür.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAME = "config.yaml"
EXAMPLE_FILENAME = "config.yaml.example"
ENV_VAR = "KISAYOL_CONFIG"

#: Bu paketin kurulu olduğu yer (kurulumdan sonra örnek dosya buradadır).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Paketle birlikte gelen şablon config'in kaynak kopyası.
EXAMPLE_SOURCE = PROJECT_ROOT / EXAMPLE_FILENAME

CONFIG_HELP = (
    "Kısayol paletin boş. Örnek config'i şuradan kopyalayıp düzenle:\n"
    "  mkdir -p {config_dir} && cp {example} {config_path}\n"
    "Alternatif yol: KISAYOL_CONFIG=/istediğin/yol/config.yaml kp"
)


class ConfigError(RuntimeError):
    """config okunamadıysa / bozuksa fırlatılır (bulunmama sayılmaz)."""


#: Yol değeri kabul eden config alanları — hepsi aynı normalizasyondan geçer.
PATH_FIELDS = ("discover_roots", "search_roots")


def expand_path(value: Any) -> str:
    """Tek bir yol değerini `~`/`$VAR` genişletilmiş hâle getirir.

    Listeleme/keşif katmanları bunu kullanır; `~` kısayolunun tamamını
    indirgemesi şart — kullanıcı `~/Mt3Ui55OS` yazıp gerçekten var olan vault'a
    işaret edebilmeli.
    """
    text = str(value).strip()
    if not text:
        return ""
    return os.path.expanduser(os.path.expandvars(text))


def expand_paths(value: Any) -> list[str]:
    """Yol listesi alanını normalize eder; bozuk girdileri sessizce atar.

    Tek bir yazım hatası tüm config'i çökertmemeli: `search_roots` içinde
    geçersiz bir giriş varsa diğer kökler taranmaya devam eder.
    """
    if not isinstance(value, list):
        return []
    expanded = (expand_path(v) for v in value if isinstance(v, (str, int, float)))
    return [p for p in expanded if p]


def default_config_path() -> Path:
    """Env override'ı varsa onu, yoksa `~/.config/kisayol/config.yaml`'ı verir."""
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".config" / "kisayol" / CONFIG_FILENAME


def help_message(config_path: Path | str | None = None) -> str:
    """Config'i nereden alacağını anlatan tek paragraf yardım mesajı."""
    path = Path(config_path) if config_path is not None else default_config_path()
    return CONFIG_HELP.format(
        config_dir=path.parent,
        example=EXAMPLE_SOURCE,
        config_path=path,
    )


def empty_config() -> dict:
    """Geçerli ama boş bir config — ilk çalıştırmada panik yaratmaz."""
    return {"items": [], "discover_roots": [], "search_roots": []}


def _expand(value: Any) -> Any:
    """Str değerlerde ~ ve env değişkenlerini genişletir; dict/list içinde recursive."""
    if isinstance(value, str):
        return os.path.expanduser(os.path.expandvars(value))
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _as_str_list(value: Any) -> list[str]:
    """Ham alanı boş-olmayan str listesine çevirir, bozuk girdiyi atar."""
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float)) and str(v).strip()]


def _as_dicts(value: Any) -> list[dict]:
    """items alanından yalnızca sözlük olanları alır, diğerlerini atar."""
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


def load_config(path: Path | str | None = None) -> dict:
    """Config'i yükler, yoksa boş config döner (raise etmez).

    Dönen dict her zaman `items`, `discover_roots` ve `search_roots`
    anahtarlarını taşır, ama boş olabilir. Item sözlükleri normalize edilir:
    eksik alanlar matcher.py'nin varsayılanlarına bırakılır.
    """
    config_path = Path(path).expanduser() if path is not None else default_config_path()

    if not config_path.exists():
        return empty_config()

    try:
        with config_path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"{config_path} okunamadı (YAML hatası): {e}") from e

    if raw is None:
        return empty_config()
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} bir sözlük olmalı, {type(raw).__name__} bulundu.")

    config = _expand(raw)
    config["items"] = _as_dicts(config.get("items"))
    for field in PATH_FIELDS:
        config[field] = expand_paths(config.get(field))
    return config
