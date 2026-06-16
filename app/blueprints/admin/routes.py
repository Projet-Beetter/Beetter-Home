from flask import render_template, redirect, url_for, flash, request, abort, session
from flask_login import login_required, current_user, logout_user
from ...models import db, User, Beehive, UserHiveIndicator, Alert, user_alert_reads, RemoteServerConfig, HiveEvent, UserPreferences
from ..utils.influxdb import delete_beehive_data, delete_all_influx_data
from ...i18n import get_text
from .forms import AdminUserActionForm
from . import admin_bp

def _t(key):
    return get_text(key, session.get('lang', 'en'))


@admin_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    if not current_user.is_admin:
        abort(403)

    admin_action_form = AdminUserActionForm(prefix='admin')
    managed_users = User.query.filter(
        User.id != current_user.id,
        User.role != 'admin'
    ).order_by(User.role.asc(), User.username.asc()).all()
    configs = RemoteServerConfig.query.order_by(RemoteServerConfig.created_at).all()

    if admin_action_form.validate_on_submit():
        target_user = db.session.get(User, int(admin_action_form.user_id.data or 0))
        if not target_user or target_user.id == current_user.id or target_user.is_admin:
            abort(403)

        if admin_action_form.action.data == 'change_role':
            new_role = request.form.get('admin-role')
            if new_role in ('viewer', 'editor', 'admin'):
                if new_role != target_user.role:
                    target_user.role = new_role
                    flash(f"{target_user.username} role updated to {new_role}.", 'success')
                else:
                    flash(_t('flash_admin_no_change'), 'info')
            else:
                flash(_t('flash_admin_invalid_role'), 'danger')
        elif admin_action_form.action.data == 'delete_user':
            db.session.execute(
                user_alert_reads.delete().where(user_alert_reads.c.user_id == target_user.id)
            )
            UserHiveIndicator.query.filter_by(user_id=target_user.id).delete()
            HiveEvent.query.filter_by(created_by=target_user.id).delete()
            for hive in target_user.beehives:
                UserHiveIndicator.query.filter_by(hive_id=hive.id).delete()
                for alert in hive.alerts:
                    db.session.execute(
                        user_alert_reads.delete().where(user_alert_reads.c.alert_id == alert.id)
                    )
                Alert.query.filter_by(hive_id=hive.id).delete()
            UserPreferences.query.filter_by(user_id=target_user.id).delete()
            db.session.delete(target_user)
            flash(f"{target_user.username} has been removed.", 'success')
        else:
            flash(_t('flash_admin_unknown_action'), 'danger')

        db.session.commit()
        return redirect(url_for('admin.index'))

    return render_template(
        'admin/index.html',
        admin_action_form=admin_action_form,
        managed_users=managed_users,
        configs=configs,
    )


@admin_bp.route('/delete-self', methods=['POST'])
@login_required
def delete_self():
    if not current_user.is_admin:
        abort(403)
    password = request.form.get('password', '')
    if not current_user.check_password(password):
        flash(_t('flash_wrong_password'), 'danger')
        return redirect(url_for('admin.index'))

    user = current_user._get_current_object()
    db.session.execute(
        user_alert_reads.delete().where(user_alert_reads.c.user_id == user.id)
    )
    UserHiveIndicator.query.filter_by(user_id=user.id).delete()
    HiveEvent.query.filter_by(created_by=user.id).delete()
    for hive in user.beehives:
        UserHiveIndicator.query.filter_by(hive_id=hive.id).delete()
        for alert in hive.alerts:
            db.session.execute(
                user_alert_reads.delete().where(user_alert_reads.c.alert_id == alert.id)
            )
        Alert.query.filter_by(hive_id=hive.id).delete()
    UserPreferences.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    logout_user()
    flash(_t('flash_account_deleted'), 'info')
    return redirect(url_for('setup.index'))


@admin_bp.route('/delete-all-users', methods=['POST'])
@login_required
def delete_all_users():
    if not current_user.is_admin:
        abort(403)
    if request.form.get('confirm_text', '').strip().upper() not in ('DELETE', 'SUPPRIMER'):
        flash(_t('flash_wrong_password'), 'danger')
        return redirect(url_for('admin.index'))

    non_admin_users = User.query.filter(User.id != current_user.id, User.role != 'admin').all()
    for user in non_admin_users:
        db.session.execute(user_alert_reads.delete().where(user_alert_reads.c.user_id == user.id))
        UserHiveIndicator.query.filter_by(user_id=user.id).delete()
        HiveEvent.query.filter_by(created_by=user.id).delete()
        for hive in user.beehives:
            UserHiveIndicator.query.filter_by(hive_id=hive.id).delete()
            for alert in hive.alerts:
                db.session.execute(user_alert_reads.delete().where(user_alert_reads.c.alert_id == alert.id))
            Alert.query.filter_by(hive_id=hive.id).delete()
            try:
                delete_beehive_data(hive.id)
            except Exception:
                pass
        UserPreferences.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
    db.session.commit()
    flash(_t('flash_all_users_deleted'), 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/delete-all-data', methods=['POST'])
@login_required
def delete_all_data():
    if not current_user.is_admin:
        abort(403)
    if request.form.get('confirm_text', '').strip().upper() not in ('DELETE', 'SUPPRIMER'):
        flash(_t('flash_wrong_password'), 'danger')
        return redirect(url_for('admin.index'))

    db.session.execute(user_alert_reads.delete())
    Alert.query.delete()
    HiveEvent.query.delete()
    Beehive.query.update({'status': 'no_data'})
    db.session.commit()
    try:
        delete_all_influx_data()
    except Exception as e:
        flash(f"Postgres data cleared; InfluxDB error: {e}", 'warning')
        return redirect(url_for('admin.index'))
    flash(_t('flash_all_data_deleted'), 'success')
    return redirect(url_for('admin.index'))


@admin_bp.route('/delete-all-beehives', methods=['POST'])
@login_required
def delete_all_beehives():
    if not current_user.is_admin:
        abort(403)
    if request.form.get('confirm_text', '').strip().upper() not in ('DELETE', 'SUPPRIMER'):
        flash(_t('flash_wrong_password'), 'danger')
        return redirect(url_for('admin.index'))

    beehives = Beehive.query.all()
    for hive in beehives:
        for alert in hive.alerts:
            db.session.execute(user_alert_reads.delete().where(user_alert_reads.c.alert_id == alert.id))
        Alert.query.filter_by(hive_id=hive.id).delete()
        HiveEvent.query.filter_by(hive_id=hive.id).delete()
        UserHiveIndicator.query.filter_by(hive_id=hive.id).delete()
        try:
            delete_beehive_data(hive.id)
        except Exception:
            pass
    Beehive.query.delete()
    db.session.commit()
    flash(_t('flash_all_beehives_deleted'), 'success')
    return redirect(url_for('admin.index'))
