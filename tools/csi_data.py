"""Parsing and conversion helpers for ESP32 CSI serial output."""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, hypot
import re


CSI_LINE_PATTERN = re.compile(
    r"CSI:\s+RSSI=(?P<rssi>-?\d+)\s+"
    r"len=(?P<length>\d+)\s+"
    r"first_word_invalid=(?P<invalid>[01])\s+"
    r"data=\[(?P<data>[^]]*)]"
)


@dataclass(frozen=True, slots=True)
class CsiFrame:
    """One CSI frame printed by the ESP32 firmware."""

    rssi: int
    reported_length: int
    first_word_invalid: bool
    values: tuple[int, ...]

    def usable_values(self) -> tuple[int, ...]:
        """Return values after removing the invalid first word when present."""

        if self.first_word_invalid:
            return self.values[4:]
        return self.values

    def amplitudes(self) -> tuple[float, ...]:
        """Convert imaginary/real byte pairs to subcarrier amplitudes."""

        values = self.usable_values()
        return tuple(
            hypot(values[index + 1], values[index])
            for index in range(0, len(values) - 1, 2)
        )

    def mean_amplitude(self) -> float:
        """Return the mean amplitude of all printed, usable subcarriers."""

        amplitudes = self.amplitudes()
        if not amplitudes:
            return 0.0
        return fsum(amplitudes) / len(amplitudes)


def parse_csi_line(line: str) -> CsiFrame | None:
    """Parse a firmware output line, returning None for unrelated or bad data."""

    match = CSI_LINE_PATTERN.search(line)
    if match is None:
        return None

    raw_values = match.group("data").strip()
    if not raw_values:
        return None

    try:
        values = tuple(int(value.strip()) for value in raw_values.split(","))
    except ValueError:
        return None

    if any(value < -128 or value > 127 for value in values):
        return None

    frame = CsiFrame(
        rssi=int(match.group("rssi")),
        reported_length=int(match.group("length")),
        first_word_invalid=match.group("invalid") == "1",
        values=values,
    )
    if not frame.amplitudes():
        return None
    return frame


def amplitude_change(previous: tuple[float, ...], current: tuple[float, ...]) -> float:
    """Return the mean absolute subcarrier change between two frames."""

    pair_count = min(len(previous), len(current))
    if pair_count == 0:
        return 0.0
    return fsum(
        abs(current[index] - previous[index]) for index in range(pair_count)
    ) / pair_count
