"""
brake_led_controller.py
Manages brake LED color zone logic and output — either to real WS2812B
hardware via NeoPixel on the Pi, or a console simulation on Windows.

Zone keys in config.json (zone1..zone4) are position-based, not color-based,
so changing any zone's color is purely a config edit with no code changes.
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
        (25,  tuple(colors["zone1"])),
        (50,  tuple(colors["zone2"])),
        (75,  tuple(colors["zone3"])),
        (100, tuple(colors["zone4"])),
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
    Attempt to initialize the NeoPixel hardware for the brake strip.
    Uses GPIO 18 (physical pin 12) for data.
    Returns a pixels object on success, None otherwise.
    """
    if not _is_raspberry_pi():
        log.info("Brake: Not a Raspberry Pi — running in simulation mode.")
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
        log.info("Brake: NeoPixel hardware detected — running in LED mode.")
        return pixels
    except Exception as e:
        log.warning(f"Brake: LED hardware not available ({e}) — running in simulation mode.")
        return None

# ── Brake LED controller class ────────────────────────────────────────────────

class BrakeLEDController:
    """
    Controls the brake LED strip.
    Four color zones, colors fully defined by config.json — this class has
    no knowledge of what color any zone actually is.
    On the Pi, drives the physical WS2812B strip.
    On Windows, renders a color bar in the terminal.
    """

    _ANSI_OFF   = "\033[90m"
    _ANSI_RESET = "\033[0m"
    _ANSI_BOLD  = "\033[1m"

    def __init__(self, led_count: int, brightness: int, colors: dict):
        self.led_count   = led_count
        self.brightness  = brightness
        self.color_zones = build_color_zones(colors)
        self._pixels     = _try_init_hardware(led_count, brightness)
        self.simulation  = self._pixels is None

    def update(self, brake_pct: float):
        """Update the brake LED strip for the given brake percentage."""
        states = compute_led_states(brake_pct, self.led_count, self.color_zones)
        if self.simulation:
            self._render_simulation(brake_pct, states)
        else:
            self._render_hardware(states)

    def clear(self):
        """Turn all brake LEDs off."""
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
                bar += f"{self._ANSI_OFF}░"
            else:
                bar += f"{self._rgb_to_ansi(color)}█"
        bar += self._ANSI_RESET
        lit = int(brake_pct)
        pct = f"{self._ANSI_BOLD}{brake_pct:5.1f}%{self._ANSI_RESET}"
        print(f"\rBrake:    {pct} [{bar}] {lit:3d}/{self.led_count}", end="", flush=True)

    def _rgb_to_ansi(self, color: tuple) -> str:
        """
        Approximate any arbitrary RGB color as the nearest terminal ANSI color.
        Not tied to any specific zone's color choice — works for whatever
        colors happen to be configured.
        """
        r, g, b = color
        # Standard 8-color ANSI palette approximation via nearest-neighbor
        palette = {
            "\033[91m": (255, 0, 0),      # red
            "\033[92m": (0, 255, 0),      # green
            "\033[93m": (255, 255, 0),    # yellow
            "\033[94m": (0, 0, 255),      # blue
            "\033[95m": (255, 0, 255),    # magenta
            "\033[96m": (0, 255, 255),    # cyan
            "\033[38;5;208m": (255, 128, 0),  # orange
        }
        best_code = min(
            palette,
            key=lambda code: sum((a - b) ** 2 for a, b in zip(palette[code], color))
        )
        return best_code
