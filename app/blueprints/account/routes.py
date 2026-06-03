from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from ...models import db, User, UserHiveIndicator, Alert, user_alert_reads
from .forms import ChangeEmailForm, ChangePasswordForm, DeleteAccountForm, AdminUserActionForm
from . import account_bp


@account_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    email_form = ChangeEmailForm(prefix='email')
    password_form = ChangePasswordForm(prefix='password')
    delete_form = DeleteAccountForm(prefix='delete')
    admin_action_form = AdminUserActionForm(prefix='admin')
    managed_users = []

    if current_user.is_admin:
        managed_users = User.query.filter(
            User.id != current_user.id,
            User.role != 'admin'
        ).order_by(User.role.asc(), User.username.asc()).all()

    # Handle email change
    if email_form.submit.data and email_form.validate_on_submit():
        if not current_user.check_password(email_form.password.data):
            flash('Invalid password.', 'danger')
        else:
            current_user.email = email_form.email.data
            db.session.commit()
            flash('Email updated successfully!', 'success')
            return redirect(url_for('account.index'))

    # Handle password change
    if password_form.submit.data and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            flash('Current password is incorrect.', 'danger')
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash('Password changed successfully!', 'success')
            return redirect(url_for('account.index'))

    # Handle account deletion
    if delete_form.submit.data and delete_form.validate_on_submit():
        if not current_user.check_password(delete_form.password.data):
            flash('Invalid password.', 'danger')
        else:
            db.session.delete(current_user)
            db.session.commit()
            flash('Account deleted successfully.', 'success')
            return redirect(url_for('auth.login'))

    # Handle admin user management actions
    if admin_action_form.validate_on_submit() and current_user.is_admin:
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
            # Remove user's own alert-read records
            db.session.execute(
                user_alert_reads.delete().where(user_alert_reads.c.user_id == target_user.id)
            )
            # Remove user's indicator preferences
            UserHiveIndicator.query.filter_by(user_id=target_user.id).delete()
            # For each beehive this user owns, clean up alerts and related data
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
        return redirect(url_for('account.index'))

    return render_template(
        'account/index.html',
        email_form=email_form,
        password_form=password_form,
        delete_form=delete_form,
        admin_action_form=admin_action_form,
        managed_users=managed_users
    )
