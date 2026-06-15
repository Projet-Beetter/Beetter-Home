from flask import render_template, request, jsonify, abort, url_for
from flask_login import login_required, current_user
from datetime import datetime
from ...models import db, HiveEvent, Beehive
from . import calendar_bp

EVENT_TYPES = {
    "inspection": {"label": "Inspection", "color": "#378ADD"},
    "treatment":  {"label": "Treatment",  "color": "#E24B4A"},
    "harvest":    {"label": "Harvest",    "color": "#F5CB5C"},
    "swarm":      {"label": "Swarm",      "color": "#639922"},
    "other":      {"label": "Other",      "color": "#9B8EA8"},
}


def can_write(user):
    return user.can_edit_data


def _parse_dt(value):
    if not value:
        return None
    value = value.strip()
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def _event_to_fc(event):
    return {
        "id": event.id,
        "title": event.title,
        "start": event.start_date.isoformat(),
        "end": event.end_date.isoformat() if event.end_date else None,
        "allDay": event.all_day,
        "color": EVENT_TYPES.get(event.event_type, EVENT_TYPES["other"])["color"],
        "extendedProps": {
            "type": event.event_type,
            "type_label": EVENT_TYPES.get(event.event_type, EVENT_TYPES["other"])["label"],
            "hive_id": event.hive_id,
            "hive_name": event.hive.name if event.hive else "Global",
            "notes": event.notes or "",
            "created_by": event.creator.username,
        },
    }


# ── Views ──────────────────────────────────────────────────────────────────

@calendar_bp.route('/')
@login_required
def index():
    hives = Beehive.query.order_by(Beehive.name).all()
    return render_template(
        'calendar/index.html',
        events_url=url_for('calendar.events_feed'),
        hives=hives,
        event_types=EVENT_TYPES,
        can_write=can_write(current_user),
        hive=None,
    )


@calendar_bp.route('/hive/<int:hive_id>')
@login_required
def hive_calendar(hive_id):
    hive = db.get_or_404(Beehive, hive_id)
    hives = Beehive.query.order_by(Beehive.name).all()
    return render_template(
        'calendar/index.html',
        events_url=url_for('calendar.hive_events_feed', hive_id=hive_id),
        hives=hives,
        event_types=EVENT_TYPES,
        can_write=can_write(current_user),
        hive=hive,
    )


# ── JSON feeds ─────────────────────────────────────────────────────────────

@calendar_bp.route('/events')
@login_required
def events_feed():
    events = HiveEvent.query.order_by(HiveEvent.start_date).all()
    return jsonify([_event_to_fc(e) for e in events])


@calendar_bp.route('/events/hive/<int:hive_id>')
@login_required
def hive_events_feed(hive_id):
    events = HiveEvent.query.filter(
        (HiveEvent.hive_id == hive_id) | (HiveEvent.hive_id.is_(None))
    ).order_by(HiveEvent.start_date).all()
    return jsonify([_event_to_fc(e) for e in events])


# ── CRUD ───────────────────────────────────────────────────────────────────

@calendar_bp.route('/events/create', methods=['POST'])
@login_required
def create_event():
    if not can_write(current_user):
        abort(403)
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Invalid JSON'}), 400

    event_type = data.get('event_type', 'other')
    if event_type not in EVENT_TYPES:
        return jsonify({'error': 'Invalid event type'}), 400

    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'Title is required'}), 400

    try:
        start = _parse_dt(data.get('start_date'))
        end   = _parse_dt(data.get('end_date'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if start is None:
        return jsonify({'error': 'start_date is required'}), 400

    raw_hive = data.get('hive_id')
    hive_id = int(raw_hive) if raw_hive else None

    event = HiveEvent(
        title=title,
        event_type=event_type,
        start_date=start,
        end_date=end,
        all_day=bool(data.get('all_day', True)),
        notes=data.get('notes', ''),
        hive_id=hive_id,
        created_by=current_user.id,
    )
    db.session.add(event)
    db.session.commit()
    return jsonify(_event_to_fc(event)), 201


@calendar_bp.route('/events/<int:event_id>/edit', methods=['PUT'])
@login_required
def edit_event(event_id):
    if not can_write(current_user):
        abort(403)
    event = db.get_or_404(HiveEvent, event_id)
    data = request.get_json(silent=True) or {}

    if 'title' in data:
        event.title = (data['title'] or '').strip() or event.title
    if 'event_type' in data and data['event_type'] in EVENT_TYPES:
        event.event_type = data['event_type']
    if 'start_date' in data:
        parsed = _parse_dt(data['start_date'])
        if parsed:
            event.start_date = parsed
    if 'end_date' in data:
        event.end_date = _parse_dt(data['end_date'])
    if 'all_day' in data:
        event.all_day = bool(data['all_day'])
    if 'notes' in data:
        event.notes = data['notes']
    if 'hive_id' in data:
        raw = data['hive_id']
        event.hive_id = int(raw) if raw else None

    db.session.commit()
    return jsonify(_event_to_fc(event))


@calendar_bp.route('/events/<int:event_id>/delete', methods=['DELETE'])
@login_required
def delete_event(event_id):
    if not can_write(current_user):
        abort(403)
    event = db.get_or_404(HiveEvent, event_id)
    db.session.delete(event)
    db.session.commit()
    return jsonify({'status': 'deleted'})
