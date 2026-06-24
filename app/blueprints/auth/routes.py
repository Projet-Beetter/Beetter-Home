import jwt
import requests as http_requests
from flask import render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from ...models import db, User, SystemConfig
from ...i18n import get_text
from .forms import LoginForm, RegisterForm
from . import auth_bp

def _t(key):
    return get_text(key, session.get('lang', 'en'))


def _try_remote_login(username, password, remember):
    """Try to authenticate against the linked server/ instance using JWT.

    If credentials are valid:
    - Verifies the JWT signature locally (offline-safe after first success).
    - Creates or updates the local User record.
    - Logs the user in via Flask-Login.

    Returns True on success, False otherwise.
    """
    linked_url = SystemConfig.get('linked_server_url', '').rstrip('/')
    linked_secret = SystemConfig.get('linked_server_jwt_secret', '')
    if not linked_url or not linked_secret:
        return False

    try:
        resp = http_requests.post(
            f"{linked_url}/api/auth/verify",
            json={'username': username, 'password': password},
            timeout=5,
        )
    except Exception:
        return False

    if not resp.ok:
        return False

    data = resp.json()
    if not data.get('valid'):
        return False

    # Verify JWT signature — ensures the server response wasn't tampered with.
    try:
        payload = jwt.decode(data['token'], linked_secret, algorithms=['HS256'])
    except jwt.PyJWTError:
        return False

    remote_username = payload.get('sub', username)
    remote_role = payload.get('role', 'viewer')

    user = User.query.filter_by(username=remote_username).first()
    if not user:
        # First remote login: create a local account.
        # Use a placeholder email; the user can update it later.
        placeholder_email = f"{remote_username}@remote.local"
        # Avoid duplicate placeholder emails if username differs slightly.
        if User.query.filter_by(email=placeholder_email).first():
            placeholder_email = f"{remote_username}.remote@remote.local"
        user = User(
            username=remote_username,
            email=placeholder_email,
            role=remote_role,
        )
        db.session.add(user)
    else:
        # Refresh role in case it changed on server/.
        user.role = remote_role

    # Cache the remote password locally so offline logins work from now on.
    user.set_password(password)
    db.session.commit()

    login_user(user, remember=remember)
    return True


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        # Local authentication (always works, including offline).
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            if next_page and (next_page.startswith('/') and not next_page.startswith('//')):
                return redirect(next_page)
            return redirect(url_for('dashboard.index'))

        # If user not found locally, try the linked remote server (online only).
        if not user:
            if _try_remote_login(form.username.data, form.password.data, form.remember.data):
                next_page = request.args.get('next')
                if next_page and (next_page.startswith('/') and not next_page.startswith('//')):
                    return redirect(next_page)
                return redirect(url_for('dashboard.index'))

        flash(_t('flash_invalid_credentials'), 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    form = RegisterForm()
    if form.validate_on_submit():
        is_first = User.query.count() == 0
        user = User(
            username=form.username.data,
            email=form.email.data,
            role='admin' if is_first else 'viewer',
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash(_t('flash_registered'), 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
