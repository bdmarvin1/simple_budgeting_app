import os
import csv
import io
from flask import render_template, request, redirect, url_for, session, flash, current_app
from werkzeug.security import check_password_hash
from . import budget_bp
from .models import db, Transaction, Project, TimeEntry, RecurringTransaction, Asset
from .utils import (
    login_required, calculate_agi, get_kansas_tax_deadlines,
    get_forecast_data, process_recurring_transactions
)
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func

@budget_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = os.environ.get('ADMIN_PASSWORD_HASH')

        if hashed_password and check_password_hash(hashed_password, password):
            session['logged_in'] = True
            return redirect(url_for('budget.dashboard'))
        else:
            flash('Invalid password', 'danger')

    return render_template('budget/login.html')

@budget_bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('budget.login'))

@budget_bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@budget_bp.route('/')
@login_required
def dashboard():
    process_recurring_transactions()
    transactions = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
    agi = calculate_agi()
    deadlines = get_kansas_tax_deadlines()
    projects = Project.query.filter_by(status='ACTIVE').all()
    forecast_data = get_forecast_data()

    project_stats = {}
    for p in projects:
        total_hours = db.session.query(func.sum(TimeEntry.hours)).filter(TimeEntry.project_id == p.id).scalar() or Decimal('0')
        ahr = p.monthly_retainer / total_hours if total_hours > 0 else Decimal('0')
        cost = total_hours * p.cost_rate
        margin = (p.monthly_retainer - cost) / p.monthly_retainer * 100 if p.monthly_retainer > 0 else Decimal('0')
        project_stats[p.id] = {'total_hours': total_hours, 'ahr': ahr, 'margin': margin}

    return render_template(
        'budget/dashboard.html',
        transactions=transactions,
        agi=agi,
        deadlines=deadlines,
        projects=projects,
        project_stats=project_stats,
        forecast_data=forecast_data,
        now_date=datetime.utcnow().strftime('%Y-%m-%d')
    )

@budget_bp.route('/projects')
@login_required
def projects():
    show_inactive = request.args.get('show_inactive', '0') == '1'
    if show_inactive:
        projects_list = Project.query.all()
    else:
        projects_list = Project.query.filter_by(status='ACTIVE').all()

    project_totals = {}
    for p in projects_list:
        # Split transactions equally among linked projects
        total = sum(t.amount / len(t.projects) for t in p.transactions) if p.transactions else Decimal('0')
        project_totals[p.id] = total

    return render_template('budget/projects.html', projects=projects_list, show_inactive=show_inactive, project_totals=project_totals)

@budget_bp.route('/projects/<int:id>')
@login_required
def project_details(id):
    project = Project.query.get_or_404(id)

    # Split transactions equally among linked projects
    total_income = sum(t.amount / len(t.projects) for t in project.transactions if t.amount > 0)
    total_expenses = sum(abs(t.amount) / len(t.projects) for t in project.transactions if t.amount < 0)
    net_total = total_income - total_expenses

    # Calculate margin based on split transactions
    margin = (total_income - total_expenses) / total_income * 100 if total_income > 0 else 0

    # Get linked recurring items
    recurring_items = project.recurring_transactions

    return render_template(
        'budget/project_details.html',
        project=project,
        total_income=total_income,
        total_expenses=total_expenses,
        net_total=net_total,
        margin=margin,
        recurring_items=recurring_items
    )

@budget_bp.route('/projects/add', methods=['POST'])
@login_required
def add_project():
    name = request.form.get('name')
    retainer = Decimal(request.form.get('monthly_retainer', '0'))
    cost_rate = Decimal(request.form.get('cost_rate', '0'))

    new_project = Project(
        name=name,
        monthly_retainer=retainer,
        cost_rate=cost_rate,
        status='ACTIVE'
    )
    db.session.add(new_project)
    db.session.commit()

    flash(f'Project "{name}" added.', 'success')
    return redirect(url_for('budget.projects'))

@budget_bp.route('/projects/update/<int:id>', methods=['POST'])
@login_required
def update_project(id):
    project = Project.query.get_or_404(id)
    project.name = request.form.get('name')
    project.monthly_retainer = Decimal(request.form.get('monthly_retainer', '0'))
    project.cost_rate = Decimal(request.form.get('cost_rate', '0'))
    project.status = request.form.get('status')

    db.session.commit()
    flash(f'Project "{project.name}" updated.', 'success')
    return redirect(url_for('budget.project_details', id=project.id))

@budget_bp.route('/time-tracking')
@login_required
def time_tracking():
    projects = Project.query.filter_by(status='ACTIVE').all()
    time_entries = TimeEntry.query.order_by(TimeEntry.date.desc()).limit(50).all()

    project_stats = {}
    for p in projects:
        total_hours = db.session.query(func.sum(TimeEntry.hours)).filter(TimeEntry.project_id == p.id).scalar() or Decimal('0')
        ahr = p.monthly_retainer / total_hours if total_hours > 0 else Decimal('0')
        cost = total_hours * p.cost_rate
        margin = (p.monthly_retainer - cost) / p.monthly_retainer * 100 if p.monthly_retainer > 0 else Decimal('0')
        project_stats[p.id] = {'total_hours': total_hours, 'ahr': ahr, 'margin': margin}

    return render_template(
        'budget/time_tracking.html',
        projects=projects,
        time_entries=time_entries,
        project_stats=project_stats,
        now_date=datetime.utcnow().strftime('%Y-%m-%d')
    )

@budget_bp.route('/time-tracking/add', methods=['POST'])
@login_required
def add_time_entry():
    project_id = request.form.get('project_id')
    hours = Decimal(request.form.get('hours', '0'))
    date_str = request.form.get('date')
    description = request.form.get('description')
    date = datetime.strptime(date_str, '%Y-%m-%d').date()

    new_entry = TimeEntry(project_id=project_id, hours=hours, date=date, description=description)
    db.session.add(new_entry)
    db.session.commit()

    if request.headers.get('HX-Request'):
        projects = Project.query.filter_by(status='ACTIVE').all()
        time_entries = TimeEntry.query.order_by(TimeEntry.date.desc()).limit(50).all()
        project_stats = {}
        for p in projects:
            total_hours = db.session.query(func.sum(TimeEntry.hours)).filter(TimeEntry.project_id == p.id).scalar() or Decimal('0')
            ahr = p.monthly_retainer / total_hours if total_hours > 0 else Decimal('0')
            cost = total_hours * p.cost_rate
            margin = (p.monthly_retainer - cost) / p.monthly_retainer * 100 if p.monthly_retainer > 0 else Decimal('0')
            project_stats[p.id] = {'total_hours': total_hours, 'ahr': ahr, 'margin': margin}
        return render_template('budget/partials/time_entry_list.html', time_entries=time_entries) + \
               f'<div id="project-stats-container" hx-swap-oob="true">' + \
               render_template('budget/partials/project_time_stats.html', projects=projects, project_stats=project_stats) + \
               '</div>'
    return redirect(url_for('budget.time_tracking'))

@budget_bp.route('/recurring')
@login_required
def recurring():
    recurring_items = RecurringTransaction.query.all()
    projects = Project.query.filter_by(status='ACTIVE').all()
    return render_template('budget/recurring.html', recurring_items=recurring_items, projects=projects)

@budget_bp.route('/recurring/add', methods=['POST'])
@login_required
def add_recurring():
    description = request.form.get('description')
    amount = Decimal(request.form.get('amount', '0'))
    category = request.form.get('category')
    frequency = request.form.get('frequency')
    is_pass_through = 'is_pass_through' in request.form
    create_immediate = 'create_immediate' in request.form
    next_date_str = request.form.get('next_date')
    project_ids = request.form.getlist('project_ids')

    next_date = datetime.strptime(next_date_str, '%Y-%m-%d').date()

    # Ensure sign matches category
    if category == 'Income':
        amount = abs(amount)
    else:
        amount = -abs(amount)

    new_recurring = RecurringTransaction(
        description=description,
        amount=amount,
        category=category,
        frequency=frequency,
        is_pass_through=is_pass_through,
        next_date=next_date
    )

    if project_ids:
        projects = Project.query.filter(Project.id.in_(project_ids)).all()
        new_recurring.projects = projects

    db.session.add(new_recurring)
    db.session.commit()

    if create_immediate:
        from .utils import process_recurring_transactions
        process_recurring_transactions()

    flash('Recurring transaction added.', 'success')
    return redirect(url_for('budget.recurring'))

@budget_bp.route('/recurring/delete/<int:id>', methods=['POST'])
@login_required
def delete_recurring(id):
    recurring = RecurringTransaction.query.get_or_404(id)
    db.session.delete(recurring)
    db.session.commit()
    flash('Recurring transaction deleted.', 'success')
    return redirect(url_for('budget.recurring'))

@budget_bp.route('/roi')
@login_required
def roi():
    software_items = RecurringTransaction.query.filter_by(category='Software').all()
    roi_data = []
    for s in software_items:
        linked_projects = s.projects
        if not linked_projects:
            efficiency = 0
            total_supported_agi = 0
        else:
            total_supported_agi = sum(p.monthly_retainer for p in linked_projects)
            efficiency = total_supported_agi / abs(s.amount) if s.amount != 0 else 0
        roi_data.append({
            'software': s,
            'linked_projects': linked_projects,
            'efficiency': efficiency,
            'total_supported_agi': total_supported_agi
        })
    return render_template('budget/roi.html', roi_data=roi_data)

@budget_bp.route('/assets')
@login_required
def assets():
    assets_list = Asset.query.order_by(Asset.purchase_date.desc()).all()
    return render_template('budget/assets.html', assets=assets_list)

@budget_bp.route('/assets/add', methods=['POST'])
@login_required
def add_asset():
    name = request.form.get('name')
    value = Decimal(request.form.get('value', '0'))
    date_str = request.form.get('purchase_date')
    purchase_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    new_asset = Asset(name=name, value=value, purchase_date=purchase_date)
    db.session.add(new_asset)
    db.session.commit()
    flash('Asset added.', 'success')
    return redirect(url_for('budget.assets'))

@budget_bp.route('/assets/delete/<int:id>', methods=['POST'])
@login_required
def delete_asset(id):
    asset = Asset.query.get_or_404(id)
    db.session.delete(asset)
    db.session.commit()
    flash('Asset deleted.', 'success')
    return redirect(url_for('budget.assets'))

@budget_bp.route('/import', methods=['GET', 'POST'])
@login_required
def import_csv():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file or not file.filename.endswith('.csv'):
            flash('Please upload a valid CSV file.', 'danger')
            return redirect(url_for('budget.import_csv'))

        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            reader = csv.DictReader(stream)

            pending_items = []
            for row in reader:
                # Expecting columns: Date, Description, Amount
                # Flexible names
                date_val = row.get('Date') or row.get('date')
                desc_val = row.get('Description') or row.get('description') or row.get('Desc')
                amount_val = row.get('Amount') or row.get('amount')

                if date_val and amount_val:
                    pending_items.append({
                        'date': date_val,
                        'description': desc_val,
                        'amount': amount_val
                    })

            projects = Project.query.filter_by(status='ACTIVE').all()
            return render_template('budget/import_review.html', items=pending_items, projects=projects)
        except Exception as e:
            flash(f'Error parsing CSV: {str(e)}', 'danger')
            return redirect(url_for('budget.import_csv'))

    return render_template('budget/import.html')

@budget_bp.route('/import/save', methods=['POST'])
@login_required
def save_import():
    indices = request.form.getlist('import_index')

    for i in indices:
        if f'save_{i}' in request.form:
            date_str = request.form.get(f'date_{i}')
            description = request.form.get(f'description_{i}')
            amount = Decimal(request.form.get(f'amount_{i}'))
            category = request.form.get(f'category_{i}')
            is_pass_through = f'is_pass_through_{i}' in request.form
            project_ids = request.form.getlist(f'project_ids_{i}')

            try:
                # Ensure sign matches category
                if category == 'Income':
                    amount = abs(amount)
                else:
                    amount = -abs(amount)

                # Try common date formats
                date = None
                for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y'):
                    try:
                        date = datetime.strptime(date_str, fmt).date()
                        break
                    except: continue

                if not date: date = datetime.utcnow().date()

                new_transaction = Transaction(
                    date=date,
                    description=description,
                    amount=amount,
                    category=category,
                    is_pass_through=is_pass_through
                )
                if project_ids:
                    projects = Project.query.filter(Project.id.in_(project_ids)).all()
                    new_transaction.projects = projects

                db.session.add(new_transaction)
            except Exception as e:
                flash(f'Error saving item {description}: {str(e)}', 'danger')

    db.session.commit()
    flash('Imported transactions saved.', 'success')
    return redirect(url_for('budget.dashboard'))

@budget_bp.route('/transactions/add', methods=['POST'])
@login_required
def add_transaction():
    description = request.form.get('description')
    amount_str = request.form.get('amount')
    date_str = request.form.get('date')
    category = request.form.get('category')
    is_pass_through = 'is_pass_through' in request.form
    project_ids = request.form.getlist('project_ids')

    try:
        amount = Decimal(amount_str)

        # Ensure sign matches category
        if category == 'Income':
            amount = abs(amount)
        else:
            amount = -abs(amount)

        date = datetime.strptime(date_str, '%Y-%m-%d').date()

        new_transaction = Transaction(
            description=description,
            amount=amount,
            date=date,
            category=category,
            is_pass_through=is_pass_through
        )

        if project_ids:
            projects = Project.query.filter(Project.id.in_(project_ids)).all()
            new_transaction.projects = projects

        db.session.add(new_transaction)
        db.session.commit()

        if request.headers.get('HX-Request'):
            transactions = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
            agi = calculate_agi()
            return render_template('budget/partials/transaction_list.html', transactions=transactions) + \
                   f'<div id="agi-gauge-container" hx-swap-oob="true">' + \
                   render_template('budget/partials/agi_gauge.html', agi=agi) + \
                   '</div>'

        return redirect(url_for('budget.dashboard'))
    except Exception as e:
        db.session.rollback()
        if request.headers.get('HX-Request'):
            return f'<div class="text-red-500">Error: {str(e)}</div>', 400
        flash(f'Error adding transaction: {str(e)}', 'danger')
        return redirect(url_for('budget.dashboard'))

@budget_bp.route('/transactions/delete/<int:id>', methods=['DELETE'])
@login_required
def delete_transaction(id):
    transaction = Transaction.query.get_or_404(id)
    db.session.delete(transaction)
    db.session.commit()

    if request.headers.get('HX-Request'):
        transactions = Transaction.query.order_by(Transaction.date.desc()).limit(10).all()
        agi = calculate_agi()
        return render_template('budget/partials/transaction_list.html', transactions=transactions) + \
               f'<div id="agi-gauge-container" hx-swap-oob="true">' + \
               render_template('budget/partials/agi_gauge.html', agi=agi) + \
               '</div>'

    return redirect(url_for('budget.dashboard'))
