"""Facilities management blueprint."""

from flask import Blueprint

facilities_bp = Blueprint('facilities', __name__)

from . import routes
