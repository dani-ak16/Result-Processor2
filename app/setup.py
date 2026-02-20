from models import *
from extensions import db
from seeds import seed_initial_data

def initialize_data(app):

    with app.app_context():

        db.create_all()
        # seed_initial_data()
        
