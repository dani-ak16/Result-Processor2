import os
from flask import Flask
from flask_migrate import Migrate
from extensions import db, login_manager
from config import Config
from blueprints import register_blueprints
from setup import initialize_data


migrate = Migrate()

def create_app():

    app = Flask(__name__)

    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    register_blueprints(app)

    os.makedirs(
        os.path.join(app.config["UPLOAD_FOLDER"], "photos"),
        exist_ok=True
    )

    initialize_data(app)

    return app
