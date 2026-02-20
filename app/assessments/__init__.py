from flask import Blueprint

assessments_bp = Blueprint(
    "assessments",
    __name__,
    url_prefix="/assessments"
)
