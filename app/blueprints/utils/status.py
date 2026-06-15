STATUS_FAMILIES = {
    'calm':     {'label': 'Calm',     'color': '#22c55e', 'alerting': False},
    'agitated': {'label': 'Warning',  'color': '#f97316', 'alerting': True},
    'critical': {'label': 'Critical', 'color': '#ef4444', 'alerting': True},
}

STATUS_CONFIG = {
    # Calm family
    'calm':         {'label': 'Calm',         'family': 'calm',     'badge': 'bg-success',   'icon': ''},
    'foraging':     {'label': 'Foraging',     'family': 'calm',     'badge': 'bg-success',   'icon': ''},
    'ventilating':  {'label': 'Ventilating',  'family': 'calm',     'badge': 'bg-success',   'icon': ''},
    # Agitated family
    'stressed':     {'label': 'Stressed',     'family': 'agitated', 'badge': 'bg-orange',    'icon': ''},
    'agitated':     {'label': 'Agitated',     'family': 'agitated', 'badge': 'bg-orange',    'icon': ''},
    'virgin_queen': {'label': 'Virgin queen', 'family': 'agitated', 'badge': 'bg-orange',    'icon': ''},
    # Critical family
    'critical':     {'label': 'Critical',     'family': 'critical', 'badge': 'bg-danger',    'icon': ''},
    'swarming':     {'label': 'Swarming',     'family': 'critical', 'badge': 'bg-danger',    'icon': ''},
    'queenless':    {'label': 'Queenless',    'family': 'critical', 'badge': 'bg-danger',    'icon': ''},
    'predator':     {'label': 'Predator',     'family': 'critical', 'badge': 'bg-danger',    'icon': ''},
    # No family
    'silent':       {'label': 'Silent',       'family': None,       'badge': 'bg-secondary', 'icon': ''},
    'no_data':      {'label': 'No data',      'family': None,       'badge': 'bg-dark',      'icon': ''},
}

ALERTING_STATUSES = tuple(k for k, v in STATUS_CONFIG.items() if v.get('family') in ('agitated', 'critical'))
CALM_STATUSES     = tuple(k for k, v in STATUS_CONFIG.items() if v.get('family') == 'calm')

def get_dot_color(status):
    family = STATUS_CONFIG.get(status, {}).get('family')
    if family == 'critical':
        return 'dot-red'
    elif family == 'agitated':
        return 'dot-yellow'
    elif family == 'calm':
        return 'dot-green'
    return 'dot-black'

def get_status_family(status):
    return STATUS_CONFIG.get(status, {}).get('family')
