"""
throttle_led_controller.py
Manages throttle LED strip output — either to real WS2812B
hardware via NeoPixel on the Pi, or a console simulation on Windows.
Single white zone across all 100 LEDs at reduced brightness.
"""

import logging

log = logging.getLogger(__name__)

# ── Hardware vs simulation detection ─────────────────────────────────────────

def _is_raspberry_pi() -> bool:
    """Return True if we are running on a Raspberry Pi."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            return "Raspberry Pi" in model
    except Exception:
        return False


def _try_init_hardware(led_count: int, gpio_pin: int):
    """
    Attempt to initialize the NeoPixel hardware for the throttle strip.
    Uses GPIO 13 (physical pin 33) for data.
    Returns a pixels object on success, None otherwise.
    """
    if not _is_raspberry_pi():
        log.info("Throttle: Not a Raspberry Pi — running in simulation mode.")
        return None

    try:
        import board
        import neopixel

        pin_map = {
            13: board.D13,
            18: board.D18,
        }
        pin = pin_map.get(gpio_pin)
        if pin is None:
            log.warning(f"Throttle: GPIO pin {gpio_pin} not supported — simulation mode.")
            return None

        pixels = neopixel.NeoPixel(
            pin,
            led_count,
            brightness=1.0,        # brightness controlled via RGB values
            auto_write=False,
            pixel_order=neopixel.GRB
        )
        log.info(f"Throttle: NeoPixel hardware detected on GPIO {gpio_pin} — running in LED mode.")
        return pixels
    except Exception as e:
        log.warning(f"Throttle: LED hardware not available ({e}) — running in simulation mode.")
        return None

# ── Throttle LED controller class ─────────────────────────────────────────────

class ThrottleLEDController:
    """
    Controls the throttle LED strip.
    Single white zone: LEDs 1..floor(throttle_pct) are lit white.
    LEDs above throttle_pct are off.
    On the Pi, drives the physical WS2812B strip.
    On Windows, renders a color bar in the terminal.
    """

    _ANSI = {
        "white": "\033[97m",
        "off":   "\033[90m",
        "reset": "\033[0m",
        "bold":  "\033[1m",
    }

    def __init__(self, led_count: int, color: tuple, gpio_pin: int):
        self.led_count  = led_count
        self.color      = color
        self._pixels    = _try_init_hardware(led_count, gpio_pin)
        self.simulation = self._pixels is None

    def update(self, throttle_pct: float):
        """Update the throttle LED strip for the given throttle percentage."""
        lit_count = int(throttle_pct)
        states = [
            self.color if i <= lit_count else (0, 0, 0)
            for i in range(1, self.led_count + 1)
        ]
        if self.simulation:
            self._render_simulation(throttle_pct, states)
        else:
            self._render_hardware(states)

    def clear(self):
        """Turn all throttle LEDs off."""
        if not self.simulation:
            self._pixels.fill((0, 0, 0))
            self._pixels.show()

    def _render_hardware(self, states: list):
        for i, color in enumerate(states):
            self._pixels[i] = color
        self._pixels.show()

    def _render_simulation(self, throttle_pct: float, states: list):
        bar = ""
        for color in states:
            if color == (0, 0, 0):
                bar += f"{self._ANSI['off']}░"
            else:
                bar += f"{self._ANSI['white']}█"
        bar += self._ANSI["reset"]
        lit = int(throttle_pct)
        pct = f"{self._ANSI['bold']}{throttle_pct:5.1f}%{self._ANSI['reset']}"
        print(f"\nThrottle: {pct} [{bar}] {lit:3d}/{self.led_count}", end="", flush=True)
