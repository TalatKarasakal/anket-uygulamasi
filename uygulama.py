import os
from flask import Flask
from dotenv import load_dotenv
from uzantılar import db

load_dotenv()

uygulama = Flask(__name__)
uygulama.config["SECRET_KEY"] = os.environ["GİZLİ_ANAHTAR"]
uygulama.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///anket.db"
db.init_app(uygulama)

import modeller

with uygulama.app_context():
    db.create_all()