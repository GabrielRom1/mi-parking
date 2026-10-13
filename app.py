import os

from flask import Flask, Blueprint, jsonify, render_template, request


from routes.auth import auth_bp

from dotenv import load_dotenv


app = Flask(__name__)
load_dotenv()



app.register_blueprint(auth_bp, url_prefix='/auth')


@app.route('/')
def hello_world():
   return render_template('index.html')



if __name__ == '__main__':
    
    port = int(os.getenv('FLASK_PORT', '4030'))
    app.run(host='0.0.0.0', port=port, debug=True)