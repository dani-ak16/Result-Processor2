from flask import Blueprint

downloads_bp = Blueprint(
    "downloads",
    __name__,
    url_prefix="/download"
)
