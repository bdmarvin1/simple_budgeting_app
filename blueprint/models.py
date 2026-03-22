from extensions import db
from datetime import datetime

class Transaction(db.Model):
    __bind_key__ = 'budget'
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(100))
    is_pass_through = db.Column(db.Boolean, default=False)

class RecurringTransaction(db.Model):
    __bind_key__ = 'budget'
    __tablename__ = 'recurring_transactions'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(100))
    frequency = db.Column(db.String(50), default='MONTHLY')
    is_pass_through = db.Column(db.Boolean, default=False)
    next_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

class Project(db.Model):
    __bind_key__ = 'budget'
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    monthly_retainer = db.Column(db.Numeric(10, 2), default=0.0)
    cost_rate = db.Column(db.Numeric(10, 2), default=0.0)
    status = db.Column(db.String(20), default='ACTIVE')
    planned_hours = db.Column(db.Numeric(10, 2), default=0.0)

    time_entries = db.relationship('TimeEntry', backref='project', lazy=True)

# Define Association Tables with EXPLICIT metadata
transaction_projects = db.Table(
    'transaction_projects',
    Transaction.metadata,
    db.Column('transaction_id', db.Integer, db.ForeignKey('transactions.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    info={'bind_key': 'budget'}
)

recurring_transaction_projects = db.Table(
    'recurring_transaction_projects',
    Transaction.metadata,
    db.Column('recurring_transaction_id', db.Integer, db.ForeignKey('recurring_transactions.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True),
    info={'bind_key': 'budget'}
)

# Late-bind relationships
Project.transactions = db.relationship('Transaction', secondary=transaction_projects, backref=db.backref('projects', lazy=True))
Project.recurring_transactions = db.relationship('RecurringTransaction', secondary=recurring_transaction_projects, backref=db.backref('projects', lazy=True))

class TimeEntry(db.Model):
    __bind_key__ = 'budget'
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    hours = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(255))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

class Asset(db.Model):
    __bind_key__ = 'budget'
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Numeric(10, 2), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
