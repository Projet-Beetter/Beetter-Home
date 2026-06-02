STATUS_CONFIG = {
    'calm':     {'label': 'Calm',     'badge': 'bg-success',   'icon': 'bi-emoji-smile'},
    'stressed': {'label': 'Stressed', 'badge': 'bg-warning',   'icon': 'bi-emoji-expressionless'},
    'agitated': {'label': 'Agitated', 'badge': 'bg-orange',    'icon': 'bi-emoji-frown'},
    'critical': {'label': 'Critical', 'badge': 'bg-danger',    'icon': 'bi-exclamation-octagon-fill'},
    'silent':  {'label': 'Silent',  'badge': 'bg-secondary', 'icon': 'bi-moon-stars-fill'},
    'no_data':  {'label': 'No data',  'badge': 'bg-dark',      'icon': 'bi-question-circle'},
}

def get_status_config(status):
    return STATUS_CONFIG.get(status, STATUS_CONFIG['no_data'])
