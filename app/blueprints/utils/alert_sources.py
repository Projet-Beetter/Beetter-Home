ALERT_SOURCES = {
    'manual':      {'label': 'Manual change',    'icon': 'bi-person-fill'},
    'no_signal':   {'label': 'No signal',        'icon': 'bi-wifi-off'},
    'threshold':   {'label': 'Sensor threshold', 'icon': 'bi-graph-up-arrow'},
    'ml':          {'label': 'AI detection',     'icon': 'bi-cpu'},
}

def get_source_config(source):
    return ALERT_SOURCES.get(source, {'label': source, 'icon': 'bi-question-circle'})
