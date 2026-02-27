"""
Authentication module for Bot Royale admin panel.
Uses session-based auth with a password from environment variable.
"""

import os
import functools
from flask import session, redirect, url_for, request


# Default password if env var not set (for development only)
ADMIN_PASSWORD = os.environ.get("BOT_ROYALE_ADMIN_PASSWORD", "admin")


def login_required(f):
    """Decorator to protect admin routes."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def check_password(password: str) -> bool:
    """Verify the admin password."""
    return password == ADMIN_PASSWORD
