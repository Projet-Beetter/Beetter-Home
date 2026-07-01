#!/usr/bin/env python3
"""
grove_lora.py
-------------
Portage Python du protocole UART de la bibliotheque Seeed
"Grove_LoRa_433MHz_and_915MHz_RF" (classes RHUartDriver + RH_RF95).

Permet de piloter un module Grove - LoRa Radio 868MHz (SKU 113060006)
depuis un Raspberry Pi via /dev/serial0, SANS rien souder ni reflasher :
on reproduit exactement les trames serie que l'Arduino envoie au module.

Points cles decouverts dans le code source Seeed :
  - Le module est un PONT serie<->SPI transparent vers la puce RFM95.
  - Le protocole n'est PAS "envoyer un message" : on lit/ecrit les
    REGISTRES du RFM95 a distance.
        Ecrire : 'W' + (reg | 0x80) + len + data...
        Lire   : 'R' + (reg & 0x7F) + len   -> le module renvoie len octets
  - >>> Le baudrate du module est 57600 <<< (et PAS 9600 !).
  - Quand le module a une interruption a signaler, il envoie l'octet 'I'.

Compatible radio avec les sketches Arduino rf95_client / rf95_server
A CONDITION de regler la MEME frequence des deux cotes (voir plus bas).
"""

import time
import struct
import serial

# ------------------------------------------------------------------ #
#  Constantes (tirees de RH_RF95.h)
# ------------------------------------------------------------------ #
RH_WRITE_MASK = 0x80

# Registres
REG_00_FIFO                 = 0x00
REG_01_OP_MODE              = 0x01
REG_06_FRF_MSB              = 0x06
REG_07_FRF_MID              = 0x07
REG_08_FRF_LSB             = 0x08
REG_09_PA_CONFIG           = 0x09
REG_0D_FIFO_ADDR_PTR       = 0x0D
REG_0E_FIFO_TX_BASE_ADDR   = 0x0E
REG_0F_FIFO_RX_BASE_ADDR   = 0x0F
REG_10_FIFO_RX_CURRENT_ADDR = 0x10
REG_12_IRQ_FLAGS           = 0x12
REG_13_RX_NB_BYTES         = 0x13
REG_1A_PKT_RSSI_VALUE      = 0x1A
REG_1D_MODEM_CONFIG1       = 0x1D
REG_1E_MODEM_CONFIG2       = 0x1E
REG_20_PREAMBLE_MSB        = 0x20
REG_21_PREAMBLE_LSB        = 0x21
REG_22_PAYLOAD_LENGTH      = 0x22
REG_26_MODEM_CONFIG3       = 0x26
REG_40_DIO_MAPPING1        = 0x40
REG_42_VERSION             = 0x42
REG_4D_PA_DAC              = 0x4D

# Modes (REG_01)
LONG_RANGE_MODE   = 0x80
MODE_SLEEP        = 0x00
MODE_STDBY        = 0x01
MODE_TX           = 0x03
MODE_RXCONTINUOUS = 0x05

# IRQ flags (REG_12)
RX_TIMEOUT        = 0x80
RX_DONE           = 0x40
PAYLOAD_CRC_ERROR = 0x20
TX_DONE           = 0x08

# PA config
PA_SELECT         = 0x80
MAX_POWER         = 0x70
PA_DAC_DISABLE    = 0x04
PA_DAC_ENABLE     = 0x07

# Frequence
FXOSC = 32000000.0
FSTEP = FXOSC / 524288          # = FXOSC / 2^19

HEADER_LEN          = 4
MAX_PAYLOAD_LEN     = 255
MAX_MESSAGE_LEN     = MAX_PAYLOAD_LEN - HEADER_LEN

BROADCAST_ADDRESS   = 0xFF

# Table modem config (reg 1d, 1e, 26) - identique a l'Arduino
MODEM_CONFIG_TABLE = {
    "Bw125Cr45Sf128":  (0x72, 0x74, 0x00),  # defaut chip + defaut RadioHead
    "Bw500Cr45Sf128":  (0x92, 0x74, 0x00),
    "Bw31_25Cr48Sf512": (0x48, 0x94, 0x00),
    "Bw125Cr48Sf4096": (0x78, 0xC4, 0x00),
}


class GroveLoRa:
    def __init__(self, port="/dev/serial0", baudrate=57600, timeout=0.1, debug=False):
        # NB : 57600 est le baudrate impose par le firmware du module Grove.
        self.ser = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        self.debug = debug
        self._mode = "idle"
        self._buf = b""
        self._rx_valid = False
        self._this_address = BROADCAST_ADDRESS
        self._tx_to = BROADCAST_ADDRESS
        self._tx_from = BROADCAST_ADDRESS
        self._tx_id = 0
        self._tx_flags = 0
        self.last_rssi = None
        time.sleep(0.1)
        self.ser.reset_input_buffer()
        self.ser.reset_output_buffer()

    # ---------- couche transport (RHUartDriver) ---------- #
    def _uart_tx(self, reg, data):
        """ 'W' + reg + len + data """
        frame = bytes([ord('W'), reg & 0xFF, len(data)]) + bytes(data)
        if self.debug:
            print("TX>", frame.hex())
        self.ser.write(frame)

    def _uart_rx(self, reg, length, timeout=3.0):
        """ 'R' + reg + len  -> lit 'length' octets renvoyes par le module """
        self.ser.write(bytes([ord('R'), reg & 0xFF, length]))
        out = bytearray()
        start = time.time()
        while len(out) < length:
            b = self.ser.read(1)
            if b:
                out += b
            if time.time() - start > timeout:
                break
        if self.debug:
            print("RX<", out.hex(), "(reg %02X)" % reg)
        return bytes(out)

    def write(self, reg, val):
        self._uart_tx(reg | RH_WRITE_MASK, [val & 0xFF])

    def read(self, reg):
        r = self._uart_rx(reg & ~RH_WRITE_MASK, 1)
        return r[0] if r else None

    def burst_write(self, reg, data):
        self._uart_tx(reg | RH_WRITE_MASK, data)

    def burst_read(self, reg, length):
        return self._uart_rx(reg & ~RH_WRITE_MASK, length)

    # ---------- init RFM95 ---------- #
    def init(self):
        # Mode sleep + LoRa
        self.write(REG_01_OP_MODE, MODE_SLEEP | LONG_RANGE_MODE)
        time.sleep(0.01)
        opmode = self.read(REG_01_OP_MODE)
        if opmode != (MODE_SLEEP | LONG_RANGE_MODE):
            print("init: reponse OP_MODE inattendue: %s (attendu 0x80)"
                  % ("None" if opmode is None else "0x%02X" % opmode))
            print(" -> verifie : baudrate 57600 ? cablage TX/RX croise ? VCC ?")
            return False

        self.write(REG_0E_FIFO_TX_BASE_ADDR, 0)
        self.write(REG_0F_FIFO_RX_BASE_ADDR, 0)
        self.set_mode_idle()
        self.set_modem_config("Bw125Cr45Sf128")  # defaut, comme l'Arduino
        self.set_preamble_length(8)
        self.set_frequency(868.0)
        self.set_tx_power(13)
        return True

    # ---------- config ---------- #
    def set_modem_config(self, name):
        c1, c2, c3 = MODEM_CONFIG_TABLE[name]
        self.write(REG_1D_MODEM_CONFIG1, c1)
        self.write(REG_1E_MODEM_CONFIG2, c2)
        self.write(REG_26_MODEM_CONFIG3, c3)

    def set_preamble_length(self, length):
        self.write(REG_20_PREAMBLE_MSB, (length >> 8) & 0xFF)
        self.write(REG_21_PREAMBLE_LSB, length & 0xFF)

    def set_frequency(self, mhz):
        frf = int((mhz * 1000000.0) / FSTEP)
        self.write(REG_06_FRF_MSB, (frf >> 16) & 0xFF)
        self.write(REG_07_FRF_MID, (frf >> 8) & 0xFF)
        self.write(REG_08_FRF_LSB, frf & 0xFF)

    def set_tx_power(self, power):
        # PA_BOOST uniquement (comme les RFM95)
        power = max(5, min(23, power))
        if power > 20:
            self.write(REG_4D_PA_DAC, PA_DAC_ENABLE)
            power -= 3
        else:
            self.write(REG_4D_PA_DAC, PA_DAC_DISABLE)
        self.write(REG_09_PA_CONFIG, PA_SELECT | (power - 5))

    # ---------- modes ---------- #
    def set_mode_idle(self):
        if self._mode != "idle":
            self.write(REG_01_OP_MODE, MODE_STDBY)
            self._mode = "idle"

    def set_mode_rx(self):
        if self._mode != "rx":
            self.write(REG_01_OP_MODE, MODE_RXCONTINUOUS)
            self.write(REG_40_DIO_MAPPING1, 0x00)  # IRQ on RxDone
            self._mode = "rx"

    def set_mode_tx(self):
        if self._mode != "tx":
            self.write(REG_01_OP_MODE, MODE_TX)
            self.write(REG_40_DIO_MAPPING1, 0x40)  # IRQ on TxDone
            self._mode = "tx"

    # ---------- interruption ---------- #
    def _handle_interrupt(self):
        irq = self.read(REG_12_IRQ_FLAGS)
        if irq is None:
            return
        if self._mode == "rx" and (irq & (RX_TIMEOUT | PAYLOAD_CRC_ERROR)):
            pass  # paquet rejete
        elif self._mode == "rx" and (irq & RX_DONE):
            length = self.read(REG_13_RX_NB_BYTES)
            cur = self.read(REG_10_FIFO_RX_CURRENT_ADDR)
            self.write(REG_0D_FIFO_ADDR_PTR, cur)
            data = self.burst_read(REG_00_FIFO, length)
            self.write(REG_12_IRQ_FLAGS, 0xFF)
            rssi = self.read(REG_1A_PKT_RSSI_VALUE)
            self.last_rssi = (rssi - 137) if rssi is not None else None
            self._validate_rx_buf(data)
            if self._rx_valid:
                self.set_mode_idle()
        elif self._mode == "tx" and (irq & TX_DONE):
            self.set_mode_idle()
        self.write(REG_12_IRQ_FLAGS, 0xFF)

    def _validate_rx_buf(self, data):
        if len(data) < HEADER_LEN:
            return
        to = data[0]
        # headers: to, from, id, flags
        if to == self._this_address or to == BROADCAST_ADDRESS:
            self._buf = data
            self._rx_valid = True

    # ---------- API publique ---------- #
    def available(self):
        # Si le module a poste un 'I', on traite l'interruption
        if self.ser.in_waiting:
            b = self.ser.read(1)
            if b == b'I':
                self._handle_interrupt()
        if self._mode == "tx":
            return False
        self.set_mode_rx()
        return self._rx_valid

    def recv(self):
        if not self.available():
            return None
        msg = self._buf[HEADER_LEN:]
        self._rx_valid = False
        self._buf = b""
        return msg

    def send(self, data):
        if isinstance(data, str):
            data = data.encode("utf-8")
        if len(data) > MAX_MESSAGE_LEN:
            return False
        self.wait_packet_sent()
        self.set_mode_idle()
        self.write(REG_0D_FIFO_ADDR_PTR, 0)
        self.write(REG_00_FIFO, self._tx_to)
        self.write(REG_00_FIFO, self._tx_from)
        self.write(REG_00_FIFO, self._tx_id)
        self.write(REG_00_FIFO, self._tx_flags)
        self.burst_write(REG_00_FIFO, data)
        self.write(REG_22_PAYLOAD_LENGTH, len(data) + HEADER_LEN)
        self.set_mode_tx()
        return True

    def wait_packet_sent(self, timeout=5.0):
        start = time.time()
        while self._mode == "tx":
            self.available()
            if time.time() - start > timeout:
                return False
            time.sleep(0.005)
        return True

    def wait_available_timeout(self, timeout):
        start = time.time()
        while time.time() - start < timeout:
            if self.available():
                return True
            time.sleep(0.01)
        return False

    def close(self):
        if self.ser.is_open:
            self.ser.close()
