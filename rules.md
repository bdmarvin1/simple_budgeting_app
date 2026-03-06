You are building a specialized Flask Blueprint for an agency founder. This is a clean-slate financial tool integrated into an existing PythonAnywhere site.

ARCHITECTURAL CONSTRAINTS

Blueprint Prefix: /admin/budget.

Database: Use a dedicated, clean database (SQLAlchemy). Do not mix with existing site data.

UI Stack: Flask + Jinja2 + Tailwind CSS + HTMX (for no-refresh interactions).

Mobile First: Mandatory. All inputs, buttons, and charts must be optimized for thumb-driven mobile use.

FINANCIAL LOGIC (THE 2026 ARCHITECTURE)

AGI (Agency Gross Income): Always subtract 'Pass-Through' expenses (Ad Spend, White Label Fees) before calculating margins.

Decimal Hours: Time entries are stored as decimals (e.g., 1.5), NOT HH:MM.

Project Scope: Only track and display projects marked as 'ACTIVE'.

Currency: Use Decimal or round(val, 2) to ensure financial precision.

KANSAS REGULATORY LOGIC

Personal Property: Flag any asset >$1,500. Assessment rate: 25%.

Key Deadlines: Jan 31 (W2/1099), Mar 15 (Property Rendition), Mar 16 (S-Corp), Apr 15 (Kansas State Tax).

UI/UX GUIDELINES

Theme: "Anxiety-Free" Design. Use Zinc/Slate/Neutral tones.

Feedback: Use HTMX for "Log Hours" and "Add Transaction" to give instant feedback without full page reloads.

Color Coding: Green for healthy margins, Red only for <50% delivery margin or >80% budget burn.

CODING PATTERN

Keep models.py, routes.py, and utils.py (for KPI math) clean and separate within the blueprint folder.

Ensure all routes are guarded by the existing Admin/Founder authentication layer.
