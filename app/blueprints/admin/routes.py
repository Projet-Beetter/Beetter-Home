from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from ...models import db, User, UserHiveIndicator, Alert, user_alert_reads, RemoteServerConfig
from .forms import AdminUserActionForm
from . import admin_bp


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
        target_user = User.query.get(int(admin_action_form.user_id.data or 0))
        if not target_user or target_user.id == current_user.id or target_user.is_admin:
            abort(403)

        if admin_action_form.action.data == 'change_role':
            new_role = request.form.get('admin-role')
            if new_role in ('viewer', 'editor', 'admin'):
                if new_role != target_user.role:
                    target_user.role = new_role
                    flash(f"{target_user.username} role updated to {new_role}.", 'success')
                else:
                    flash('No role change detected.', 'info')
            else:
                flash('Invalid role selected.', 'danger')
        elif admin_action_form.action.data == 'delete_user':
            db.session.execute(
                user_alert_reads.delete().where(user_alert_reads.c.user_id == target_user.id)
            )
            UserHiveIndicator.query.filter_by(user_id=target_user.id).delete()
            for hive in target_user.beehives:
                UserHiveIndicator.query.filter_by(hive_id=hive.id).delete()
                for alert in hive.alerts:
                    db.session.execute(
                        user_alert_reads.delete().where(user_alert_reads.c.alert_id == alert.id)
                    )
                Alert.query.filter_by(hive_id=hive.id).delete()
            db.session.delete(target_user)
            flash(f"{target_user.username} has been removed.", 'success')
        else:
            flash('Unknown admin action.', 'danger')

        db.session.commit()
        return redirect(url_for('admin.index'))

    return render_template(
        'admin/index.html',
        admin_action_form=admin_action_form,
        managed_users=managed_users,
        configs=configs,
    )
