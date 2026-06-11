"""
lora/receiver.py
─────────────────────────────────────────────────────────────────────────────
LoRa / LoRaWAN receiver.

Listens for packets from sensor nodes and forwards the data to the Beetter API.

──────────────────────────────────────────────────────────────────────────────
JSON packet format (sent by ESP32, all optional except "id"):

  {
    "id":    <int>,            beehive identifier

    "t_int": <float>,          interior temperature (°C)
    "h_int": <float>,          interior humidity (%)
    "t_ext": <float>,          exterior temperature (°C)
    "h_ext": <float>,          exterior humidity (%)

    "sf_int": <float>,         interior peak frequency (Hz)
    "sa_int": <float>,         interior RMS amplitude (0–1)
    "sf_ext": <float>,         exterior peak frequency (Hz)
    "sa_ext": <float>,         exterior RMS amplitude (0–1)

    "l_ext":  <float>,         exterior light level

    "mc_int": [c1,c2,c3,c4,c5],  MFCC coefficients 1-5, interior  ← NEW
    "mc_ext": [c1,c2,c3,c4,c5],  MFCC coefficients 1-5, exterior  ← NEW
  }

The "mc_int" / "mc_ext" fields are optional — the receiver works without them
and the API/InfluxDB silently skip them if absent.
Once the ESP32 firmware computes MFCC on-device, it adds these arrays.
All other fields remain unchanged.

──────────────────────────────────────────────────────────────────────────────
Hardware integration:
Replace the STUB sections with your actual LoRa library calls.

Common choices:
  - adafruit-circuitpython-rfm9x  (SX127x via CircuitPython / Blinka)
  - pyLoRa / SX127x               (raw SX127x via RPi GPIO + SPI)
  - pyserial + RAK811 / Dragino   (AT-command LoRaWAN module over UART)

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

BEETTER_URL  = os.environ.get('BEETTER_URL', 'http://localhost:5000')
API_ENDPOINT = f'{BEETTER_URL}/api/data'

LORA_FREQUENCY = float(os.environ.get('LORA_FREQUENCY', '868.0'))
LORA_SF        = int(os.environ.get('LORA_SF', '9'))
LORA_BW        = int(os.environ.get('LORA_BW', '125000'))


def init_lora():
    """
    Initialise the LoRa radio.  STUB — replace with hardware init.

    Example with adafruit-circuitpython-rfm9x:
        import board, busio, digitalio, adafruit_rfm9x
        spi  = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
        cs   = digitalio.DigitalInOut(board.CE1)
        rst  = digitalio.DigitalInOut(board.D25)
        rfm9 = adafruit_rfm9x.RFM9x(spi, cs, rst, LORA_FREQUENCY)
        rfm9.signal_bandwidth = LORA_BW
        rfm9.spreading_factor = LORA_SF
        return rfm9
    """
    log.warning('LoRa hardware not configured — running in STUB mode')
    return None


def receive_packet(radio):
    """
    Block until a packet arrives.  STUB — replace with actual receive call.

    Example:
        return radio.receive(timeout=30.0)
    """
    time.sleep(10)
    # Simulated packet — includes MFCC to test the full pipeline
    sample = json.dumps({
        "id": 1,
        "t_int": 34.7, "h_int": 64.7,
        "t_ext": 18.3, "h_ext": 55.0,
        "sf_int": 245.0, "sa_int": 0.42,
        "sf_ext": 120.0, "sa_ext": 0.11,
        "l_ext": 760.0,
        "mc_int": [-24.5,  7.2, -3.1,  1.4, -0.7],
        "mc_ext": [-18.3,  5.1, -2.2,  0.9, -0.3],
    }).encode()
    log.debug('STUB: returning simulated packet')
    return sample


def parse_packet(raw: bytes) -> dict | None:
    """
    Decode a raw LoRa payload (UTF-8 JSON) into the dict the Flask API expects.

    MFCC fields (mc_int / mc_ext) are optional: if the ESP32 doesn't send them
    yet, the fields are simply absent from the returned dict and the API/InfluxDB
    will silently ignore them.
    """
    try:
        data = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        log.warning('Could not decode packet: %s', e)
        return None

    beehive_id = data.get('id')
    if beehive_id is None:
        log.warning('Packet missing "id" field: %s', data)
        return None

    payload = {
        'beehive_id':      int(beehive_id),
        'temperature_int': data.get('t_int'),
        'humidity_int':    data.get('h_int'),
        'temperature_ext': data.get('t_ext'),
        'humidity_ext':    data.get('h_ext'),
        'sound_freq_int':  data.get('sf_int'),
        'sound_amp_int':   data.get('sa_int'),
        'sound_freq_ext':  data.get('sf_ext'),
        'sound_amp_ext':   data.get('sa_ext'),
        'light_ext':       data.get('l_ext'),
    }

    # ── MFCC (optional, added when ESP32 firmware is ready) ───────────────
    # mc_int / mc_ext are lists of 5 floats: [c1, c2, c3, c4, c5]
    # Validate shape if present; silently drop malformed values.
    for key, field in (('mc_int', 'mfcc_int'), ('mc_ext', 'mfcc_ext')):
        raw_list = data.get(key)
        if raw_list is not None:
            if isinstance(raw_list, list) and len(raw_list) == 5:
                try:
                    payload[field] = [float(v) for v in raw_list]
                except (TypeError, ValueError):
                    log.warning('Invalid MFCC values in "%s": %s', key, raw_list)
            else:
                log.warning('"%s" must be a list of 5 floats, got: %s', key, raw_list)

    return payload


def push_to_api(payload: dict) -> bool:
    """POST sensor data to the local Beetter Flask API."""
    try:
        resp = requests.post(API_ENDPOINT, json=payload, timeout=10)
        if resp.ok:
            fields = [k for k, v in payload.items()
                      if k != 'beehive_id' and v is not None]
            log.info('Data pushed : beehive=%s  fields=%s', payload.get('beehive_id'), ','.join(fields))
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
