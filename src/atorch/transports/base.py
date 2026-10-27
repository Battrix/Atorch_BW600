"""Interfata comuna pentru toate transporturile (USB, Wi-Fi, Bluetooth)."""
from __future__ import annotations

import abc
from dataclasses import dataclass

from atorch.protocol import Reply


class TransportError(Exception):
    pass


class TransportTimeout(TransportError):
    pass


@dataclass(frozen=True)
class DeviceInfo:
    transport: str            # "usb" | "wifi" | "ble"
    path: str                 # identificator specific transportului
    product: str = ""
    serial: str = ""
    extra: str = ""

    def __str__(self) -> str:
        bits = [self.transport, self.product or "?", self.serial or "fara serie"]
        return " | ".join(bits) + (f" | {self.extra}" if self.extra else "")


class Transport(abc.ABC):
    """Un transport trimite un cadru de 64 B si intoarce raspunsul parsat."""

    name = "?"

    @abc.abstractmethod
    def open(self) -> None: ...

    @abc.abstractmethod
    def close(self) -> None: ...

    @abc.abstractmethod
    def send(self, frame: bytes) -> None:
        """Trimite un cadru de 64 B (fara report ID)."""

    @abc.abstractmethod
    def receive(self, timeout: float = 0.8) -> Reply:
        """Asteapta un raspuns. Ridica TransportTimeout daca nu vine."""

    def exchange(self, frame: bytes, timeout: float = 0.8, want_type: int | None = None) -> Reply:
        """Trimite si asteapta un raspuns; ignora raspunsurile de alt tip (daca want_type)."""
        self.send(frame)
        import time
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise TransportTimeout("fara raspuns")
            r = self.receive(left)
            if want_type is None or r.type == want_type:
                return r

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()
