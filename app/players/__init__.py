"""Players blueprint - player management, evaluations, and metrics."""

from flask import Blueprint

players_bp = Blueprint('players', __name__, url_prefix='/players')

from app.players import routes  # noqa: E402, F401
