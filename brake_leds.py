"""
brake_leds.py
Entry point. Loads config, starts the GT7 telemetry listener,
and feeds brake and throttle data to their respective LED controllers.
"""

import socket
import json
import pathlib
import logging

from logger import setup_logging
from gt7_telemetry import start_heartbeat, decrypt_gt7_packet, is_valid_packet, parse_brake, parse_throttle
from led_controller import LEDController
from throttle_leds import ThrottleLEDController

# ── Load config ───────────────────────────────────────────────────────────────

config_path = pathlib.Path(__file__).parent / "config.json"
with open(config_path) as f:
    cfg = json.load(f)

PS5_IP              = cfg["ps5_ip"]
RECEIVE_PORT        = cfg["receive_port"]
SEND_PORT           = cfg["send_port"]
HEARTBEAT_MS        = cfg["heartbeat_ms"]
LED_COUNT           = cfg["led_count"]
BRIGHTNESS          = cfg["brightness"]
COLORS              = cfg["colors"]
THROTTLE_LED_COUNT  = cfg["throttle_led_count"]
THROTTLE_COLOR      = tuple(cfg["throttle_color"])
THROTTLE_GPIO_PIN   = cfg["throttle_gpio_pin"]

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log = setup_logging()
    log.info("ClaudeBrakeLEDs starting up")
    log.info(f"PS5 IP: {PS5_IP}, receive port: {RECEIVE_PORT}, send port: {SEND_PORT}")

    brake_leds    = LEDController(LED_COUNT, BRIGHTNESS, COLORS)
    throttle_leds = ThrottleLEDController(THROTTLE_LED_COUNT, THROTTLE_COLOR, THROTTLE_GPIO_PIN)

    start_heartbeat(PS5_IP, SEND_PORT, HEARTBEAT_MS)
    log.info("Heartbeat started")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", RECEIVE_PORT))
    sock.settimeout(5.0)

    log.info(f"Listening for GT7 telemetry on port {RECEIVE_PORT}")

    try:
        while True:
            try:
                data, _ = sock.recvfrom(4096)

                decrypted = decrypt_gt7_packet(data)
                if decrypted is None or not is_valid_packet(decrypted):
                    continue

                brake_pct    = parse_brake(decrypted)
                throttle_pct = parse_throttle(decrypted)

                if brake_pct is not None:
                    brake_leds.update(brake_pct)

                if throttle_pct is not None:
                    throttle_leds.update(throttle_pct)

            except socket.timeout:
                pass  # keep waiting silently

    except KeyboardInterrupt:
        log.info("Stopped by user.")
        brake_leds.clear()
        throttle_leds.clear()
    except Exception as e:
        log.error(f"Fatal error: {e}", exc_info=True)
    finally:
        sock.close()
        log.info("Socket closed. Exiting.")


if __name__ == "__main__":
    main()
