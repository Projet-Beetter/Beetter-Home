from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from ...models import db, Beehive, Alert
from ..utils.influxdb import query_chart_data, query_latest_values, RANGE_OPTIONS
from ..utils.decorators import editor_required
from ..utils.status import STATUS_CONFIG
from .forms import BeehiveForm
from . import beehives_bp
from ..utils.geocode import geocode

@beehives_bp.route('/')
@login_required
def index():
    beehives = Beehive.query.order_by(Beehive.created_at).all()
    return render_template('beehives/index.html', beehives=beehives, status_config=STATUS_CONFIG)


@beehives_bp.route('/new', methods=['GET', 'POST'])
@login_required
@editor_required
def new():
    form = BeehiveForm()
    if form.validate_on_submit():
        hive = Beehive(
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
        hive.latitude, hive.longitude = geocode(hive.street, hive.city, hive.postal_code)
        db.session.add(hive)
        db.session.commit()
        flash(f'Beehive "{hive.name}" added.', 'success')
        return redirect(url_for('beehives.index'))
    return render_template('beehives/form.html', form=form, title='Add beehive')


@beehives_bp.route('/<int:hive_id>/edit', methods=['GET', 'POST'])
@login_required
@editor_required
def edit(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    form = BeehiveForm(obj=hive)
    if form.validate_on_submit():
        form.populate_obj(hive)
        hive.latitude, hive.longitude = geocode(hive.street, hive.city, hive.postal_code)
        db.session.commit()
        flash(f'Beehive "{hive.name}" updated.', 'success')
        return redirect(url_for('beehives.index'))
    return render_template('beehives/form.html', form=form, title='Edit beehive', hive=hive)


@beehives_bp.route('/<int:hive_id>/delete', methods=['POST'])
@login_required
@editor_required
def delete(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    name = hive.name
    db.session.delete(hive)
    db.session.commit()
    flash(f'Beehive "{name}" deleted.', 'info')
    return redirect(url_for('beehives.index'))


@beehives_bp.route('/<int:hive_id>/toggle', methods=['POST'])
@login_required
@editor_required
def toggle(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    hive.enabled = not hive.enabled
    db.session.commit()
    state = 'enabled' if hive.enabled else 'disabled'
    flash(f'Beehive "{hive.name}" {state}.', 'success')
    return redirect(url_for('beehives.index'))


@beehives_bp.route('/<int:hive_id>')
@login_required
def detail(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
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
            flash('Could not reach InfluxDB. Check your connection.', 'warning')
    return render_template(
    'beehives/detail.html',
    hive=hive,
    chart_data=chart_data,
    latest=latest,
    range_str=range_str,
    range_options=RANGE_OPTIONS,
    status_config=STATUS_CONFIG,
    )

@beehives_bp.route('/<int:hive_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(hive_id):
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    if hive in current_user.favorite_hives:
        current_user.favorite_hives.remove(hive)
    else:
        current_user.favorite_hives.append(hive)
    db.session.commit()
    return redirect(request.referrer or url_for('beehives.index'))

@beehives_bp.route('/<int:hive_id>/status', methods=['POST'])
@login_required
def set_status(hive_id):
    if not current_user.is_admin:
        abort(403)
    hive = Beehive.query.filter_by(id=hive_id).first_or_404()
    new_status = request.form.get('status')
    if new_status in ('calm', 'stressed', 'agitated', 'critical', 'silent', 'no_data',
                      'swarming', 'queenless', 'predator', 'ventilating', 'virgin_queen'):
        if new_status != hive.status:
            db.session.add(Alert(hive_id=hive.id, old_status=hive.status, new_status=new_status, source='manual'))
            hive.status = new_status
            db.session.commit()
            flash(f'Status updated to {new_status}.', 'success')
    return redirect(request.referrer or url_for('beehives.index'))

