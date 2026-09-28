"""NotebookLM HTTP köprüsü.

Üçüncü parti NotebookLM otomasyon paketi bu reponun içine vendor'lanmaz; kullanıcı
onu kendi makinesinde kurup HTTP sunucusu olarak çalıştırır, buradaki istemci
sadece o sunucuya HTTP istekleriyle konuşur.
"""

from bridge.client import (
    DEFAULT_BASE_URL,
    DEFAULT_TIMEOUT,
    BridgeError,
    NotebookLMBridge,
    NotAuthenticatedError,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "BridgeError",
    "NotebookLMBridge",
    "NotAuthenticatedError",
]
