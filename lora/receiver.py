"""
LoRa / LoRaWAN receiver stub.

This script listens for packets from sensor nodes and forwards the data
to the local Beetter Flask API.

Hardware integration
--------------------
Replace the STUB section below with your actual LoRa library calls.

Common choices:
  - adafruit-circuitpython-rfm9x  (SX127x via CircuitPython / Blinka)
  - pyLoRa / SX127x               (raw SX127x via RPi GPIO + SPI)
  - pyserial + RAK811 / Dragino   (AT-command LoRaWAN module over UART)
  - pySX127x                      (low-level SX127x driver)

Expected packet format (JSON, up to 255 bytes). Keys are short to save airtime:
  {
    "id": <beehive_id>,
    "t_int": <float>, "h_int": <float>,        # interior temp/humidity sensor
    "t_ext": <float>, "h_ext": <float>,        # exterior temp/humidity sensor
    "sf_int": <float>, "sa_int": <float>,      # interior mic: peak frequency (Hz) + amplitude
    "sf_ext": <float>, "sa_ext": <float>,      # exterior mic: peak frequency (Hz) + amplitude
    "l_ext": <float>                           # exterior photoresistor: light level
  }
  All sensor fields are optional; only the ones present are forwarded.

Usage:
  python receiver.py
  BEETTER_URL=http://localhost:5000 python receiver.py
"""

import json
import logging
import os
import time

import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

BEETTER_URL = os.environ.get('BEETTER_URL', 'http://localhost:5000')
API_ENDPOINT = f'{BEETTER_URL}/api/data'

# ─── LoRa configuration ────────────────────────────────────────────────────────
LORA_FREQUENCY = float(os.environ.get('LORA_FREQUENCY', '868.0'))    # MHz
LORA_SF        = int(os.environ.get('LORA_SF', '7'))                  # Spreading factor 7–12
LORA_BW        = int(os.environ.get('LORA_BW', '125000'))             # Bandwidth in Hz


def init_lora():
    """
    Initialise the LoRa radio.

    STUB — replace with your hardware initialisation.
    Example with adafruit-circuitpython-rfm9x:

        import board, busio, digitalio
        import adafruit_rfm9x

        spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        cs  = digitalio.DigitalInOut(board.CE1)
        rst = digitalio.DigitalInOut(board.D25)
        rfm9x = adafruit_rfm9x.RFM9x(spi, cs, rst, LORA_FREQUENCY)
        rfm9x.signal_bandwidth = LORA_BW
        rfm9x.spreading_factor = LORA_SF
        return rfm9x
    """
    log.warning('LoRa hardware not configured — running in STUB mode')
    return None


def receive_packet(radio):
    """
    Block until a packet arrives and return its raw bytes.

    STUB — replace with actual receive call.
    Example:

        packet = radio.receive(timeout=30.0)
        return packet
    """
    # Simulated packet for development:
    time.sleep(10)
    sample = json.dumps({
        "id": 1,
        "t_int": 34.7, "h_int": 64.7,
        "t_ext": 18.3, "h_ext": 55.0,
        "sf_int": 245.0, "sa_int": 0.42,
        "sf_ext": 120.0, "sa_ext": 0.11,
        "l_ext": 760.0,
    }).encode()
    log.debug('STUB: returning simulated packet')
    return sample


def parse_packet(raw: bytes) -> dict | None:
    """Decode a raw LoRa payload into a dict understood by the Flask API."""
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        log.warning('Could not decode packet: %s', e)
        return None

    beehive_id = data.get('id')
    if beehive_id is None:
        log.warning('Packet missing "id" field: %s', data)
        return None

    return {
        'beehive_id': int(beehive_id),
        'temperature_int': data.get('t_int'),
        'humidity_int':    data.get('h_int'),
        'temperature_ext': data.get('t_ext'),
        'humidity_ext':    data.get('h_ext'),
        # Interior microphone: peak frequency (Hz) + amplitude of that peak
        'sound_freq_int':  data.get('sf_int'),
        'sound_amp_int':   data.get('sa_int'),
        # Exterior microphone: peak frequency (Hz) + amplitude of that peak
        'sound_freq_ext':  data.get('sf_ext'),
        'sound_amp_ext':   data.get('sa_ext'),
        # Exterior photoresistor: light level
        'light_ext':       data.get('l_ext'),
    }


def push_to_api(payload: dict) -> bool:
    """POST sensor data to the local Beetter Flask API."""
    try:
        resp = requests.post(API_ENDPOINT, json=payload, timeout=10)
        if resp.ok:
            measured = [k for k, v in payload.items()
                        if k != 'beehive_id' and v is not None]
            log.info('Data pushed: beehive=%s fields=%s',
                     payload.get('beehive_id'), ','.join(measured))
            return True
        log.error('API returned %s: %s', resp.status_code, resp.text)
        return False
    except requests.RequestException as e:
        log.error('Could not reach Beetter API: %s', e)
        return False


def main():
    log.info('Starting LoRa receiver (freq=%.1f MHz, SF=%d, BW=%d Hz)',
             LORA_FREQUENCY, LORA_SF, LORA_BW)
    radio = init_lora()

    while True:
        try:
            raw = receive_packet(radio)
            if raw is None:
                continue
            payload = parse_packet(raw)
            if payload:
                push_to_api(payload)
        except KeyboardInterrupt:
            log.info('Receiver stopped.')
            break
        except Exception as e:
            log.exception('Unexpected error: %s', e)
            time.sleep(5)


if __name__ == '__main__':
    main()
