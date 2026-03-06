from flask import Blueprint
from .models import db

budget_bp = Blueprint(
    'budget',
    __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/budget/static'
)

from . import routes
