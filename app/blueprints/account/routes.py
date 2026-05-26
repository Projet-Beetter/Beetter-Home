from flask import render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from ...models import db, User
from .forms import ChangeEmailForm, ChangePasswordForm, DeleteAccountForm
from . import account_bp


@account_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    email_form = ChangeEmailForm()
    password_form = ChangePasswordForm()
    delete_form = DeleteAccountForm()

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
            user_id = current_user.id
            db.session.delete(current_user)
            db.session.commit()
            flash('Account deleted successfully.', 'success')
            return redirect(url_for('auth.login'))

    return render_template(
        'account/index.html',
        email_form=email_form,
        password_form=password_form,
        delete_form=delete_form
    )
