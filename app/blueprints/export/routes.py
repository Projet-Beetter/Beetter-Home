import csv
import io
from datetime import datetime, timezone
from flask import render_template, request, Response, flash, redirect, url_for, session
from flask_login import login_required
from ...models import db, Beehive
from ...i18n import get_text

def _t(key):
    return get_text(key, session.get('lang', 'en'))
from ..utils.influxdb import query_export_data, MEASUREMENTS, RANGE_OPTIONS
from . import export_bp

FIELD_CATEGORIES = [
    {
        'label': 'Interior',
        'collapsible': False,
        'fields': [
            ('temperature_int', 'Temperature',    '°C'),
            ('humidity_int',    'Humidity',        '%'),
            ('sound_freq_int',  'Sound Frequency', 'Hz'),
            ('sound_amp_int',   'Sound Amplitude', ''),
        ],
    },
    {
        'label': 'Exterior',
        'collapsible': False,
        'fields': [
            ('temperature_ext', 'Temperature',    '°C'),
            ('humidity_ext',    'Humidity',        '%'),
            ('sound_freq_ext',  'Sound Frequency', 'Hz'),
            ('sound_amp_ext',   'Sound Amplitude', ''),
            ('light_ext',       'Light Level',     '/10'),
        ],
    },
    {
        'label': 'MFCC Interior',
        'collapsible': True,
        'fields': [(f'mfcc_int_{i}', f'MFCC Int C{i}', '') for i in range(13)],
    },
    {
        'label': 'MFCC Exterior',
        'collapsible': True,
        'fields': [(f'mfcc_ext_{i}', f'MFCC Ext C{i}', '') for i in range(13)],
    },
]

RANGE_LABELS = {
    '1h':  'Last hour',
    '6h':  'Last 6 hours',
    '24h': 'Last 24 hours',
    '7d':  'Last 7 days',
    '30d': 'Last 30 days',
}


@export_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()

    if request.method == 'POST':
        selected_hive_ids = request.form.getlist('beehive_ids')
        selected_fields   = request.form.getlist('fields')
        use_custom        = request.form.get('use_custom')

        if not selected_hive_ids:
            flash(_t('flash_export_no_hive'), 'warning')
            return redirect(url_for('export.index'))
        if not selected_fields:
            flash(_t('flash_export_no_field'), 'warning')
            return redirect(url_for('export.index'))

        valid_fields = [f for f in selected_fields if f in MEASUREMENTS]
        if not valid_fields:
            flash(_t('flash_export_invalid_fields'), 'warning')
            return redirect(url_for('export.index'))

        if use_custom:
            try:
                date_from = datetime.strptime(request.form.get('date_from', ''), '%Y-%m-%dT%H:%M')
                date_to   = datetime.strptime(request.form.get('date_to',   ''), '%Y-%m-%dT%H:%M')
                start_str = date_from.strftime('%Y-%m-%dT%H:%M:%SZ')
                stop_str  = date_to.strftime('%Y-%m-%dT%H:%M:%SZ')
            except ValueError:
                flash(_t('flash_export_invalid_dates'), 'warning')
                return redirect(url_for('export.index'))
        else:
            preset = request.form.get('range_preset', '24h')
            if preset not in RANGE_OPTIONS:
                preset = '24h'
            start_str = f'-{preset}'
            stop_str  = None

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['timestamp', 'beehive'] + valid_fields)

        for hive_id_str in selected_hive_ids:
            hive = db.session.get(Beehive, hive_id_str.upper())
            if not hive:
                continue
            try:
                rows = query_export_data(str(hive.id), valid_fields, start_str, stop_str)
            except Exception:
                flash(f'Could not fetch data for "{hive.name}". Check InfluxDB connection.', 'warning')
                continue
            for row in rows:
                writer.writerow(
                    [row['timestamp'], hive.name] + [row.get(f, '') for f in valid_fields]
                )

        output.seek(0)
        filename = f'beetter_export_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}.csv'
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'},
        )

    return render_template(
        'export/index.html',
        beehives=beehives,
        field_categories=FIELD_CATEGORIES,
        range_options=RANGE_OPTIONS,
        range_labels=RANGE_LABELS,
    )
