from __init__ import createapp
from extensions import db
from models import *

with app.app_context():
    print(db.engine.table_names())          # ← shows what tables actually exist
    print(User.__table__.name)              # should be 'users'
    print(User.query.first())               # usually raises NoResult or returns None