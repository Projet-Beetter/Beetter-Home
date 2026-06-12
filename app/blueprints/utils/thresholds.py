# Each tuple: (ok_min, ok_max, warn_min, warn_max)
#   ok zone   [ok_min  … ok_max]  → green
#   warn zone [warn_min… warn_max] but outside ok → orange
#   crit zone outside warn range entirely → red
THRESHOLDS = {
    "temperature_int":  (32,  38,   28,   42  ),  # °C
    "temperature_ext":  (5,   35,   0,    40  ),  # °C
    "humidity_int":     (50,  75,   40,   85  ),  # %
    "humidity_ext":     (30,  90,   20,   95  ),  # %
    "sound_freq_int":   (180, 320,  150,  400 ),  # Hz
    "light_ext":        (0,   20,   0,    60  ),  # %
}


def get_threshold_status(key, value):
    """Return 'ok', 'warn', or 'crit' based on THRESHOLDS."""
    if value is None or key not in THRESHOLDS:
        return "no_data"
    ok_min, ok_max, warn_min, warn_max = THRESHOLDS[key]
    if ok_min <= value <= ok_max:
        return "ok"
    if warn_min <= value <= warn_max:
        return "warn"
    return "crit"


def check_any_crit(sensor_dict):
    """
    Given a dict of {sensor_key: value}, return a list of keys
    that are in 'crit' status. Empty list = all ok/warn/no_data.
    """
    return [
        key for key, value in sensor_dict.items()
        if get_threshold_status(key, value) == "crit"
    ]


def check_any_warn(sensor_dict):
    """
    Return list of keys in 'warn' status (outside ok range but not crit).
    Empty list = all ok/no_data.
    """
    return [
        key for key, value in sensor_dict.items()
        if get_threshold_status(key, value) == "warn"
    ]


def all_ok(sensor_dict):
    """
    Return True if every present sensor value is within its ok range.
    Sensors absent from the dict (None values) are ignored.
    Returns False if sensor_dict is empty.
    """
    present = {k: v for k, v in sensor_dict.items()
               if v is not None and k in THRESHOLDS}
    if not present:
        return False
    return all(get_threshold_status(k, v) == "ok" for k, v in present.items())
