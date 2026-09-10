from flask import Flask
from uzantılar import db

uygulama = Flask(__name__)
uygulama.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///anket.db"
db.init_app(uygulama)

import modeller


with uygulama.app_context():
    db.create_all()
