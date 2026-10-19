import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.models import Role

app = create_app()

with app.app_context():
    Role.add_default_roles()

if __name__ == '__main__':
    port = int(os.getenv('FLASK_PORT', '4030'))
    app.run(host='0.0.0.0', port=port, debug=True)