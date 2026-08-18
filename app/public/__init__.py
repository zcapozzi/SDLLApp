"""Public blueprint for unauthenticated access to team schedules."""

from flask import Blueprint

public_bp = Blueprint('public', __name__, url_prefix='/s')

from app.public import routes  # noqa
