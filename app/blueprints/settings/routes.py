from flask import render_template, redirect, url_for, flash, request, session, abort
from flask_login import login_required, current_user
from ...models import db, RemoteServerConfig, UserPreferences
from .forms import RemoteServerForm
from . import settings_bp


@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def index():
    prefs = current_user.prefs
    if request.method == 'POST':
        prefs.language    = request.form.get('language', 'en')
        prefs.time_format = request.form.get('time_format', '24h')
        prefs.week_start  = request.form.get('week_start', 'monday')
        prefs.temp_unit   = request.form.get('temp_unit', 'C')

        prefs.email_alerts      = 'email_alerts'      in request.form
        prefs.alert_temperature = 'alert_temperature' in request.form
        prefs.alert_humidity    = 'alert_humidity'    in request.form
        prefs.alert_sound       = 'alert_sound'       in request.form
        prefs.alert_offline     = 'alert_offline'     in request.form

        prefs.high_contrast = 'high_contrast' in request.form
        prefs.large_text    = 'large_text'    in request.form
        prefs.reduce_motion = 'reduce_motion' in request.form

        db.session.commit()

        session['lang']      = prefs.language
        session['temp_unit'] = prefs.temp_unit

        flash('Preferences saved.', 'success')
        return redirect(url_for('settings.index'))

    return render_template('settings/index.html', prefs=prefs)


@settings_bp.route('/remote/new', methods=['GET', 'POST'])
@login_required
def remote_new():
    if not current_user.is_admin:
        abort(403)
    form = RemoteServerForm()
    if form.validate_on_submit():
        config = RemoteServerConfig(
            name=form.name.data,
            url=form.url.data,
            api_key=form.api_key.data,
            push_interval=form.push_interval.data,
            user_id=current_user.id,
        )
        db.session.add(config)
        db.session.commit()
        flash(f'Remote server "{config.name}" added.', 'success')
        return redirect(url_for('admin.index'))
    return render_template('settings/remote_form.html', form=form, title='Add remote server')


@settings_bp.route('/remote/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
def remote_edit(config_id):
    if not current_user.is_admin:
        abort(403)
    config = RemoteServerConfig.query.filter_by(id=config_id).first_or_404()
    form = RemoteServerForm(obj=config)
    if form.validate_on_submit():
        config.name = form.name.data
        config.url = form.url.data
        config.api_key = form.api_key.data
        config.push_interval = form.push_interval.data
        db.session.commit()
        flash(f'Remote server "{config.name}" updated.', 'success')
        return redirect(url_for('admin.index'))
    return render_template('settings/remote_form.html', form=form, title='Edit remote server', config=config)


@settings_bp.route('/remote/<int:config_id>/delete', methods=['POST'])
@login_required
def remote_delete(config_id):
    if not current_user.is_admin:
        abort(403)
    config = RemoteServerConfig.query.filter_by(id=config_id).first_or_404()
    name = config.name
    db.session.delete(config)
    db.session.commit()
    flash(f'Remote server "{name}" removed.', 'info')
    return redirect(url_for('admin.index'))


@settings_bp.route('/remote/<int:config_id>/toggle', methods=['POST'])
@login_required
def remote_toggle(config_id):
    if not current_user.is_admin:
        abort(403)
    config = RemoteServerConfig.query.filter_by(id=config_id).first_or_404()
    config.enabled = not config.enabled
    db.session.commit()
    state = 'enabled' if config.enabled else 'disabled'
    flash(f'Remote server "{config.name}" {state}.', 'success')
    return redirect(url_for('admin.index'))
