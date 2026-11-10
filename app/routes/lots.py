from flask import Blueprint, jsonify, render_template, session
from sqlalchemy.exc import SQLAlchemyError

from app.database import db
from app.decorators import role_required
from app.forms.lot_form import MAX_FLOORS, LotForm
from app.models import Lots, Role, Spots, User

lots_bp = Blueprint('lots', __name__)

def _role_label(role):
    return role.name.title()


def _reservable_roles():
    """Roles a floor can be restricted to. Admins can already reserve anywhere."""
    return Role.query.filter(Role.name != 'admin').order_by(Role.id).all()


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
    rows = (
        db.session.query(
            Spots.lot_id,
            db.func.count(Spots.id),
            db.func.sum(db.case((Spots.is_accessible.is_(True), 1), else_=0)),
        )
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


@lots_bp.route('/', methods=['GET'])
@role_required('admin')
def index():
    user = db.session.get(User, session['user_id'])
    roles = _reservable_roles()
    form = LotForm()
    return render_template(
        'lots/index.html',
        user=user,
        form=form,
        role_options=[(role.id, _role_label(role)) for role in roles],
        max_floors=MAX_FLOORS,
    )


@lots_bp.route('/rows', methods=['GET'])
@role_required('admin')
def rows():
    lots = Lots.query.filter(Lots.parent_id.is_(None)).all()
    lots.sort(key=lambda lot: lot.name.casefold())
    return render_template('lots/_rows.html', lots=_lot_summaries(lots))


@lots_bp.route('/', methods=['POST'])
@role_required('admin')
def create():
    roles = {role.id: role for role in _reservable_roles()}
    form = LotForm(role_choices=[(role_id, _role_label(role)) for role_id, role in roles.items()])

    if not form.validate():
        errors = form.field_errors()
        if 'csrf_token' in errors:
            message = 'Tu sesión expiró. Recarga la página e inténtalo de nuevo.'
        elif 'name' in errors and errors['name'].startswith('Ya existe'):
            message = errors['name']
        else:
            count = len(errors)
            message = (
                'Corrige el campo marcado e inténtalo de nuevo.'
                if count == 1
                else f'Corrige los {count} campos marcados e inténtalo de nuevo.'
            )
        return jsonify(errors=errors, message=message), 422

    floors = [
        {
            'capacity': entry.form.capacity.data,
            'accessible_capacity': entry.form.accessible_capacity.data,
            'role': roles[entry.form.role_id.data],
        }
        for entry in form.floors.entries
    ]
    lot = Lots.create_lot(
        name=form.name.data,
        location=form.location.data,
        is_paid=form.is_paid.data,
        floors=floors,
    )

    try:
        db.session.add(lot)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(
            errors={},
            message='No se pudo guardar el lote. Inténtalo de nuevo en un momento.',
        ), 500

    summary = _lot_summaries([lot])[0]
    if summary['floors']:
        message = (
            f"{lot.name} se creó con {_plural(summary['floors'], 'piso')} "
            f"y {_plural(summary['spots'], 'espacio')}."
        )
    else:
        message = f"{lot.name} se creó como un lote vacío."

    return jsonify(
        id=lot.id,
        name=lot.name,
        message=message,
        row_html=render_template('lots/_row.html', lot=summary),
    ), 201
