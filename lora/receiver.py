#!/usr/bin/env python3
"""
receiver.py  –  Récepteur LoRa Beetter Home
============================================
Reçoit les trames Beetter (blocs ENV et/ou AUD) via le module
Grove LoRa 868MHz branché sur le Raspberry Pi, et écrit dans InfluxDB
via la fonction write_sensor_data() de influxdb.py.

Nomenclature des champs : identique à influxdb.py (beetter.fr)
  temperature_int / humidity_int
  temperature_ext / humidity_ext
  sound_freq_int  / sound_amp_int
  sound_freq_ext  / sound_amp_ext
  light_ext
  mfcc_int_0..12  / mfcc_ext_0..12

Basé sur grove_lora.py (doit être dans le même dossier).

Lancement :
  python3 receiver.py

Avec écriture InfluxDB :
  INFLUX_ENABLE=1 python3 receiver.py
"""

import struct
import math
import time
import os
import sys
import logging
from datetime import datetime, timezone
from grove_lora import GroveLoRa

# ─── Configuration ───────────────────────────────────────────
PORT      = "/dev/serial0"   # Adapter si USB : "/dev/ttyUSB0"
FREQUENCE = 868.0

# ─── Magics et tailles ───────────────────────────────────────
MAGIC_ENV  = 0xE0
MAGIC_AUD  = 0xA0
SIZE_ENV   = 23
SIZE_AUD   = 73

FMT_ENV = "<BH4sIhHhHHH"
FMT_AUD = "<BH4sIHHHH13h13hH"

# ─── InfluxDB ────────────────────────────────────────────────
INFLUX_ENABLE = os.getenv("INFLUX_ENABLE", "0") == "1"
INFLUX_URL    = os.getenv("INFLUX_URL",    "http://localhost:8086")
INFLUX_TOKEN  = os.getenv("INFLUX_TOKEN",  "votre_token_ici")
INFLUX_ORG    = os.getenv("INFLUX_ORG",    "beetter")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "beetter")

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("beetter")


# ═══════════════════════════════════════════════════════════
#  CRC-16/CCITT
# ═══════════════════════════════════════════════════════════
def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = (crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1
        crc &= 0xFFFF
    return crc


# ═══════════════════════════════════════════════════════════
#  Humidité absolue (g/m³) – recalculée côté Home
# ═══════════════════════════════════════════════════════════
def hum_absolue(temp_c: float, rh: float) -> float:
    if temp_c <= -243.5:
        return 0.0
    es = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
    return (rh / 100.0) * es * 216.7 / (temp_c + 273.15)


# ═══════════════════════════════════════════════════════════
#  Décodage BLOC ENV (23 bytes)
#  Champs nommés selon la nomenclature influxdb.py
# ═══════════════════════════════════════════════════════════
def decoder_env(data: bytes) -> dict | None:
    if len(data) < SIZE_ENV or data[0] != MAGIC_ENV:
        return None

    bloc = data[:SIZE_ENV]
    crc_recu = struct.unpack_from("<H", bloc, SIZE_ENV - 2)[0]
    if crc_recu != crc16_ccitt(bloc[:-2]):
        log.warning(f"ENV CRC invalide : 0x{crc_recu:04X}")
        return None

    v = struct.unpack(FMT_ENV, bloc)
    # v : magic, seq, hive_id, ts, t_int×100, h_int×10,
    #          t_ext×100, h_ext×10, lum, crc

    t_int = v[4] / 100.0
    h_int = v[5] / 10.0
    t_ext = v[6] / 100.0
    h_ext = v[7] / 10.0

    return {
        # Méta
        "type"           : "ENV",
        "seq"            : v[1],
        "beehive_id"     : v[2].decode("ascii").rstrip("\x00"),
        "ts"             : v[3],
        "ts_iso"         : datetime.fromtimestamp(v[3], tz=timezone.utc).isoformat(),
        "crc_ok"         : True,

        # Nomenclature influxdb.py ← noms identiques à write_sensor_data()
        "temperature_int": t_int,
        "humidity_int"   : h_int,
        "temperature_ext": t_ext,
        "humidity_ext"   : h_ext,
        "light_ext"      : float(v[8]),

        # Humidité absolue (calculée, non stockée dans InfluxDB directement
        # mais utile pour l'affichage console)
        "hum_abs_int"    : hum_absolue(t_int, h_int),
        "hum_abs_ext"    : hum_absolue(t_ext, h_ext),
    }


# ═══════════════════════════════════════════════════════════
#  Décodage BLOC AUD (73 bytes)
#  Champs nommés selon la nomenclature influxdb.py
# ═══════════════════════════════════════════════════════════
def decoder_aud(data: bytes) -> dict | None:
    if len(data) < SIZE_AUD or data[0] != MAGIC_AUD:
        return None

    bloc = data[:SIZE_AUD]
    crc_recu = struct.unpack_from("<H", bloc, SIZE_AUD - 2)[0]
    if crc_recu != crc16_ccitt(bloc[:-2]):
        log.warning(f"AUD CRC invalide : 0x{crc_recu:04X}")
        return None

    v = struct.unpack(FMT_AUD, bloc)
    # v : magic, seq, hive_id, ts,
    #     fi×10, ri×10000, fe×10, re×10000,
    #     mfcc_int[13]×100, mfcc_ext[13]×100, crc

    return {
        # Méta
        "type"          : "AUD",
        "seq"           : v[1],
        "beehive_id"    : v[2].decode("ascii").rstrip("\x00"),
        "ts"            : v[3],
        "ts_iso"        : datetime.fromtimestamp(v[3], tz=timezone.utc).isoformat(),
        "crc_ok"        : True,

        # Nomenclature influxdb.py ← noms identiques à write_sensor_data()
        "sound_freq_int": v[4] / 10.0,
        "sound_amp_int" : v[5] / 10000.0,
        "sound_freq_ext": v[6] / 10.0,
        "sound_amp_ext" : v[7] / 10000.0,

        # MFCC : liste de 13 floats — write_sensor_data() les éclate
        # en mfcc_int_0..mfcc_int_12 et mfcc_ext_0..mfcc_ext_12
        "mfcc_int"      : [x / 100.0 for x in v[8:21]],
        "mfcc_ext"      : [x / 100.0 for x in v[21:34]],
    }


# ═══════════════════════════════════════════════════════════
#  Parsing d'une trame → liste de blocs décodés
# ═══════════════════════════════════════════════════════════
def parser_trame(payload: bytes) -> list:
    blocs = []
    pos   = 0
    while pos < len(payload):
        octet = payload[pos]
        if octet == MAGIC_ENV:
            if pos + SIZE_ENV > len(payload):
                log.warning("Trame ENV tronquée"); break
            b = decoder_env(payload[pos:])
            if b: blocs.append(b)
            pos += SIZE_ENV
        elif octet == MAGIC_AUD:
            if pos + SIZE_AUD > len(payload):
                log.warning("Trame AUD tronquée"); break
            b = decoder_aud(payload[pos:])
            if b: blocs.append(b)
            pos += SIZE_AUD
        else:
            pos += 1
    return blocs


# ═══════════════════════════════════════════════════════════
#  Affichage console
# ═══════════════════════════════════════════════════════════
def afficher_env(d: dict, rssi) -> None:
    print(f"\n┌── BLOC ENV ─ Ruche {d['beehive_id']} ─ #{d['seq']} ─ RSSI {rssi} dBm")
    print(f"│  {d['ts_iso']}")
    print(f"│  temperature_int : {d['temperature_int']:>7.2f} °C    "
          f"humidity_int : {d['humidity_int']:>6.1f} %RH  "
          f"(abs: {d['hum_abs_int']:.2f} g/m³)")
    print(f"│  temperature_ext : {d['temperature_ext']:>7.2f} °C    "
          f"humidity_ext : {d['humidity_ext']:>6.1f} %RH  "
          f"(abs: {d['hum_abs_ext']:.2f} g/m³)")
    print(f"│  light_ext       : {d['light_ext']:>7.0f} ADC")
    print(f"└{'─'*60}")


def afficher_aud(d: dict, rssi) -> None:
    mfcc_i = ", ".join(f"{x:>6.2f}" for x in d['mfcc_int'])
    mfcc_e = ", ".join(f"{x:>6.2f}" for x in d['mfcc_ext'])
    print(f"\n┌── BLOC AUD ─ Ruche {d['beehive_id']} ─ #{d['seq']} ─ RSSI {rssi} dBm")
    print(f"│  {d['ts_iso']}")
    print(f"│  sound_freq_int  : {d['sound_freq_int']:>7.1f} Hz    "
          f"sound_amp_int  : {d['sound_amp_int']:.4f}")
    print(f"│  sound_freq_ext  : {d['sound_freq_ext']:>7.1f} Hz    "
          f"sound_amp_ext  : {d['sound_amp_ext']:.4f}")
    print(f"│  mfcc_int[0..12] : [{mfcc_i}]")
    print(f"│  mfcc_ext[0..12] : [{mfcc_e}]")
    print(f"└{'─'*60}")


# ═══════════════════════════════════════════════════════════
#  Écriture InfluxDB via write_sensor_data() de influxdb.py
# ═══════════════════════════════════════════════════════════
def ecrire_influxdb(blocs: list) -> None:
    """
    Appelle write_sensor_data() avec les champs issus des blocs décodés.
    Les noms de champs sont identiques à ceux de influxdb.py :
      temperature_int, humidity_int, temperature_ext, humidity_ext,
      sound_freq_int, sound_amp_int, sound_freq_ext, sound_amp_ext,
      light_ext, mfcc_int (list[13]), mfcc_ext (list[13])
    """
    try:
        from influxdb_client import InfluxDBClient, Point, WritePrecision
        from influxdb_client.client.write_api import SYNCHRONOUS
        from datetime import datetime, timezone

        client = InfluxDBClient(
            url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG
        )
        write = client.write_api(write_options=SYNCHRONOUS)

        # Agréger les données de tous les blocs reçus dans ce cycle
        kwargs: dict = {}
        ts = None

        for d in blocs:
            ts = datetime.fromtimestamp(d["ts"], tz=timezone.utc)
            beehive_id = d["beehive_id"]

            if d["type"] == "ENV":
                kwargs["temperature_int"] = d["temperature_int"]
                kwargs["humidity_int"]    = d["humidity_int"]
                kwargs["temperature_ext"] = d["temperature_ext"]
                kwargs["humidity_ext"]    = d["humidity_ext"]
                kwargs["light_ext"]       = d["light_ext"]

            elif d["type"] == "AUD":
                kwargs["sound_freq_int"]  = d["sound_freq_int"]
                kwargs["sound_amp_int"]   = d["sound_amp_int"]
                kwargs["sound_freq_ext"]  = d["sound_freq_ext"]
                kwargs["sound_amp_ext"]   = d["sound_amp_ext"]
                kwargs["mfcc_int"]        = d["mfcc_int"]
                kwargs["mfcc_ext"]        = d["mfcc_ext"]

        if not kwargs or ts is None:
            return

        # Construction des points InfluxDB
        # Scalaires
        scalar_map = {
            "temperature_int": kwargs.get("temperature_int"),
            "humidity_int"   : kwargs.get("humidity_int"),
            "temperature_ext": kwargs.get("temperature_ext"),
            "humidity_ext"   : kwargs.get("humidity_ext"),
            "sound_freq_int" : kwargs.get("sound_freq_int"),
            "sound_amp_int"  : kwargs.get("sound_amp_int"),
            "sound_freq_ext" : kwargs.get("sound_freq_ext"),
            "sound_amp_ext"  : kwargs.get("sound_amp_ext"),
            "light_ext"      : kwargs.get("light_ext"),
        }

        points = [
            Point(measurement)
            .tag("beehive_id", str(beehive_id))
            .field("value", float(value))
            .time(ts, WritePrecision.S)
            for measurement, value in scalar_map.items()
            if value is not None
        ]

        # MFCC : mfcc_int_0..12 et mfcc_ext_0..12
        for coeff_list, prefix in (
            (kwargs.get("mfcc_int"), "mfcc_int"),
            (kwargs.get("mfcc_ext"), "mfcc_ext"),
        ):
            if coeff_list and len(coeff_list) == 13:
                for i, val in enumerate(coeff_list):
                    points.append(
                        Point(f"{prefix}_{i}")
                        .tag("beehive_id", str(beehive_id))
                        .field("value", float(val))
                        .time(ts, WritePrecision.S)
                    )

        write.write(
            bucket=INFLUX_BUCKET,
            org=INFLUX_ORG,
            record=points,
        )
        client.close()
        log.info(f"InfluxDB : {len(points)} points écrits "
                 f"(ruche {beehive_id}, ts {ts.isoformat()})")

    except ImportError:
        log.warning("influxdb-client non installé : pip3 install influxdb-client")
    except Exception as e:
        log.error(f"InfluxDB erreur : {e}")


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    log.info("=== Beetter Home – Receiver LoRa ===")
    log.info(f"Port       : {PORT} @ 57600 bauds")
    log.info(f"Fréquence  : {FREQUENCE} MHz")
    log.info(f"InfluxDB   : {'activé' if INFLUX_ENABLE else 'désactivé'}")
    log.info(f"Blocs      : ENV={SIZE_ENV}B (0xE0)  AUD={SIZE_AUD}B (0xA0)")

    lora = GroveLoRa(port=PORT, baudrate=57600)
    log.info("Initialisation du module Grove LoRa...")

    if not lora.init():
        log.error("Echec init LoRa. Vérifier câblage et port série.")
        lora.close()
        sys.exit(1)

    lora.set_frequency(FREQUENCE)
    log.info(f"Prêt sur {FREQUENCE} MHz. En attente de trames Beetter...\n")

    nb_recus   = 0
    nb_env     = 0
    nb_aud     = 0
    nb_erreurs = 0
    seq_par_ruche: dict = {}

    try:
        while True:
            msg = lora.recv()
            if msg is None:
                time.sleep(0.02)
                continue

            nb_recus += 1
            rssi = lora.last_rssi if lora.last_rssi is not None else "?"

            log.info(f"Trame reçue : {len(msg)} bytes | "
                     f"hex : {msg[:6].hex(' ')}... | RSSI : {rssi} dBm")

            blocs = parser_trame(msg)

            if not blocs:
                log.warning("Aucun bloc valide.")
                nb_erreurs += 1
                continue

            for d in blocs:
                hive = d["beehive_id"]
                seq  = d["seq"]

                # Détection de pertes
                if hive in seq_par_ruche:
                    ecart = seq - seq_par_ruche[hive] - 1
                    if ecart > 0:
                        log.warning(f"⚠ Ruche {hive} : {ecart} trame(s) "
                                    f"perdue(s) (#{seq_par_ruche[hive]} → #{seq})")
                seq_par_ruche[hive] = seq

                if d["type"] == "ENV":
                    afficher_env(d, rssi)
                    nb_env += 1
                elif d["type"] == "AUD":
                    afficher_aud(d, rssi)
                    nb_aud += 1

            # Écriture InfluxDB (regroupe ENV + AUD du même cycle)
            if INFLUX_ENABLE:
                ecrire_influxdb(blocs)

            log.info(f"Stats : {nb_recus} reçues | {nb_env} ENV | "
                     f"{nb_aud} AUD | {nb_erreurs} erreurs")

    except KeyboardInterrupt:
        print()
        log.info("Arrêt.")
    finally:
        lora.close()
        log.info(f"Bilan : {nb_recus} trames | {nb_env} ENV | "
                 f"{nb_aud} AUD | {nb_erreurs} erreurs")


if __name__ == "__main__":
    main()
