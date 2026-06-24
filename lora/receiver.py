#!/usr/bin/env python3
"""
receiver.py  –  Récepteur LoRa Beetter Home
============================================
Reçoit les trames Beetter (blocs ENV et/ou AUD) via le module
Grove LoRa 868MHz branché sur le Raspberry Pi, et envoie les relevés
décodés à l'API Flask locale (POST /api/data) — exactement comme le
fait tools/simulate.py. C'est Flask qui écrit ensuite dans InfluxDB,
vérifie les seuils et déclenche les alertes.

Nomenclature des champs : identique à l'API Flask (POST /api/data)
  temperature_int / humidity_int
  temperature_ext / humidity_ext
  sound_freq_int  / sound_amp_int
  sound_freq_ext  / sound_amp_ext
  light_ext
  mfcc_int[0..12] / mfcc_ext[0..12]

Basé sur grove_lora.py (doit être dans le même dossier).

Firmware v4 : seq passe de uint16 à uint32 dans les blocs ENV et AUD.
  SIZE_ENV : 23 → 25 bytes  |  SIZE_AUD : 73 → 75 bytes
  FMT_ENV  : BH → BI        |  FMT_AUD  : BH → BI

Lancement :
  python3 receiver.py

Avec envoi vers l'API Flask :
  API_ENABLE=1 python3 receiver.py

Horodatage InfluxDB :
  Par défaut : heure de réception du Raspberry Pi (datetime.now UTC).
  Pour utiliser l'heure embarquée dans la trame LoRa :
    USE_LORA_TIMESTAMP=1 python3 receiver.py
"""

import struct
import math
import time
import os
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
import requests
from grove_lora import GroveLoRa

# ─── Inference (IA) ──────────────────────────────────────────
_IA_DIR = Path(__file__).parent.parent / "IA"
sys.path.insert(0, str(_IA_DIR))

try:
    import torch
    from beehive.model import ContrastiveBeehiveModel, BeehiveFineTuner
    from beehive.data import FeatureNormalizer
    from beehive.config import MODEL_CFG
    from beehive.inference import BeehiveInference
    from influxdb_client import InfluxDBClient, Point, WritePrecision
    from influxdb_client.client.write_api import SYNCHRONOUS
    _INFERENCE_AVAILABLE = True
except ImportError as _e:
    logging.warning(f"Inference non disponible : {_e}")
    _INFERENCE_AVAILABLE = False

# ─── Load .env from parent directory ─────────────────────────
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# ─── Configuration ───────────────────────────────────────────
PORT      = "/dev/serial0"   # Adapter si USB : "/dev/ttyUSB0"
FREQUENCE = 868.0

# ─── Magics et tailles ───────────────────────────────────────
MAGIC_ENV  = 0xE0
MAGIC_AUD  = 0xA0
SIZE_ENV   = 25   # +2 bytes : seq uint16 → uint32 (firmware v4)
SIZE_AUD   = 75   # +2 bytes : seq uint16 → uint32 (firmware v4)

# seq passe de H (uint16) à I (uint32) — firmware v4
FMT_ENV = "<BI4sIhHhHHH"
FMT_AUD = "<BI4sIHHHH13h13hH"

# ─── API Flask (POST /api/data) ───────────────────────────────
# Même approche que tools/simulate.py : on pousse du JSON à l'app
# Flask locale, qui se charge elle-même d'écrire dans InfluxDB,
# de vérifier les seuils et de créer les alertes si besoin.
API_ENABLE  = os.getenv("API_ENABLE", "0") == "1"
API_URL     = os.getenv("BEETTER_API_URL", "http://localhost:5000")
API_TIMEOUT = float(os.getenv("BEETTER_API_TIMEOUT", "5"))

# ─── Horodatage ───────────────────────────────────────────────
# USE_LORA_TIMESTAMP=1 → timestamp de la trame LoRa (horloge du boîtier)
# USE_LORA_TIMESTAMP=0 → heure de réception du Raspberry Pi (défaut)
USE_LORA_TIMESTAMP = os.getenv("USE_LORA_TIMESTAMP", "0") == "1"

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("beetter")

# ─── Inference engine ─────────────────────────────────────────
def _charger_inference() -> BeehiveInference | None:
    if not _INFERENCE_AVAILABLE:
        return None
    try:
        backbone  = ContrastiveBeehiveModel(MODEL_CFG)
        finetuner = BeehiveFineTuner(backbone)
        state = torch.load(_IA_DIR / "checkpoints/finetune_best.pt", map_location="cpu", weights_only=True)
        finetuner.load_state_dict(state)
        norm_in  = FeatureNormalizer.load(_IA_DIR / "calibration/norm_in.json")
        norm_out = FeatureNormalizer.load(_IA_DIR / "calibration/norm_out.json")
        engine = BeehiveInference(finetuner, norm_in, norm_out)
        log.info("Moteur d'inférence chargé.")
        return engine
    except Exception as e:
        log.warning(f"Impossible de charger le modèle : {e}")
        return None


def _ecrire_influx_anomalie(result, beehive_id: str, ts_iso: str) -> None:
    """Écrit le résultat d'inférence dans le bucket 'anomaly' d'InfluxDB."""
    if not _INFERENCE_AVAILABLE:
        return
    try:
        url   = os.getenv("INFLUXDB_URL",   "http://localhost:8086")
        token = os.getenv("INFLUXDB_TOKEN",  "")
        org   = os.getenv("INFLUXDB_ORG",    "")
        with InfluxDBClient(url=url, token=token, org=org) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)
            point = (
                Point("anomaly_score")
                .tag("hive_id", beehive_id)
                .field("p_normal",  float(result.probabilities[0]))
                .field("p_anomaly", float(result.probabilities[1]))
                .field("label",     result.label)
                .field("alert",     result.alert)
                .time(ts_iso, WritePrecision.SECONDS)
            )
            write_api.write(bucket="anomaly", org=org, record=point)
            log.info(f"Inférence → {result.label} "
                     f"(normal={result.probabilities[0]:.0%} "
                     f"anomaly={result.probabilities[1]:.0%})"
                     f"{' ⚠ ALERTE' if result.alert else ''}")
    except Exception as e:
        log.warning(f"Erreur écriture InfluxDB anomaly : {e}")

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
    #          t_ext×100, h_ext×10, lum×10, crc

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
        "light_ext"      : v[8] / 10.0,

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
        # Encodage différencié (firmware v2) :
        #   MFCC0      × 10   → ÷ 10.0    (résolution 0.1)
        #   MFCC1..12  × 1000 → ÷ 1000.0  (résolution 0.001, 10× plus précis)
        "mfcc_int"      : [v[8]  / 10.0] + [x / 1000.0 for x in v[9:21]],
        "mfcc_ext"      : [v[21] / 10.0] + [x / 1000.0 for x in v[22:34]],
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
    print(f"│  light_ext       : {d['light_ext']:>5.1f} / 10")
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
#  Envoi vers l'API Flask (POST /api/data) — même approche
#  que tools/simulate.py (fonction send()).
# ═══════════════════════════════════════════════════════════
def construire_payload(blocs: list) -> dict | None:
    """
    Agrège les blocs ENV + AUD reçus dans ce cycle en un seul payload
    JSON, avec exactement les mêmes noms de champs que simulate.py /
    POST /api/data.

    beehive_id reste tel que décodé depuis la trame (ASCII, ex. "B001") :
    la base de données stocke désormais l'ID de ruche en string, donc
    plus besoin de conversion vers un entier.
    """
    payload: dict = {}
    beehive_id = None
    ts_lora = None

    for d in blocs:
        beehive_id = d["beehive_id"]
        if ts_lora is None:
            ts_lora = d["ts_iso"]

        if d["type"] == "ENV":
            payload["temperature_int"] = d["temperature_int"]
            payload["humidity_int"]    = d["humidity_int"]
            payload["temperature_ext"] = d["temperature_ext"]
            payload["humidity_ext"]    = d["humidity_ext"]
            payload["light_ext"]       = d["light_ext"]

        elif d["type"] == "AUD":
            payload["sound_freq_int"] = d["sound_freq_int"]
            payload["sound_amp_int"]  = d["sound_amp_int"]
            payload["sound_freq_ext"] = d["sound_freq_ext"]
            payload["sound_amp_ext"]  = d["sound_amp_ext"]
            payload["mfcc_int"]       = d["mfcc_int"]
            payload["mfcc_ext"]       = d["mfcc_ext"]

    if not payload or beehive_id is None:
        return None

    if USE_LORA_TIMESTAMP:
        ts_iso = ts_lora
    else:
        ts_iso = datetime.now(timezone.utc).isoformat()

    payload["beehive_id"] = beehive_id
    payload["timestamp"]  = ts_iso
    return payload


def envoyer_api(blocs: list) -> None:
    """
    Construit le payload JSON et le POST sur {API_URL}/api/data,
    exactement comme send() dans tools/simulate.py.
    """
    payload = construire_payload(blocs)
    if payload is None:
        return

    try:
        r = requests.post(f"{API_URL}/api/data", json=payload, timeout=API_TIMEOUT)
        if r.ok:
            mfcc_tag = " +MFCC" if "mfcc_int" in payload else ""
            log.info(f"API : relevé envoyé (ruche {payload['beehive_id']}, "
                      f"{payload['timestamp']}){mfcc_tag}")
        else:
            log.error(f"API erreur HTTP {r.status_code} : {r.text}")
    except requests.RequestException as e:
        log.error(f"API injoignable ({API_URL}) : {e}")


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════
def main():
    log.info("=== Beetter Home – Receiver LoRa ===")
    log.info(f"Port       : {PORT} @ 57600 bauds")
    log.info(f"Fréquence  : {FREQUENCE} MHz")
    log.info(f"API Flask  : {'activé (' + API_URL + ')' if API_ENABLE else 'désactivé'}")
    log.info(f"Horodatage : {'trame LoRa (USE_LORA_TIMESTAMP=1)' if USE_LORA_TIMESTAMP else 'réception Raspberry Pi (défaut)'}")
    log.info(f"Blocs      : ENV={SIZE_ENV}B (0xE0)  AUD={SIZE_AUD}B (0xA0)")

    lora = GroveLoRa(port=PORT, baudrate=57600)
    log.info("Initialisation du module Grove LoRa...")
    inference_engine = _charger_inference()

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

            # Envoi vers l'API Flask (regroupe ENV + AUD du même cycle)
            if API_ENABLE:
                envoyer_api(blocs)
            # ─── Inférence IA ────────────────────────────────
            if inference_engine is not None:
                env_bloc = next((b for b in blocs if b["type"] == "ENV"), None)
                aud_bloc = next((b for b in blocs if b["type"] == "AUD"), None)
                if env_bloc and aud_bloc:
                    features = {
                        "t_in_C":          env_bloc["temperature_int"],
                        "h_in_pct":        env_bloc["humidity_int"],
                        "t_out_C":         env_bloc["temperature_ext"],
                        "h_out_pct":       env_bloc["humidity_ext"],
                        "dom_freq_in_hz":  aud_bloc["sound_freq_int"],
                        "rms_in":          aud_bloc["sound_amp_int"],
                        "dom_freq_out_hz": aud_bloc["sound_freq_ext"],
                        "rms_out":         aud_bloc["sound_amp_ext"],
                        **{f"mfcc_in_{i}":  aud_bloc["mfcc_int"][i] for i in range(13)},
                        **{f"mfcc_out_{i}": aud_bloc["mfcc_ext"][i] for i in range(13)},
                        "timestamp_min":   0,
                        "anomaly_flag":    0,
                    }
                    result = inference_engine.infer_from_features(features)
                    _ecrire_influx_anomalie(result, env_bloc["beehive_id"], env_bloc["ts_iso"])
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