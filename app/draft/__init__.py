"""Draft blueprint for managing player drafts."""

from flask import Blueprint

draft_bp = Blueprint('draft', __name__, url_prefix='/draft')

from app.draft import routes
