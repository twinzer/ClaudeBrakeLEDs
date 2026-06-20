"""
led_controller.py
Manages LED color zone logic and output — either to real WS2812B
hardware via NeoPixel on the Pi, or a console simulation on Windows.
"""

import logging

log = logging.getLogger(__name__)

# ── Color zone logic ──────────────────────────────────────────────────────────

def build_color_zones(colors: dict) -> list:
    """
    Convert the color config dict into an ordered list of (threshold, rgb) tuples.
    LEDs 1-25 → zone1, 26-50 → zone2, 51-75 → zone3, 76-100 → zone4.
    """
    return [
        (25,  tuple(colors["zone1_green"])),
        (50,  tuple(colors["zone2_yellow"])),
        (75,  tuple(colors["zone3_orange"])),
        (100, tuple(colors["zone4_red"])),
    ]


def get_led_color(led_index_1based: int, color_zones: list) -> tuple:
    """Return the RGB color for a given LED position (1-based)."""
    for threshold, color in color_zones:
        if led_index_1based <= threshold:
            return color
    return color_zones[-1][1]


def compute_led_states(brake_pct: float, led_count: int, color_zones: list) -> list:
    """
    Return a list of led_count RGB tuples.
    LEDs 1..floor(brake_pct) are lit in their zone color.
    LEDs above brake_pct are off (0, 0, 0).
    """
    lit_count = int(brake_pct)
    return [
        get_led_color(i, color_zones) if i <= lit_count else (0, 0, 0)
        for i in range(1, led_count + 1)
    ]

# ── Hardware vs simulation detection ─────────────────────────────────────────

def _is_raspberry_pi() -> bool:
    """Return True if we are running on a Raspberry Pi."""
    try:
        with open("/proc/device-tree/model", "r") as f:
            model = f.read()
            return "Raspberry Pi" in model
    except Exception:
        return False


def _try_init_hardware(led_count: int, brightness: int):
    """
    Attempt to initialize the NeoPixel hardware.
    Only tries on a real Raspberry Pi with LED strip physically connected.
    Returns a pixels object on success, None otherwise.
    """
    if not _is_raspberry_pi():
        log.info("Not a Raspberry Pi — running in simulation mode.")
        return None

    try:
        import board
        import neopixel
        pixels = neopixel.NeoPixel(
            board.D18,
            led_count,
            brightness=brightness / 255.0,
            auto_write=False,
            pixel_order=neopixel.GRB
        )
        log.info("NeoPixel hardware detected — running in LED mode.")
        return pixels
    except Exception as e:
        log.warning(f"LED hardware not available ({e}) — running in simulation mode.")
        return None

# ── LED controller class ──────────────────────────────────────────────────────

class LEDController:
    """
    Abstracts LED output. On the Pi, drives the physical WS2812B strip.
    On Windows, renders a color bar in the terminal.
    """

    # ANSI color codes for terminal simulation
    _ANSI = {
        "green":  "\033[92m",
        "yellow": "\033[93m",
        "orange": "\033[38;5;208m",
        "red":    "\033[91m",
        "off":    "\033[90m",
        "reset":  "\033[0m",
        "bold":   "\033[1m",
    }

    def __init__(self, led_count: int, brightness: int, colors: dict):
        self.led_count   = led_count
        self.brightness  = brightness
        self.color_zones = build_color_zones(colors)
        self._pixels     = _try_init_hardware(led_count, brightness)
        self.simulation  = self._pixels is None

    def update(self, brake_pct: float):
        """Update the LED strip (or simulation) for the given brake percentage."""
        states = compute_led_states(brake_pct, self.led_count, self.color_zones)
        if self.simulation:
            self._render_simulation(brake_pct, states)
        else:
            self._render_hardware(states)

    def clear(self):
        """Turn all LEDs off."""
        if not self.simulation:
            self._pixels.fill((0, 0, 0))
            self._pixels.show()

    def _render_hardware(self, states: list):
        for i, color in enumerate(states):
            self._pixels[i] = color
        self._pixels.show()

    def _render_simulation(self, brake_pct: float, states: list):
        bar = ""
        for color in states:
            if color == (0, 0, 0):
                bar += f"{self._ANSI['off']}░"
            else:
                bar += f"{self._rgb_to_ansi(color)}█"
        bar += self._ANSI["reset"]
        lit = int(brake_pct)
        pct = f"{self._ANSI['bold']}{brake_pct:5.1f}%{self._ANSI['reset']}"
        print(f"\r{pct} [{bar}] {lit:3d}/{self.led_count}", end="", flush=True)

    def _rgb_to_ansi(self, color: tuple) -> str:
        r, g, b = color
        if r == 0 and g > 0:
            return self._ANSI["green"]
        elif r > 0 and g > 0 and b == 0:
            return self._ANSI["yellow"] if g > 80 else self._ANSI["orange"]
        elif r > 0 and g == 0:
            return self._ANSI["red"]
        return self._ANSI["off"]
