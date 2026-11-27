from pathlib import Path

from flask import Blueprint, current_app, render_template

from app.decorators import role_required

public_bp = Blueprint('public', __name__)

LANDING_IMAGE_DIR = Path('img') / 'landing'


def _landing_images():
    """Names (without extension) of the landing photos that exist in static/img/landing."""
    folder = Path(current_app.static_folder) / LANDING_IMAGE_DIR
    if not folder.is_dir():
        return set()
    return {path.stem for path in folder.glob('*.webp')}


@public_bp.route('/')
def index():
    # landing page
    return render_template('index.html', landing_images=_landing_images())


@public_bp.route('/restringida')
@role_required()
def restrict():
    return 'ruta restringida'


@public_bp.route('/restringida-admin')
@role_required('admin')
def restrict_admin():
    return 'ruta restringida para admins'