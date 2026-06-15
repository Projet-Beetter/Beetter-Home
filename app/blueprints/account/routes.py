from flask import render_template, redirect, url_for, flash, session
from flask_login import login_required, logout_user, current_user
from ...models import db
from ...i18n import get_text
from .forms import ChangeEmailForm, ChangePasswordForm, DeleteAccountForm
from . import account_bp

def _t(key):
    return get_text(key, session.get('lang', 'en'))


@account_bp.route('/', methods=['GET', 'POST'])
@login_required
def index():
    email_form = ChangeEmailForm(prefix='email')
    password_form = ChangePasswordForm(prefix='password')
    delete_form = DeleteAccountForm(prefix='delete')

    # Handle email change
    if email_form.submit.data and email_form.validate_on_submit():
        if not current_user.check_password(email_form.password.data):
            flash(_t('flash_invalid_password'), 'danger')
        else:
            current_user.email = email_form.email.data
            db.session.commit()
            flash(_t('flash_email_updated'), 'success')
            return redirect(url_for('account.index'))

    # Handle password change
    if password_form.submit.data and password_form.validate_on_submit():
        if not current_user.check_password(password_form.current_password.data):
            flash(_t('flash_wrong_password'), 'danger')
        else:
            current_user.set_password(password_form.new_password.data)
            db.session.commit()
            flash(_t('flash_password_changed'), 'success')
            return redirect(url_for('account.index'))

    # Handle account deletion
    if delete_form.submit.data and delete_form.validate_on_submit():
        if not current_user.check_password(delete_form.password.data):
            flash(_t('flash_invalid_password'), 'danger')
        else:
            db.session.delete(current_user)
            db.session.commit()
            logout_user()
            flash(_t('flash_account_deleted'), 'success')
            return redirect(url_for('auth.login'))

    return render_template(
        'account/index.html',
        email_form=email_form,
        password_form=password_form,
        delete_form=delete_form,
    )
