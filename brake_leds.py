"""
brake_leds.py
Entry point. Loads config, starts the GT7 telemetry listener,
and feeds brake data to the LED controller.
"""

import socket
import struct
import json
import pathlib

from gt7_telemetry import start_heartbeat, decrypt_gt7_packet, is_valid_packet, parse_brake
from led_controller import LEDController

# ── Load config ───────────────────────────────────────────────────────────────

config_path = pathlib.Path(__file__).parent / "config.json"
with open(config_path) as f:
    cfg = json.load(f)

PS5_IP       = cfg["ps5_ip"]
RECEIVE_PORT = cfg["receive_port"]
SEND_PORT    = cfg["send_port"]
HEARTBEAT_MS = cfg["heartbeat_ms"]
LED_COUNT    = cfg["led_count"]
BRIGHTNESS   = cfg["brightness"]
COLORS       = cfg["colors"]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    leds = LEDController(LED_COUNT, BRIGHTNESS, COLORS)

    start_heartbeat(PS5_IP, SEND_PORT, HEARTBEAT_MS)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", RECEIVE_PORT))
    sock.settimeout(5.0)

    print(f"Listening for GT7 telemetry on port {RECEIVE_PORT}")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)

                decrypted = decrypt_gt7_packet(data)
                if decrypted is None or not is_valid_packet(decrypted):
                    continue

                brake_pct = parse_brake(decrypted)
                if brake_pct is None:
                    continue

                leds.update(brake_pct)

            except socket.timeout:
                pass  # keep waiting silently

    except KeyboardInterrupt:
        print("\n\nStopped.")
        leds.clear()
    finally:
        sock.close()


if __name__ == "__main__":
    main()
