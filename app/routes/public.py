

from flask import Blueprint, render_template

public_bp = Blueprint('public', __name__)


@public_bp.route('/')
def hello_world():
    return render_template('index.html')