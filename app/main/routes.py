from flask import render_template, request, redirect, url_for, flash, session
from utils.academic import get_current_session
from datetime import datetime
from . import main_bp

@main_bp.route("/")
def home():
    current_session = get_current_session()
    current_year = datetime.now().year

    return render_template("main/home.html",
        session=current_session,
        datetime=datetime,
        year=current_year
    )

@main_bp.route("/dashboard")
def dashboard():
    current_session = get_current_session()
    current_year = datetime.now().year

    return render_template("main/dashboard.html",
        session=current_session,
        datetime=datetime,
        year=current_year
    )