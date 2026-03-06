import os
from flask import Flask
from dotenv import load_dotenv
from blueprint import budget_bp, db

# Load environment variables from .env
load_dotenv()

def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///budget.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)

    # Register Blueprint
    app.register_blueprint(budget_bp, url_prefix='/admin/budget')

    # Home redirect to budget tool
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('budget.dashboard'))

    with app.app_context():
        db.create_all()
        print("Database initialized.")

    return app

if __name__ == '__main__':
    app = create_app()
    print("Starting KC Local SEO Budget Tool standalone runner...")
    print("Access the dashboard at http://127.0.0.1:5000/admin/budget")
    app.run(debug=True, port=5000)
