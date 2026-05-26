from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from ...models import db, RemoteServerConfig
from .forms import RemoteServerForm
from . import settings_bp


@settings_bp.route('/')
@login_required
def index():
    configs = RemoteServerConfig.query.filter_by(user_id=current_user.id).order_by(RemoteServerConfig.created_at).all()
    return render_template('settings/index.html', configs=configs)


@settings_bp.route('/remote/new', methods=['GET', 'POST'])
@login_required
def remote_new():
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
        return redirect(url_for('settings.index'))
    return render_template('settings/remote_form.html', form=form, title='Add remote server')


@settings_bp.route('/remote/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
def remote_edit(config_id):
    config = RemoteServerConfig.query.filter_by(id=config_id, user_id=current_user.id).first_or_404()
    form = RemoteServerForm(obj=config)
    if form.validate_on_submit():
        config.name = form.name.data
        config.url = form.url.data
        config.api_key = form.api_key.data
        config.push_interval = form.push_interval.data
        db.session.commit()
        flash(f'Remote server "{config.name}" updated.', 'success')
        return redirect(url_for('settings.index'))
    return render_template('settings/remote_form.html', form=form, title='Edit remote server', config=config)


@settings_bp.route('/remote/<int:config_id>/delete', methods=['POST'])
@login_required
def remote_delete(config_id):
    config = RemoteServerConfig.query.filter_by(id=config_id, user_id=current_user.id).first_or_404()
    name = config.name
    db.session.delete(config)
    db.session.commit()
    flash(f'Remote server "{name}" removed.', 'info')
    return redirect(url_for('settings.index'))


@settings_bp.route('/remote/<int:config_id>/toggle', methods=['POST'])
@login_required
def remote_toggle(config_id):
    config = RemoteServerConfig.query.filter_by(id=config_id, user_id=current_user.id).first_or_404()
    config.enabled = not config.enabled
    db.session.commit()
    state = 'enabled' if config.enabled else 'disabled'
    flash(f'Remote server "{config.name}" {state}.', 'success')
    return redirect(url_for('settings.index'))
