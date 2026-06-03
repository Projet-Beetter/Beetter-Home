STATUS_CONFIG = {
    'calm':         {'label': 'Calm',         'badge': 'bg-success',   'icon': ''},
    'stressed':     {'label': 'Stressed',     'badge': 'bg-warning',   'icon': ''},
    'agitated':     {'label': 'Agitated',     'badge': 'bg-orange',    'icon': ''},
    'critical':     {'label': 'Critical',     'badge': 'bg-danger',    'icon': ''},
    'swarming':     {'label': 'Swarming',     'badge': 'bg-danger',    'icon': ''},
    'queenless':    {'label': 'Queenless',    'badge': 'bg-danger',    'icon': ''},
    'predator':     {'label': 'Predator',     'badge': 'bg-danger',    'icon': ''},
    'ventilating':  {'label': 'Ventilating',  'badge': 'bg-info',      'icon': ''},
    'virgin_queen': {'label': 'Virgin queen', 'badge': 'bg-purple',    'icon': ''},
    'silent':       {'label': 'Silent',       'badge': 'bg-secondary', 'icon': ''},
    'no_data':      {'label': 'No data',      'badge': 'bg-dark',      'icon': ''},
}

def get_status_config(status):
    return STATUS_CONFIG.get(status, STATUS_CONFIG['no_data'])

def get_dot_color(status):
    if status in ('calm', 'ventilating'):
        return 'dot-green'
    elif status in ('stressed', 'agitated', 'virgin_queen'):
        return 'dot-yellow'
    elif status in ('critical', 'swarming', 'queenless', 'predator'):
        return 'dot-red'
    else:
        return 'dot-black'
