from flask import Flask
from extensions import db as budget_db
import os
from dotenv import load_dotenv
import blueprint.models

load_dotenv()

def init_budget_db():
    app = Flask(__name__)

    # Configure binds
    budget_db_uri = os.environ.get('DATABASE_URL', 'sqlite:///budget.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')
    app.config['SQLALCHEMY_BINDS'] = {
        'budget': budget_db_uri
    }
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    budget_db.init_app(app)

    with app.app_context():
        # This will create tables for models with __bind_key__ = 'budget' in the budget SQLite db
        budget_db.create_all(bind_key='budget')
        print(f"Budget database initialized at: {budget_db_uri}")

if __name__ == "__main__":
    init_budget_db()
