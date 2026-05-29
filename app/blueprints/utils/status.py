STATUS_CONFIG = {
    'healthy':  {'label': 'Healthy',  'badge': 'bg-success',   'icon': 'bi-check-circle-fill'},
    'warning':  {'label': 'Warning',  'badge': 'bg-warning',   'icon': 'bi-exclamation-triangle-fill'},
    'critical': {'label': 'Critical', 'badge': 'bg-danger',    'icon': 'bi-x-circle-fill'},
    'offline':  {'label': 'Offline',  'badge': 'bg-secondary', 'icon': 'bi-slash-circle'},
    'no_data':  {'label': 'No data',  'badge': 'bg-dark',      'icon': 'bi-question-circle'},
}

def get_status_config(status):
    return STATUS_CONFIG.get(status, STATUS_CONFIG['no_data'])
