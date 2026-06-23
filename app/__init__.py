import os
from flask import Flask, jsonify, render_template
from flask_cors import CORS
from werkzeug.exceptions import HTTPException
from config import Config

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    CORS(app)
    os.makedirs(app.instance_path, exist_ok=True)

    from . import db
    db.init_app(app)

    from .routes import api
    app.register_blueprint(api, url_prefix="/api")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(HTTPException)
    def handle_http_error(e):
        return jsonify({
            "status": "error",
            "error": e.name,
            "message": e.description
        }), e.code

    @app.errorhandler(Exception)
    def handle_exception(e):
        return jsonify({
            "status": "error",
            "error": "Internal Server Error",
            "message": str(e)
        }), 500

    return app