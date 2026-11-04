from flask import Blueprint, render_template

from app.decorators import role_required

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def hello_world():
    return render_template('index.html')


@public_bp.route('/restringida')
@role_required()
def restrict():
    return 'ruta restringida'


@public_bp.route('/restringida-admin')
@role_required('admin')
def restrict_admin():
    return 'ruta restringida para admins'