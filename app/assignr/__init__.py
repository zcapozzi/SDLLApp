"""Assignr integration blueprint."""

from flask import Blueprint

assignr_bp = Blueprint('assignr', __name__)

from . import routes  # noqa: F401, E402
