import socket
import struct
import threading
import time
import json
import pathlib

config_path = pathlib.Path(__file__).parent / "config.json"
with open(config_path) as file:
    cfg = json.load(file)

# ── Configuration ─────────────────────────────────────────────────────────────
PS5_IP            = cfg["ps5_ip"]   # <-- your PS5's local IP
RECEIVE_PORT      = cfg["receive_port"]              # GT7 sends telemetry to this port
SEND_PORT         = cfg["send_port"]              # we send heartbeat to this port
HEARTBEAT_MS      = cfg["heartbeat_ms"]                # milliseconds between heartbeats
LED_COUNT         = cfg["led_count"]

# Salsa20 key (first 32 bytes of the GT7 key string)
KEY = b"Simulator Interface Packet GT7 ver 0.0"[:32]

# ── Salsa20 ───────────────────────────────────────────────────────────────────

def _rotate_left(v: int, n: int) -> int:
    return ((v << n) | (v >> (32 - n))) & 0xFFFFFFFF

def _quarter_round(state: list, a: int, b: int, c: int, d: int):
    state[b] ^= _rotate_left((state[a] + state[d]) & 0xFFFFFFFF,  7)
    state[c] ^= _rotate_left((state[b] + state[a]) & 0xFFFFFFFF,  9)
    state[d] ^= _rotate_left((state[c] + state[b]) & 0xFFFFFFFF, 13)
    state[a] ^= _rotate_left((state[d] + state[c]) & 0xFFFFFFFF, 18)

def _salsa20_block(state: list) -> list:
    """One Salsa20 block (20 rounds = 10 double-rounds)."""
    x = state[:]
    for _ in range(10):
        # column rounds
        _quarter_round(x,  0,  4,  8, 12)
        _quarter_round(x,  5,  9, 13,  1)
        _quarter_round(x, 10, 14,  2,  6)
        _quarter_round(x, 15,  3,  7, 11)
        # row rounds
        _quarter_round(x,  0,  1,  2,  3)
        _quarter_round(x,  5,  6,  7,  4)
        _quarter_round(x, 10, 11,  8,  9)
        _quarter_round(x, 15, 12, 13, 14)
    return [(x[i] + state[i]) & 0xFFFFFFFF for i in range(16)]

def _salsa20_setup(key: bytes, nonce: bytes) -> list:
    """
    Build the initial Salsa20 state correctly for a 256-bit key.

    Layout (16 x uint32):
      0: const0   1-4: key[0:16]   5: const1
      6-7: nonce  8-9: counter     10: const2
      11-14: key[16:32]            15: const3
    """
    k = struct.unpack_from("<8I", key)   # 8 x uint32 from 32-byte key
    n = struct.unpack_from("<2I", nonce) # 2 x uint32 from 8-byte nonce

    state = [0] * 16
    # Salsa20 "expand 32-byte k" constants
    state[0]  = 0x61707865   # "expa"
    state[5]  = 0x3320646e   # "nd 3"
    state[10] = 0x79622d32   # "2-by"
    state[15] = 0x6b206574   # "te k"
    # First half of key → positions 1–4
    state[1], state[2], state[3], state[4] = k[0], k[1], k[2], k[3]
    # Second half of key → positions 11–14
    state[11], state[12], state[13], state[14] = k[4], k[5], k[6], k[7]
    # Nonce
    state[6], state[7] = n[0], n[1]
    # Counter starts at 0
    state[8], state[9] = 0, 0
    return state

def salsa20_decrypt(ciphertext: bytes, key: bytes, nonce: bytes) -> bytes:
    """Decrypt ciphertext using Salsa20 with the given key and nonce."""
    state = _salsa20_setup(key, nonce)
    plaintext = bytearray(len(ciphertext))
    offset = 0
    while offset < len(ciphertext):
        keystream_words = _salsa20_block(state)
        # Convert 16 x uint32 → 64 bytes
        keystream = struct.pack("<16I", *keystream_words)
        chunk = min(64, len(ciphertext) - offset)
        for i in range(chunk):
            plaintext[offset + i] = ciphertext[offset + i] ^ keystream[i]
        offset += chunk
        # Increment 64-bit counter (low word first)
        state[8] = (state[8] + 1) & 0xFFFFFFFF
        if state[8] == 0:
            state[9] = (state[9] + 1) & 0xFFFFFFFF
    return bytes(plaintext)

# ── GT7 packet handling ───────────────────────────────────────────────────────

GT7_MAGIC    = 0x47375330
IV_OFFSET    = 0x40        # offset of IV1 in the raw encrypted packet
IV_XOR       = 0xDEADBEAF  # XOR constant to derive IV2

def decrypt_gt7_packet(data: bytes):
    """
    Decrypt a raw GT7 UDP packet.
    Returns the decrypted bytes, or None if the packet is too short.
    """
    if len(data) < IV_OFFSET + 4:
        return None

    iv1 = struct.unpack_from("<I", data, IV_OFFSET)[0]
    iv2 = (iv1 ^ IV_XOR) & 0xFFFFFFFF

    # 8-byte nonce: iv2 (4 bytes LE) + iv1 (4 bytes LE)
    nonce = struct.pack("<II", iv2, iv1)

    return salsa20_decrypt(data, KEY, nonce)

def parse_brake(decrypted: bytes):
    """
    Extract brake percentage from a decrypted GT7 packet.
    Brake is a single byte at offset 146; range 0-255 → 0-100 %.
    Returns float 0.0–100.0, or None if packet is too short.
    """
    if len(decrypted) < 147:
        return None
    brake_raw = decrypted[146]
    return (brake_raw / 255.0) * 100.0

# ── Heartbeat thread ──────────────────────────────────────────────────────────

def heartbeat_thread(ps5_ip: str, send_port: int, interval_ms: int):
    """Continuously send the GT7 heartbeat ('A' x 64) to the PS5."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = b'\x41' * 64   # 64 × 'A'
    while True:
        try:
            sock.sendto(payload, (ps5_ip, send_port))
            # print(f"Heartbeat → {ps5_ip}:{send_port}")
        except Exception as e:
            print(f"Heartbeat error: {e}")
        time.sleep(interval_ms / 1000.0)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Start heartbeat in background
    hb = threading.Thread(
        target=heartbeat_thread,
        args=(PS5_IP, SEND_PORT, HEARTBEAT_MS),
        daemon=True
    )
    hb.start()

    # Listen for telemetry
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", RECEIVE_PORT))
    sock.settimeout(5.0)

    print(f"Listening for GT7 telemetry on port {RECEIVE_PORT}")
    print("Press Ctrl+F5 to stop...\n")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(4096)
               # print(f"Packet from {addr}, {len(data)} bytes")

                decrypted = decrypt_gt7_packet(data)
                if decrypted is None:
                    print("  Packet too short, skipping.")
                    continue

                # Validate magic number
                magic = struct.unpack_from("<I", decrypted, 0)[0]
                if magic != GT7_MAGIC:
                    print(f"  Bad magic: 0x{magic:08X} (expected 0x{GT7_MAGIC:08X}), skipping.")
                    continue

                brake_pct = parse_brake(decrypted)
                if brake_pct is None:
                    print("  Decrypted packet too short for brake value.")
                    continue

                print(f"  ✓ Brake: {brake_pct:.0f}%")

            except socket.timeout:
                print("No packet in 5 s, waiting...")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        sock.close()

if __name__ == "__main__":
    main()
