"""
gt7_telemetry.py
Handles all GT7 UDP telemetry: heartbeat, receiving packets,
Salsa20 decryption, and extracting brake and throttle data.
"""

import socket
import struct
import threading
import time
import logging

log = logging.getLogger(__name__)

# ── Salsa20 ───────────────────────────────────────────────────────────────────

_KEY       = b"Simulator Interface Packet GT7 ver 0.0"[:32]
_GT7_MAGIC = 0x47375330
_IV_OFFSET = 0x40
_IV_XOR    = 0xDEADBEAF


def _rotate_left(v: int, n: int) -> int:
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF


def _quarter_round(state: list, a: int, b: int, c: int, d: int):
    state[b] ^= _rotate_left((state[a] + state[d]) & 0xFFFFFFFF,  7)
    state[c] ^= _rotate_left((state[b] + state[a]) & 0xFFFFFFFF,  9)
    state[d] ^= _rotate_left((state[c] + state[b]) & 0xFFFFFFFF, 13)
    state[a] ^= _rotate_left((state[d] + state[c]) & 0xFFFFFFFF, 18)


def _salsa20_block(state: list) -> list:
    x = state[:]
    for _ in range(10):
        _quarter_round(x,  0,  4,  8, 12)
        _quarter_round(x,  5,  9, 13,  1)
        _quarter_round(x, 10, 14,  2,  6)
        _quarter_round(x, 15,  3,  7, 11)
        _quarter_round(x,  0,  1,  2,  3)
        _quarter_round(x,  5,  6,  7,  4)
        _quarter_round(x, 10, 11,  8,  9)
        _quarter_round(x, 15, 12, 13, 14)
    return [(x[i] + state[i]) & 0xFFFFFFFF for i in range(16)]


def _salsa20_setup(key: bytes, nonce: bytes) -> list:
    k = struct.unpack_from("<8I", key)
    n = struct.unpack_from("<2I", nonce)
    state = [0] * 16
    state[0]  = 0x61707865
    state[5]  = 0x3320646e
    state[10] = 0x79622d32
    state[15] = 0x6b206574
    state[1],  state[2],  state[3],  state[4]  = k[0], k[1], k[2], k[3]
    state[11], state[12], state[13], state[14] = k[4], k[5], k[6], k[7]
    state[6], state[7] = n[0], n[1]
    state[8], state[9] = 0, 0
    return state


def _salsa20_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    state = _salsa20_setup(key, nonce)
    plaintext = bytearray(len(ciphertext))
    offset = 0
    while offset < len(ciphertext):
        keystream_words = _salsa20_block(state)
        keystream = struct.pack("<16I", *keystream_words)
        chunk = min(64, len(ciphertext) - offset)
        for i in range(chunk):
            plaintext[offset + i] = ciphertext[offset + i] ^ keystream[i]
        offset += chunk
        state[8] = (state[8] + 1) & 0xFFFFFFFF
        if state[8] == 0:
            state[9] = (state[9] + 1) & 0xFFFFFFFF
    return bytes(plaintext)

# ── GT7 packet handling ───────────────────────────────────────────────────────

def decrypt_gt7_packet(data: bytes):
    """Decrypt a raw GT7 UDP packet. Returns bytes or None if too short."""
    if len(data) < _IV_OFFSET + 4:
        return None
    iv1 = struct.unpack_from("<I", data, _IV_OFFSET)[0]
    iv2 = (iv1 ^ _IV_XOR) & 0xFFFFFFFF
    nonce = struct.pack("<II", iv2, iv1)
    return _salsa20_decrypt(data, _KEY, nonce)


def parse_brake(decrypted: bytes):
    """Extract brake percentage (0.0-100.0) from decrypted packet, or None."""
    if len(decrypted) < 147:
        return None
    return min((decrypted[146] / 255.0) * 100.0, 100.0)


def parse_throttle(decrypted: bytes):
    """Extract throttle percentage (0.0-100.0) from decrypted packet, or None."""
    if len(decrypted) < 146:
        return None
    return min((decrypted[145] / 255.0) * 100.0, 100.0)


def is_valid_packet(decrypted: bytes) -> bool:
    """Return True if the decrypted packet has the correct GT7 magic number."""
    if len(decrypted) < 4:
        return False
    return struct.unpack_from("<I", decrypted, 0)[0] == _GT7_MAGIC


def start_heartbeat(ps5_ip: str, send_port: int, interval_ms: int):
    """Start the GT7 heartbeat in a background daemon thread."""
    def _heartbeat():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        payload = b'\x41' * 64
        while True:
            try:
                sock.sendto(payload, (ps5_ip, send_port))
            except Exception as e:
                log.error(f"Heartbeat error: {e}")
            time.sleep(interval_ms / 1000.0)
    threading.Thread(target=_heartbeat, daemon=True).start()
