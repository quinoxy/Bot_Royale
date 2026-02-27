"""
Upload Blueprint — handles bot file uploads.
"""

import os
from flask import Blueprint, request, render_template, redirect, url_for, flash

from database import add_team, get_all_teams, get_setting

upload_bp = Blueprint("upload", __name__)

BOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__) or "."), "bots")
# Fallback: if __file__ resolution is odd, use a path relative to server/
if not os.path.isabs(BOTS_DIR):
    BOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bots")
BOTS_DIR = os.path.normpath(BOTS_DIR)

MAX_FILE_SIZE = 100 * 1024  # 100KB
ALLOWED_EXTENSIONS = {".py"}

os.makedirs(BOTS_DIR, exist_ok=True)


def validate_team_name(name: str) -> str | None:
    """Return error message or None if valid."""
    if not name or not name.strip():
        return "Team name cannot be empty."
    name = name.strip()
    if len(name) > 30:
        return "Team name must be 30 characters or less."
    if not name.replace("_", "").replace("-", "").replace(" ", "").isalnum():
        return "Team name can only contain letters, numbers, spaces, hyphens, and underscores."
    return None


@upload_bp.route("/")
def index():
    teams = get_all_teams()
    submissions_open = get_setting("submissions_open", "1") == "1"
    return render_template("upload.html", teams=teams, submissions_open=submissions_open)


@upload_bp.route("/upload", methods=["POST"])
def upload():
    # Check if submissions are open
    if get_setting("submissions_open", "1") != "1":
        flash("Submissions are currently closed.", "error")
        return redirect(url_for("upload.index"))

    team_name = request.form.get("team_name", "").strip()

    # Validate team name
    err = validate_team_name(team_name)
    if err:
        flash(err, "error")
        return redirect(url_for("upload.index"))

    # Validate file
    if "bot_file" not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("upload.index"))

    file = request.files["bot_file"]
    if file.filename == "":
        flash("No file selected.", "error")
        return redirect(url_for("upload.index"))

    # Check extension
    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        flash(f"Only Python (.py) files are allowed. Got: {ext}", "error")
        return redirect(url_for("upload.index"))

    # Read and check size
    content = file.read()
    if len(content) > MAX_FILE_SIZE:
        flash(f"File too large ({len(content)} bytes). Max is {MAX_FILE_SIZE} bytes.", "error")
        return redirect(url_for("upload.index"))

    # Save the file — use team ID from DB to avoid filename collisions
    safe_name = team_name.replace(" ", "_").lower()
    # Remove any characters that aren't alphanumeric or underscore/hyphen
    safe_name = "".join(c for c in safe_name if c.isalnum() or c in ("_", "-"))
    file_path = os.path.join(BOTS_DIR, f"{safe_name}_bot.py")
    with open(file_path, "wb") as f:
        f.write(content)

    # Register in database
    if add_team(team_name, file_path):
        flash(f"Bot uploaded successfully for team '{team_name}'!", "success")
    else:
        flash("Database error. Please try again.", "error")

    return redirect(url_for("upload.index"))
