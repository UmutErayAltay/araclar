"""Flask uygulaması (Dalga B): salt-okunur web grafiği.

Sunucu YALNIZCA `127.0.0.1` üzerinde dinler, indeks DB'sini `mode=ro` ile açar
ve vault'a hiçbir yazma yolu yoktur.
"""

from __future__ import annotations

from .sunucu import app_olustur, calistir

__all__ = ["app_olustur", "calistir"]