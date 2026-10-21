
from flask import Blueprint, jsonify, render_template, request


auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route('/login', methods=['GET','POST'])
def login():
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    return render_template('register.html')
