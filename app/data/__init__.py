"""Data Management blueprint for player evals, placement, and surveys."""

from flask import Blueprint

data_bp = Blueprint('data', __name__)

from app.data import routes  # noqa: F401, E402
