from flask import render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user
from extensions import db
from .loaders import load_user
from models.user import User, School
from utils.decorators import login_required
from . import auth_bp
from seeds import seed_initial_data
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from email_validator import validate_email, EmailNotValidError
import re

@auth_bp.route("/register-school", methods=["GET", "POST"])
def register_school():
    if request.method == "POST":
        try:
            # Input validation and sanitization
            school_name = request.form.get("school_name", "").strip()
            admin_username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            
            # Validate required fields
            if not all([school_name, admin_username, email, password]):
                flash("All fields are required", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Validate school name
            if len(school_name) < 3 or len(school_name) > 200:
                flash("School name must be between 3 and 200 characters", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Validate username
            if not re.match(r'^[a-zA-Z0-9_-]{3,30}$', admin_username):
                flash("Username must be 3-30 characters (letters, numbers, underscore, hyphen only)", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Validate email
            try:
                valid = validate_email(email)
                email = valid.email  # normalized form
            except EmailNotValidError as e:
                flash(f"Invalid email: {str(e)}", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Validate password strength
            if len(password) < 8:
                flash("Password must be at least 8 characters long", "danger")
                return redirect(url_for("auth.register_school"))
            
            if not re.search(r'[A-Z]', password):
                flash("Password must contain at least one uppercase letter", "danger")
                return redirect(url_for("auth.register_school"))
            
            if not re.search(r'[a-z]', password):
                flash("Password must contain at least one lowercase letter", "danger")
                return redirect(url_for("auth.register_school"))
            
            if not re.search(r'[0-9]', password):
                flash("Password must contain at least one number", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Check for existing school (case-insensitive)
            if School.query.filter(School.name.ilike(school_name)).first():
                flash("School already registered", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Check for existing username (case-insensitive)
            if User.query.filter(User.username.ilike(admin_username)).first():
                flash("Username already taken", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Check for existing email
            if User.query.filter_by(email=email).first():
                flash("Email already registered", "danger")
                return redirect(url_for("auth.register_school"))
            
            # Create School and Admin in a transaction
            try:
                school = School(
                    name=school_name,
                    email=email
                )
                db.session.add(school)
                db.session.flush()  # Get ID without committing
                
                admin = User(
                    school_id=school.id,
                    username=admin_username,
                    email=email,
                    role="admin"
                )
                admin.set_password(password)
                
                db.session.add(admin)
                db.session.commit()
                
                flash("School registered successfully! Please log in.", "success")
                return redirect(url_for("auth.login"))
                
            except IntegrityError as e:
                db.session.rollback()
                # Log the error for debugging
                app.logger.error(f"Database integrity error during school registration: {str(e)}")
                flash("Registration failed due to duplicate data. Please try again.", "danger")
                return redirect(url_for("auth.register_school"))
            
            except SQLAlchemyError as e:
                db.session.rollback()
                app.logger.error(f"Database error during school registration: {str(e)}")
                flash("An error occurred during registration. Please try again.", "danger")
                return redirect(url_for("auth.register_school"))
        
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Unexpected error during school registration: {str(e)}")
            flash("An unexpected error occurred. Please try again.", "danger")
            return redirect(url_for("auth.register_school"))
    
    return render_template("auth/register_school.html")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Invalid credentials", "danger")
            return redirect(url_for("auth.login"))

        login_user(user)

        school_id = current_user.school_id
        
        seed_initial_data(school_id)

        return redirect(url_for("main.dashboard"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("auth.login"))