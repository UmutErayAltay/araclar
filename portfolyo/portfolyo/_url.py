"""Ortak URL desenleri: bağlantılar yalnız https:// ya da güvenli göreli yol olabilir."""

import re

HTTPS_URL = re.compile(r"^https://[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?(?::\d+)?(?:[/?#][^\s\"'<>()*`]*)?$")
GORELI_URL = re.compile(r"^[A-Za-z0-9.][A-Za-z0-9._/-]*(?:#[A-Za-z0-9_-]+)?$")
