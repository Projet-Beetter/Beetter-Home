from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user
from ...models import db, User
from . import setup_bp


@setup_bp.route('/', methods=['GET'])
def index():
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))
    return render_template('setup/index.html')


@setup_bp.route('/create', methods=['POST'])
def create():
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))

    username = request.form.get('username', '').strip()
    email    = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    confirm  = request.form.get('confirm', '')

    errors = []
    if not username or len(username) < 3:
        errors.append('Username must be at least 3 characters.')
    if not email or '@' not in email:
        errors.append('A valid email is required.')
    if not password or len(password) < 8:
        errors.append('Password must be at least 8 characters.')
    if password != confirm:
        errors.append('Passwords do not match.')

    if errors:
        for e in errors:
            flash(e, 'danger')
        return render_template('setup/index.html', username=username, email=email)

    user = User(username=username, email=email, role='admin')
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    flash('Welcome to Beetter! Your admin account has been created.', 'success')
    return redirect(url_for('setup.done'))


@setup_bp.route('/done')
def done():
    if User.query.count() == 0:
        return redirect(url_for('setup.index'))
    return render_template('setup/done.html')
