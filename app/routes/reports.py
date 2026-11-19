from flask import Blueprint, current_app, render_template, session, url_for

from app.decorators import role_required
from app.models import Lots, Role, User

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/', methods=['GET'])
@role_required('admin')
def index():
    management_url = (
        url_for('lots.index') if 'lots.index' in current_app.view_functions else None
    )
    return render_template(
        'reports/index.html',
        user=User.get_user_by_id(session['user_id']),
        lots=Lots.get_parent_lots(),
        roles=Role.get_roles_for_lots(),
        management_url=management_url,
    )
