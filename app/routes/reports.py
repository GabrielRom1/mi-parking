from flask import Blueprint, current_app, jsonify, render_template, request, session, url_for

from app.decorators import role_required
from app.models import Lots, Role, User
from app.services.reports import ReportError, build_report, parse_filters

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/', methods=['GET'])
@role_required('admin')
def index():
    # Lot management (feature/lot-management) is registered at /admin/lots.
    management_url = (
        url_for('lots.index') if 'lots.index' in current_app.view_functions else '/admin/lots/'
    )
    return render_template(
        'reports/index.html',
        user=User.get_user_by_id(session['user_id']),
        lots=Lots.get_parent_lots(),
        roles=Role.get_roles_for_lots(),
        management_url=management_url,
    )


@reports_bp.route('/data', methods=['GET'])
@role_required('admin')
def data():
    try:
        period, lot, role = parse_filters(request.args)
    except ReportError as error:
        return jsonify(error=str(error)), 400
    return jsonify(build_report(period, lot, role))
