# KC Local SEO Financial Blueprint

A dedicated financial management and forecasting tool for KC Local SEO, built as a specialized Flask Blueprint. This tool provides "anxiety-free" financial clarity, focusing on Agency Gross Income (AGI), project profitability, and tax compliance. Optimized for mobile-first management with Zinc/Slate/Neutral tones.

## Key Features

### 1. Project Profitability & Time Tracking
- **Live AHR**: Track Average Hourly Rate in real-time as hours are logged.
- **Delivery Margin**: Monitor project health (Revenue vs. Labor Cost).
- **Project Details**: Deep dive into historical transactions and recurring templates for every client.

### 2. Financial Forecasting
- **13-Week Cash Forecast**: A rolling Chart.js visualization of projected cash flow.
- **Recurring Transactions**: Set up templates (Software, Payroll, Retainers) that automatically populate the ledger on their due date.
- **AGI Gauge**: Real-time tracking of Agency Gross Income (Total Revenue minus Pass-Throughs).

### 3. Compliance & ROI
- **Kansas Property Tax**: Asset ledger that flags items exceeding the $1,500 threshold for personal property rendition.
- **Tax Deadlines**: Countdown to critical dates (W2/1099, Property Rendition).
- **Software ROI**: Link SaaS expenses to projects to analyze spend efficiency relative to supported AGI.

### 4. Data Entry & UX
- **CSV Import**: Bulk upload transactions with a manual review/categorization stage.
- **Mobile First**: Optimized for thumb-driven use with Tailwind CSS.
- **HTMX Powered**: Seamless, no-refresh interactions for all data entry.

## Tech Stack
- **Backend**: Flask, SQLAlchemy (SQLite)
- **Frontend**: Tailwind CSS, HTMX, Jinja2, Chart.js
- **Security**: Werkzeug password hashing, environment-based configuration.

## Installation & Setup

### Option 1: Standalone Runner (Quick Start)
1. **Install Dependencies**:
   ```bash
   pip install -r budget_requirements.txt
   ```
2. **Configuration**:
   Copy `.env.example` to `.env` and set your `FLASK_SECRET_KEY` and `ADMIN_PASSWORD_HASH`.
   - **Generate a password hash**:
     ```bash
     python hash_password.py your_password
     ```
3. **Run**:
   ```bash
   python run_standalone.py
   ```
   Access at `http://127.0.0.1:5000/admin/budget`.

### Option 2: Integrate into Existing Flask App
To add this tool to your existing site:

1. **Register the Blueprint**:
   In your app factory or main `app.py`:
   ```python
   from blueprint import budget_bp, db as budget_db

   app = Flask(__name__)

   # Initialize the budget database (uses its own instance)
   budget_db.init_app(app)

   # Register the blueprint at your preferred prefix
   app.register_blueprint(budget_bp, url_prefix='/admin/budget')
   ```

2. **Required Environment Variables**:
   Ensure your main app's `.env` includes:
   - `ADMIN_PASSWORD_HASH`: Hash for dashboard access (use `hash_password.py`).
   - `DATABASE_URL`: Path to the budget SQLite file (e.g., `sqlite:///budget.db`).

3. **Initialize Models**:
   Run `db.create_all()` within the app context to create the required budget tables.

## Development Logic
- **Signage**: Income is always stored and displayed as positive (+). Expenses (Payroll, Software, etc.) are stored as negative (-) but displayed with absolute values and appropriate coloring (Zinc/Black).
- **Pass-Throughs**: Expenses flagged as "Pass-Through" are deducted from Total Revenue to calculate AGI.
- **Split Accounting**: Transactions linked to multiple projects are split equally among them for all project-specific financial reporting and margin calculations.
- **Assets**: Kansas-specific logic flags any individual asset with a value > $1,500.

## Directory Structure
- `blueprint/`: The core logic, models, and templates of the budget tool.
- `hash_password.py`: Utility to generate the secure password hash.
- `run_standalone.py`: Test runner for local development.
- `budget_requirements.txt`: Necessary Python packages for the budget tool.
