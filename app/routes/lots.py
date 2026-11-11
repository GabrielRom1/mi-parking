import unicodedata

from flask import Blueprint, jsonify, render_template, session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.database import db
from app.decorators import role_required
from app.forms.lot_form import LotForm
from app.models import Lots, Role, Spots, User

lots_bp = Blueprint('lots', __name__)


def _sort_key(name):
    """Case- and accent-insensitive. lots.js compares these same keys when inserting a row."""
    decomposed = unicodedata.normalize('NFD', name.casefold())
    return ''.join(char for char in decomposed if not unicodedata.combining(char))


def _role_label(role):
    return role.name.title()


def _role_choices():
    """(value, label) options for a floor's role, starting with no role. Admins can already reserve anywhere."""
    roles = Role.query.filter(Role.name != 'admin').order_by(Role.id).all()
    return [('', 'Sin rol')] + [(role.id, _role_label(role)) for role in roles]


def _lot_summary(lot, spot_counts):
    floors = lot.floors
    spots = accessible = 0
    for lot_id in [lot.id, *(floor.id for floor in floors)]:
        total, accessible_total = spot_counts.get(lot_id, (0, 0))
        spots += total
        accessible += accessible_total

    roles = sorted({floor.role for floor in floors if floor.role}, key=lambda r: r.id)
    return {
        'id': lot.id,
        'name': lot.name,
        'sort_key': _sort_key(lot.name),
        'location': lot.location,
        'is_paid': bool(lot.is_paid),
        'floors': len(floors),
        'spots': spots,
        'accessible': accessible,
        'roles': [_role_label(role) for role in roles],
    }


def _spot_counts(lot_ids):
    if not lot_ids:
        return {}
    accessible_count = db.func.sum(db.case((Spots.is_accessible.is_(True), 1), else_=0))
    rows = (
        db.session.query(Spots.lot_id, db.func.count(Spots.id), accessible_count)
        .filter(Spots.lot_id.in_(lot_ids))
        .group_by(Spots.lot_id)
        .all()
    )
    return {lot_id: (total, accessible or 0) for lot_id, total, accessible in rows}


def _lot_summaries(lots):
    lot_ids = [lot.id for lot in lots] + [floor.id for lot in lots for floor in lot.floors]
    spot_counts = _spot_counts(lot_ids)
    return [_lot_summary(lot, spot_counts) for lot in lots]


def _plural(count, word):
    return f"{count} {word}{'' if count == 1 else 's'}"


def _validation_message(errors):
    if 'csrf_token' in errors:
        return 'Tu sesión expiró. Recarga la página e inténtalo de nuevo.'
    if errors.get('name', '').startswith('Ya existe'):
        return errors['name']
    if len(errors) == 1:
        return 'Corrige el campo marcado e inténtalo de nuevo.'
    return f'Corrige los {len(errors)} campos marcados e inténtalo de nuevo.'


def _created_message(summary):
    name = summary['name']
    if not summary['floors']:
        return f'{name} se creó como un lote vacío.'
    floors = _plural(summary['floors'], 'piso')
    spots = _plural(summary['spots'], 'espacio')
    return f'{name} se creó con {floors} y {spots}.'


@lots_bp.route('/', methods=['GET'])
@role_required('admin')
def index():
    user = db.session.get(User, session['user_id'])
    form = LotForm()
    return render_template(
        'lots/index.html',
        user=user,
        form=form,
        role_options=_role_choices(),
    )


@lots_bp.route('/rows', methods=['GET'])
@role_required('admin')
def rows():
    lots = (
        Lots.query.options(selectinload(Lots.floors).selectinload(Lots.role))
        .filter(Lots.parent_id.is_(None))
        .all()
    )
    lots.sort(key=lambda lot: _sort_key(lot.name))
    return render_template('lots/include/rows.html', lots=_lot_summaries(lots))


@lots_bp.route('/', methods=['POST'])
@role_required('admin')
def create():
    form = LotForm(role_choices=_role_choices())

    if not form.validate():
        errors = form.field_errors()
        return jsonify(errors=errors, message=_validation_message(errors)), 422

    lot = Lots.create_lot(
        name=form.name.data,
        location=form.location.data,
        is_paid=form.is_paid.data,
        floors=form.floors.data,
    )

    try:
        db.session.add(lot)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(message='No se pudo guardar el lote. Inténtalo de nuevo en un momento.'), 500

    summary = _lot_summaries([lot])[0]
    return jsonify(
        message=_created_message(summary),
        row_html=render_template('lots/include/row.html', lot=summary),
    ), 201
