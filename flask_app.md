# Update Instructions for `flask_app.py`

To resolve the `InvalidRequestError` and properly integrate the Budget Tool while keeping the databases separate, please apply the following changes to your `flask_app.py`.

### 1. Update Imports

Ensure you are importing `db` from the blueprint instead of creating a new instance.

**Find:**
```python
from flask_sqlalchemy import SQLAlchemy
# ... other imports ...
from blueprint import budget_bp
```

**Change to:**
```python
from blueprint import budget_bp, db
```

### 2. Configure `SQLALCHEMY_BINDS`

Add the `SQLALCHEMY_BINDS` configuration to your app. This allows Flask-SQLAlchemy to manage multiple database files.

**Find where you set `SQLALCHEMY_DATABASE_URI` and add the following:**

```python
# Main database (e.g., MySQL or another SQLite)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')

# Budget database (Separate SQLite)
app.config['SQLALCHEMY_BINDS'] = {
    'budget': os.environ.get('DATABASE_URL', 'sqlite:///budget.db')
}
```

### 3. Use the Shared `db` Instance

Remove the line where you create a new `SQLAlchemy` instance and replace it with `db.init_app(app)`.

**Find and Remove:**
```python
db = SQLAlchemy(app)
```

**Replace with:**
```python
db.init_app(app)
```

### 4. Update Tables Creation

In your startup logic (e.g., in an `app_context()` block), ensure you are creating tables for all binds.

```python
with app.app_context():
    db.create_all() # Creates tables for the main URI
    db.create_all(bind_key='budget') # Creates tables for the budget SQLite db
```

---

### Why this is necessary:
SQLAlchemy mappers need to be initialized against a single metadata instance when they share relationships. By using `db.init_app(app)` with the `db` instance from the blueprint, both your main app models and the budget tool models will share the same metadata, while `SQLALCHEMY_BINDS` ensures they still point to separate physical database files.

The models in `blueprint/models.py` have also been refactored to use association models, which is more robust for this type of multi-database setup.
