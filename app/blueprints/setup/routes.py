import re
from flask import render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user
from ...models import db, User, Beehive
from ..utils.geocode import geocode
from . import setup_bp


@setup_bp.route('/', methods=['GET'])
def index():
    # if User.query.count() > 0:
    #     return redirect(url_for('auth.login'))
    return render_template('setup/index.html')


@setup_bp.route('/create', methods=['POST'])
def create():
    # if User.query.count() > 0:
    #     return redirect(url_for('auth.login'))

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
    return redirect(url_for('setup.create_hive'))


@setup_bp.route('/hive', methods=['GET', 'POST'])
def create_hive():
    if User.query.count() == 0:
        return redirect(url_for('setup.index'))
    if request.method == 'POST':
        if 'skip' in request.form:
            return redirect(url_for('setup.done'))

        hive_id   = request.form.get('hive_id', '').strip()
        hive_name = request.form.get('hive_name', '').strip()
        city      = request.form.get('city', '').strip()

        hive_id = hive_id.upper()
        errors = []
        if not re.match(r'^[A-Z0-9]{4}$', hive_id):
            errors.append('Hive ID must be exactly 4 letters/digits (e.g. A1B2).')
        elif db.session.get(Beehive, hive_id):
            errors.append(f'A hive with ID {hive_id} already exists.')
        if not hive_name:
            errors.append('Hive name is required.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('setup/hive.html',
                                   hive_id=hive_id,
                                   hive_name=hive_name,
                                   city=city)

        lat, lng = None, None
        if city:
            try:
                lat, lng = geocode(None, city, None)
            except Exception:
                pass

        hive = Beehive(
            id=hive_id,
            name=hive_name,
            city=city or None,
            latitude=lat,
            longitude=lng,
            user_id=current_user.id,
        )
        db.session.add(hive)
        db.session.commit()
        flash(f'Hive "{hive_name}" created with ID {hive_id}.', 'success')
        return redirect(url_for('setup.done'))

    return render_template('setup/hive.html')


@setup_bp.route('/done')
def done():
    if User.query.count() == 0:
        return redirect(url_for('setup.index'))
    return render_template('setup/done.html')
