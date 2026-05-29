ALERT_SOURCES = {
    'manual':      {'label': 'Manual change',    'icon': 'bi-person-fill'},
    'no_signal':   {'label': 'No signal',        'icon': 'bi-wifi-off'},
}

def get_source_config(source):
    return ALERT_SOURCES.get(source, {'label': source, 'icon': 'bi-question-circle'})
