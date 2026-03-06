from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# Association tables for many-to-many relationships
transaction_projects = db.Table('transaction_projects',
    db.Column('transaction_id', db.Integer, db.ForeignKey('transactions.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True)
)

recurring_transaction_projects = db.Table('recurring_transaction_projects',
    db.Column('recurring_transaction_id', db.Integer, db.ForeignKey('recurring_transactions.id'), primary_key=True),
    db.Column('project_id', db.Integer, db.ForeignKey('projects.id'), primary_key=True)
)

class Project(db.Model):
    __tablename__ = 'projects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    monthly_retainer = db.Column(db.Numeric(10, 2), default=0.0)
    cost_rate = db.Column(db.Numeric(10, 2), default=0.0)
    status = db.Column(db.String(20), default='ACTIVE')  # ACTIVE, COMPLETED, CANCELLED
    planned_hours = db.Column(db.Numeric(10, 2), default=0.0)

    time_entries = db.relationship('TimeEntry', backref='project', lazy=True)

    # Relationship for transactions (many-to-many)
    transactions = db.relationship('Transaction', secondary=transaction_projects, backref='projects')

    def __repr__(self):
        return f'<Project {self.name}>'

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(100))
    is_pass_through = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Transaction {self.description} - {self.amount}>'

class RecurringTransaction(db.Model):
    __tablename__ = 'recurring_transactions'
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(255), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    category = db.Column(db.String(100))
    frequency = db.Column(db.String(50), default='MONTHLY')  # MONTHLY, ANNUAL, WEEKLY
    is_pass_through = db.Column(db.Boolean, default=False)
    next_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    # Relationship for projects (many-to-many)
    projects = db.relationship('Project', secondary=recurring_transaction_projects, backref='recurring_transactions')

    def __repr__(self):
        return f'<RecurringTransaction {self.description} - {self.amount} ({self.frequency})>'

class TimeEntry(db.Model):
    __tablename__ = 'time_entries'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    hours = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(255))
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    def __repr__(self):
        return f'<TimeEntry {self.hours}h for Project {self.project_id}>'

class Asset(db.Model):
    __tablename__ = 'assets'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Numeric(10, 2), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)

    @property
    def is_taxable_kansas(self):
        # Flag any asset >$1,500. Assessment rate: 25%.
        return self.value > 1500

    def __repr__(self):
        return f'<Asset {self.name} - {self.value}>'
