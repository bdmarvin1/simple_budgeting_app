import os
from functools import wraps
from flask import session, redirect, url_for, flash
from decimal import Decimal
from datetime import datetime, timedelta
from .models import Transaction, Project, RecurringTransaction, db

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('budget.login'))
        return f(*args, **kwargs)
    return decorated_function

def calculate_agi():
    """AGI (Agency Gross Income): Total Revenue - Total Pass-Through Expenses."""
    transactions = Transaction.query.all()
    # Total Income: positive transactions that are NOT pass-through (though usually income isn't pass-through)
    # Actually, the rule says AGI = Total Revenue - (Sum of Pass-Through Transactions).
    # Revenue is income. Pass-through are specific expenses.

    total_revenue = sum(t.amount for t in transactions if t.amount > 0)
    total_pass_through = sum(abs(t.amount) for t in transactions if t.is_pass_through and t.amount < 0)

    return total_revenue - total_pass_through

def get_kansas_tax_deadlines():
    return [
        {"date": "Jan 31", "event": "W2/1099 Deadlines"},
        {"date": "Mar 15", "event": "Personal Property Rendition"},
        {"date": "Mar 16", "event": "S-Corp Tax Return"},
        {"date": "Apr 15", "event": "Kansas State Tax"},
    ]

def process_recurring_transactions():
    """Check for due recurring transactions and create entries."""
    today = datetime.utcnow().date()
    recurring_items = RecurringTransaction.query.filter(RecurringTransaction.next_date <= today).all()

    for item in recurring_items:
        while item.next_date <= today:
            # Create transaction
            new_t = Transaction(
                date=item.next_date,
                description=f"{item.description} (Recurring)",
                amount=item.amount,
                category=item.category,
                is_pass_through=item.is_pass_through
            )
            if item.projects:
                new_t.projects = item.projects

            db.session.add(new_t)

            # Update next date
            if item.frequency == 'MONTHLY':
                # Simple month increment
                month = item.next_date.month
                year = item.next_date.year + (month // 12)
                month = (month % 12) + 1
                try:
                    item.next_date = item.next_date.replace(year=year, month=month)
                except ValueError:
                    # Handle last day of month issues
                    # If 31st isn't in next month, use last day of next month
                    import calendar
                    last_day = calendar.monthrange(year, month)[1]
                    item.next_date = item.next_date.replace(year=year, month=month, day=last_day)
            elif item.frequency == 'WEEKLY':
                item.next_date += timedelta(weeks=1)
            elif item.frequency == 'ANNUAL':
                item.next_date = item.next_date.replace(year=item.next_date.year + 1)

            # Commit inside loop to avoid skipping if one fails?
            # Better to commit all at once at the end.

    db.session.commit()

def get_forecast_data():
    """Generate 13-week forecast data."""
    weeks = []
    income_data = []
    expense_data = []

    today = datetime.utcnow().date()

    # Active projects retainers
    active_projects = Project.query.filter_by(status='ACTIVE').all()
    recurring_items = RecurringTransaction.query.all()

    for i in range(13):
        start_date = today + timedelta(weeks=i)
        end_date = start_date + timedelta(days=6)

        weeks.append(start_date.strftime('%b %d'))

        week_income = Decimal('0')
        week_expense = Decimal('0')

        # Approximate project income
        # If we assume retainers are paid on the 1st of the month
        for p in active_projects:
            # Simple logic: if the 1st of any month falls in this week
            # Or just spread it out? The prompt says "upcoming retainers".
            # Let's assume retainers are paid monthly on the day they were created?
            # Or just use the 1st of the month for simplicity in the forecast.

            # For now, let's distribute monthly retainer into 4 weeks for a smoother chart,
            # OR better: pick a day (e.g., 1st of month).

            # Let's try to see if 'today's day' of the month falls in this week
            # This simulates a monthly payment cycle based on "now"
            payment_day = 1 # Assume 1st of the month

            current_check = start_date
            while current_check <= end_date:
                if current_check.day == payment_day:
                    week_income += p.monthly_retainer
                current_check += timedelta(days=1)

        # Recurring items
        for item in recurring_items:
            # Calculate occurrences in this week
            temp_date = item.next_date
            # This is a bit complex to project exactly without a robust rrule engine
            # But let's do a simple approximation

            # If it's MONTHLY
            if item.frequency == 'MONTHLY':
                # Check if any "monthly anniversary" falls in this week
                # (Simple check: is (current_date.day == item.next_date.day))
                current_check = start_date
                while current_check <= end_date:
                    if current_check.day == item.next_date.day:
                        if item.amount > 0: week_income += item.amount
                        else: week_expense += abs(item.amount)
                    current_check += timedelta(days=1)
            elif item.frequency == 'WEEKLY':
                # Weekly always hits once a week
                if item.amount > 0: week_income += item.amount
                else: week_expense += abs(item.amount)
            # ANNUAL is rarer, skip for simple forecast unless it hits
            elif item.frequency == 'ANNUAL':
                if start_date <= item.next_date <= end_date:
                    if item.amount > 0: week_income += item.amount
                    else: week_expense += abs(item.amount)

        income_data.append(float(week_income))
        expense_data.append(float(week_expense))

    return {
        "labels": weeks,
        "income": income_data,
        "expenses": expense_data
    }
