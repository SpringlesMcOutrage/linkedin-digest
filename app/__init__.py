from flask import Flask
from .routes import register_routes
from .config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    register_routes(app)
    return app
