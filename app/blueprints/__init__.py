from auth.routes import auth_bp
from students.routes import students_bp
from assessments.routes import assessments_bp
from results.routes import results_bp
from teacher.routes import teacher_bp
# from analytics.routes import analytics_bp
from admin.routes import admin_bp
from file_uploads.routes import uploads_bp
from main.routes import main_bp

def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(students_bp)
    app.register_blueprint(assessments_bp)
    app.register_blueprint(results_bp)
    app.register_blueprint(teacher_bp)
    # app.register_blueprint(analytics_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(uploads_bp)
