#!/usr/bin/env python3
"""Plot ESP32-S3 CSI data received over a serial port."""

from __future__ import annotations

import argparse
from collections import deque
import queue
import threading
import time

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import serial
from serial.tools import list_ports

from tools.csi_data import CsiFrame, amplitude_change, parse_csi_line


DEFAULT_BAUD_RATE = 115200
DEFAULT_HISTORY_SIZE = 300


def serial_ports() -> list[str]:
    """Return likely USB serial devices, with macOS callout devices first."""

    devices = [port.device for port in list_ports.comports()]
    likely = [
        device
        for device in devices
        if "usbmodem" in device.lower() or "usbserial" in device.lower()
    ]
    return sorted(likely or devices)


def select_port(requested_port: str | None) -> str:
    """Use the requested port, or select the only likely USB serial port."""

    if requested_port:
        return requested_port

    ports = serial_ports()
    if not ports:
        raise SystemExit(
            "USB serial port was not found. Connect the ESP32-S3 and try again."
        )
    if len(ports) > 1:
        choices = "\n  ".join(ports)
        raise SystemExit(
            "Multiple serial ports were found. Pass one as an argument:\n  " + choices
        )
    return ports[0]


def enqueue_latest(target: queue.Queue[CsiFrame], frame: CsiFrame) -> None:
    """Keep receiving even if the plot briefly falls behind."""

    try:
        target.put_nowait(frame)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        target.put_nowait(frame)


def read_serial(
    port: str,
    baud_rate: int,
    frames: queue.Queue[CsiFrame],
    errors: queue.Queue[str],
    stop_event: threading.Event,
) -> None:
    """Read and parse CSI lines until the plot window closes."""

    try:
        with serial.Serial(port, baud_rate, timeout=1) as connection:
            while not stop_event.is_set():
                line = connection.readline().decode("utf-8", errors="replace")
                frame = parse_csi_line(line)
                if frame is not None:
                    enqueue_latest(frames, frame)
    except serial.SerialException as error:
        errors.put(str(error))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Plot ESP32-S3 Wi-Fi CSI values in real time."
    )
    parser.add_argument(
        "port",
        nargs="?",
        help="serial port; automatically selected when exactly one USB port exists",
    )
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    parser.add_argument("--history", type=int, default=DEFAULT_HISTORY_SIZE)
    parser.add_argument(
        "--list-ports", action="store_true", help="list serial ports and exit"
    )
    return parser


def main() -> None:
    args = create_parser().parse_args()
    if args.history < 10:
        raise SystemExit("--history must be at least 10")

    if args.list_ports:
        ports = serial_ports()
        print("\n".join(ports) if ports else "No serial ports found.")
        return

    port = select_port(args.port)
    frame_queue: queue.Queue[CsiFrame] = queue.Queue(maxsize=1000)
    error_queue: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()
    reader = threading.Thread(
        target=read_serial,
        args=(port, args.baud, frame_queue, error_queue, stop_event),
        daemon=True,
    )
    reader.start()

    start_time = time.monotonic()
    sample_times: deque[float] = deque(maxlen=args.history)
    mean_amplitudes: deque[float] = deque(maxlen=args.history)
    motion_scores: deque[float] = deque(maxlen=args.history)
    previous_amplitudes: tuple[float, ...] = ()

    figure, (history_axis, carrier_axis) = plt.subplots(2, 1, figsize=(11, 7))
    figure.canvas.manager.set_window_title("ESP32-S3 Wi-Fi CSI")
    figure.suptitle(f"Waiting for CSI data from {port}")

    mean_line, = history_axis.plot([], [], label="Mean amplitude", linewidth=1.5)
    motion_line, = history_axis.plot([], [], label="Frame change", linewidth=1.2)
    history_axis.set_ylabel("Amplitude")
    history_axis.set_xlabel("Time (seconds)")
    history_axis.grid(alpha=0.3)
    history_axis.legend(loc="upper left")

    carrier_line, = carrier_axis.plot([], [], marker="o", markersize=3)
    carrier_axis.set_xlabel("Printed subcarrier index")
    carrier_axis.set_ylabel("Amplitude")
    carrier_axis.grid(alpha=0.3)

    def update_plot(_frame_number: int):
        nonlocal previous_amplitudes

        if not error_queue.empty():
            error = error_queue.get_nowait()
            figure.suptitle(f"Serial error: {error}")
            stop_event.set()
            return mean_line, motion_line, carrier_line

        latest: CsiFrame | None = None
        while True:
            try:
                latest = frame_queue.get_nowait()
            except queue.Empty:
                break

            amplitudes = latest.amplitudes()
            sample_times.append(time.monotonic() - start_time)
            mean_amplitudes.append(latest.mean_amplitude())
            motion_scores.append(amplitude_change(previous_amplitudes, amplitudes))
            previous_amplitudes = amplitudes

        if latest is None:
            return mean_line, motion_line, carrier_line

        mean_line.set_data(sample_times, mean_amplitudes)
        motion_line.set_data(sample_times, motion_scores)
        history_axis.relim()
        history_axis.autoscale_view()

        amplitudes = latest.amplitudes()
        carrier_line.set_data(range(len(amplitudes)), amplitudes)
        carrier_axis.relim()
        carrier_axis.autoscale_view()

        figure.suptitle(
            f"{port}  RSSI={latest.rssi} dBm  "
            f"CSI length={latest.reported_length}  "
            f"visible subcarriers={len(amplitudes)}"
        )
        return mean_line, motion_line, carrier_line

    animation = FuncAnimation(
        figure, update_plot, interval=50, blit=False, cache_frame_data=False
    )
    try:
        plt.tight_layout()
        plt.show()
    finally:
        stop_event.set()
        reader.join(timeout=2)
        del animation


if __name__ == "__main__":
    main()
