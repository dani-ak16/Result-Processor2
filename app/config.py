from flask import config
import os


class Config:

    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "school_result_secret_key"
    )

    ALLOWED_EXTENSIONS = {"csv", "xlsx"}

    if os.environ.get("RENDER"):

        DATABASE = "/tmp/school_results.db"
        UPLOAD_FOLDER = "/tmp/uploads"

    else:
        SQLALCHEMY_DATABASE_URI = "sqlite:///school_results.db"
        UPLOAD_FOLDER = "uploads"
