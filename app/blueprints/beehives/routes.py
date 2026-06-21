from flask import render_template, redirect, url_for, flash, request, abort, session
from flask_login import login_required, current_user
from ...models import db, Beehive, Alert, UserHiveIndicator
from ...i18n import get_text
from ..utils.influxdb import query_chart_data, query_latest_values, RANGE_OPTIONS, delete_beehive_data
from ..utils.decorators import editor_required
from ..utils.status import STATUS_CONFIG
from ..utils.thresholds import THRESHOLDS, get_threshold_status
from .forms import BeehiveForm
from . import beehives_bp
from ..utils.geocode import geocode

def _t(key):
    return get_text(key, session.get('lang', 'en'))


_SEVERITY = {
    "swarming": "crit", "queenless": "crit", "predator": "crit", "critical": "crit",
    "stressed": "warn", "agitated": "warn", "virgin_queen": "warn", "silent": "warn",
    "foraging": "ok",   "calm": "ok",        "ventilating": "ok",
    "no_data":  "no_data",
}

@beehives_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()
    hive_metrics = {}
    for hive in beehives:
        latest = {}
        if hive.enabled:
            try:
                latest = query_latest_values(str(hive.id))
            except Exception:
                pass
        online = hive.enabled and bool(latest)
        hive_metrics[hive.id] = {
            "online":  online,
            "overall": _SEVERITY.get(hive.status, "no_data") if online else "no_data",
        }
    return render_template('beehives/index.html',
        beehives=beehives,
        status_config=STATUS_CONFIG,
        hive_metrics=hive_metrics,
    )


@beehives_bp.route('/new', methods=['GET', 'POST'])
@login_required
@editor_required
def new():
    form = BeehiveForm()
    if form.validate_on_submit():
        hive_id = form.hive_id.data.upper()
        if db.session.get(Beehive, hive_id):
            form.hive_id.errors.append('This ID is already taken.')
        else:
            hive = Beehive(
                id=hive_id,
                name=form.name.data,
                street=form.street.data,
                city=form.city.data,
                postal_code=form.postal_code.data,
                device_eui=form.device_eui.data,
                lora_frequency=form.lora_frequency.data or 868.0,
                spreading_factor=form.spreading_factor.data or 7,
                bandwidth=form.bandwidth.data or 125,
                user_id=current_user.id,
            )
            try:
                hive.latitude, hive.longitude = geocode(hive.street, hive.city, hive.postal_code)
            except Exception:
                pass
            db.session.add(hive)
            db.session.commit()
            flash(f'Beehive "{hive.name}" added.', 'success')
            return redirect(url_for('beehives.index'))
    return render_template('beehives/form.html', form=form, title='Add beehive')


@beehives_bp.route('/<string:hive_id>/edit', methods=['GET', 'POST'])
@login_required
@editor_required
def edit(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    form = BeehiveForm(obj=hive)
    if form.validate_on_submit():
        hive.name = form.name.data
        hive.street = form.street.data
        hive.city = form.city.data
        hive.postal_code = form.postal_code.data
        hive.device_eui = form.device_eui.data
        hive.lora_frequency = form.lora_frequency.data or 868.0
        hive.spreading_factor = form.spreading_factor.data or 7
        hive.bandwidth = form.bandwidth.data or 125
        if form.no_data_threshold_minutes.data is not None:
            hive.no_data_threshold_minutes = form.no_data_threshold_minutes.data
        try:
            hive.latitude, hive.longitude = geocode(hive.street, hive.city, hive.postal_code)
        except Exception:
            pass
        db.session.commit()
        flash(f'Beehive "{hive.name}" updated.', 'success')
        return redirect(url_for('beehives.index'))
    return render_template('beehives/form.html', form=form, title='Edit beehive', hive=hive)


@beehives_bp.route('/<string:hive_id>/delete', methods=['POST'])
@login_required
@editor_required
def delete(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    name = hive.name
    try:
        delete_beehive_data(str(hive_id))
    except Exception:
        flash(_t('flash_influxdb_purge_failed'), 'warning')
    db.session.delete(hive)
    db.session.commit()
    flash(f'Beehive "{name}" deleted.', 'info')
    return redirect(url_for('beehives.index'))


@beehives_bp.route('/<string:hive_id>/toggle', methods=['POST'])
@login_required
@editor_required
def toggle(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    hive.enabled = not hive.enabled
    db.session.commit()
    state = 'enabled' if hive.enabled else 'disabled'
    flash(f'Beehive "{hive.name}" {state}.', 'success')
    return redirect(url_for('beehives.index'))


@beehives_bp.route('/<string:hive_id>')
@login_required
def detail(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()

    # ── Prev / next navigation — same order as dashboard ─────────────
    all_hives = Beehive.query.order_by(Beehive.created_at).all()

    if len(all_hives) > 1:
        online_hives  = [h for h in all_hives if h.enabled and h.status != 'no_data']
        offline_hives = [h for h in all_hives if not (h.enabled and h.status != 'no_data')]
        ordered_hives = online_hives + offline_hives
    else:
        ordered_hives = all_hives

    hive_ids    = [h.id for h in ordered_hives]
    current_idx = hive_ids.index(hive.id) if hive.id in hive_ids else 0
    prev_hive   = ordered_hives[current_idx - 1] if current_idx > 0 else None
    next_hive   = ordered_hives[current_idx + 1] if current_idx < len(ordered_hives) - 1 else None

    range_str = request.args.get('range', '24h')
    if range_str not in RANGE_OPTIONS:
        range_str = '24h'

    chart_data = {}
    latest = {}
    if hive.enabled:
        try:
            chart_data = query_chart_data(str(hive.id), range_str)
            latest = query_latest_values(str(hive.id))
        except Exception:
            flash(_t('flash_influxdb_unreachable'), 'warning')

    online = hive.enabled and bool(latest)
    effective_status = hive.status if online else 'no_data'
    def _v(key):
        obj = latest.get(key)
        return obj['value'] if obj is not None else None

    metrics = [
        {"key": "temperature_int", "label": "Temp. int.",  "value": _v('temperature_int'), "unit": "°C",  "icon": "bi-thermometer-half",  "color": "#E24B4A"},
        {"key": "temperature_ext", "label": "Temp. ext.",  "value": _v('temperature_ext'), "unit": "°C",  "icon": "bi-thermometer-half",  "color": "#F4836B"},
        {"key": "humidity_int",    "label": "Hum. int.",   "value": _v('humidity_int'),    "unit": "%",   "icon": "bi-droplet-half",      "color": "#378ADD"},
        {"key": "humidity_ext",    "label": "Hum. ext.",   "value": _v('humidity_ext'),    "unit": "%",   "icon": "bi-droplet-half",      "color": "#85B7EB"},
        {"key": "sound_freq_int",  "label": "Frequency",   "value": _v('sound_freq_int'),  "unit": " Hz", "icon": "bi-music-note-beamed", "color": "#639922"},
        {"key": "light_ext",       "label": "Light",       "value": _v('light_ext'),       "unit": "/10", "icon": "bi-brightness-high",   "color": "#BA7517"},
    ]
    for m in metrics:
        m["status"] = get_threshold_status(m["key"], m["value"])

    return render_template(
    'beehives/detail.html',
    hive=hive,
    chart_data=chart_data,
    latest=latest,
    metrics=metrics,
    range_str=range_str,
    range_options=RANGE_OPTIONS,
    status_config=STATUS_CONFIG,
    selected_indicators = (lambda u: u.indicators.split(',') if u else ['temperature_int', 'humidity_int'])(UserHiveIndicator.query.filter_by(user_id=current_user.id, hive_id=hive.id).first()),
    prev_hive=prev_hive,
    next_hive=next_hive,
    hive_position=f"{current_idx + 1}/{len(ordered_hives)}",
    effective_status=effective_status,
    thresholds=THRESHOLDS,
    )


@beehives_bp.route('/<string:hive_id>/indicators/toggle', methods=['POST'])
@login_required
def toggle_indicator(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    sensor = request.form.get('sensor_key')
    section_key = request.form.get('section_key')
    if not sensor:
        return redirect(request.referrer or url_for('beehives.detail', hive_id=hive.id))

    # retrieve or create user-hive selection
    uhi = UserHiveIndicator.query.filter_by(user_id=current_user.id, hive_id=hive.id).first()
    if not uhi:
        uhi = UserHiveIndicator(user_id=current_user.id, hive_id=hive.id, indicators='temperature_int,humidity_int')
        db.session.add(uhi)

    current = [s for s in uhi.indicators.split(',') if s]
    if sensor in current:
        # remove, enforce minimum 1
        if len(current) > 1:
            current.remove(sensor)
        else:
            flash(_t('flash_indicator_min'), 'warning')
            return redirect(request.referrer or url_for('beehives.detail', hive_id=hive.id))
    else:
        # add, enforce maximum 6
        if len(current) >= 6:
            flash(_t('flash_indicator_max'), 'warning')
            return redirect(request.referrer or url_for('beehives.detail', hive_id=hive.id))
        current.append(sensor)

    uhi.indicators = ','.join(current)
    db.session.commit()
    if section_key:
        return redirect(url_for('beehives.detail', hive_id=hive.id, open=section_key))
    return redirect(request.referrer or url_for('beehives.detail', hive_id=hive.id))

@beehives_bp.route('/<string:hive_id>/status', methods=['POST'])
@login_required
def set_status(hive_id):
    if not current_user.is_admin:
        abort(403)
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    new_status = request.form.get('status')
    if new_status in STATUS_CONFIG:
        if new_status != hive.status:
            note = request.form.get('note', '').strip() or None
            db.session.add(Alert(
                hive_id=hive.id,
                old_status=hive.status,
                new_status=new_status,
                source='manual',
                note=note
            ))
            hive.status = new_status
            db.session.commit()
            flash(f'Status updated to {new_status}.', 'success')
    return redirect(request.referrer or url_for('beehives.index'))

