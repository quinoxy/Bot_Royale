"""
Admin Server — Port 5002
Dashboard for managing Bot Royale platform settings,
teams, and tournament operations.
"""

import os
import sys
import subprocess
import threading
import functools
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response

sys.path.insert(0, os.path.dirname(__file__))
from database import (
    init_db,
    get_all_settings,
    set_setting,
    get_all_teams_including_inactive,
    deactivate_team,
    activate_team,
    reset_leaderboard,
    delete_all_matches,
    get_match_count,
    get_team_count,
    get_leaderboard,
    get_matches,
)

app = Flask(__name__)
app.secret_key = os.environ.get("ADMIN_SECRET_KEY", "bot-royale-admin-secret-key")

# Admin credentials (change these or set via environment variables)
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

# Track tournament status
tournament_status = {"running": False, "output": ""}


def check_auth(username, password):
    """Verify admin credentials."""
    return username == ADMIN_USER and password == ADMIN_PASS


def authenticate():
    """Send a 401 response to prompt for credentials."""
    return Response(
        "Access denied. Please provide valid admin credentials.",
        401,
        {"WWW-Authenticate": 'Basic realm="Bot Royale Admin"'},
    )


def require_admin(f):
    """Decorator to require admin login on a route."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


@app.route("/")
@require_admin
def index():
    settings = get_all_settings()
    teams = get_all_teams_including_inactive()
    stats = {
        "team_count": get_team_count(),
        "match_count": get_match_count(),
        "total_teams": len(teams),
    }
    rankings = get_leaderboard()
    recent_matches = get_matches(limit=5)
    return render_template(
        "admin.html",
        settings=settings,
        teams=teams,
        stats=stats,
        rankings=rankings,
        recent_matches=recent_matches,
        tournament_status=tournament_status,
    )


@app.route("/settings", methods=["POST"])
@require_admin
def update_settings():
    # Toggle submissions
    submissions = request.form.get("submissions_open", "0")
    set_setting("submissions_open", submissions)

    # Move timeout
    move_timeout = request.form.get("move_timeout", "2")
    try:
        timeout_val = max(1, min(30, int(move_timeout)))
        set_setting("move_timeout", str(timeout_val))
    except ValueError:
        flash("Invalid move timeout value.", "error")
        return redirect(url_for("index"))

    # Max moves
    max_moves = request.form.get("max_moves", "1000")
    try:
        moves_val = max(10, min(10000, int(max_moves)))
        set_setting("max_moves", str(moves_val))
    except ValueError:
        flash("Invalid max moves value.", "error")
        return redirect(url_for("index"))

    flash("Settings updated successfully!", "success")
    return redirect(url_for("index"))


@app.route("/team/<name>/toggle", methods=["POST"])
@require_admin
def toggle_team(name):
    action = request.form.get("action", "deactivate")
    if action == "activate":
        activate_team(name)
        flash(f"Team '{name}' activated.", "success")
    else:
        deactivate_team(name)
        flash(f"Team '{name}' deactivated.", "success")
    return redirect(url_for("index"))


@app.route("/reset-leaderboard", methods=["POST"])
@require_admin
def reset_lb():
    reset_leaderboard()
    flash("Leaderboard has been reset to zero.", "success")
    return redirect(url_for("index"))


@app.route("/clear-matches", methods=["POST"])
@require_admin
def clear_matches():
    delete_all_matches()
    flash("All match history has been cleared.", "success")
    return redirect(url_for("index"))


@app.route("/run-tournament", methods=["POST"])
@require_admin
def run_tournament():
    if tournament_status["running"]:
        flash("A tournament is already running!", "error")
        return redirect(url_for("index"))

    def _run():
        tournament_status["running"] = True
        tournament_status["output"] = "Starting tournament...\n"
        try:
            script = os.path.join(os.path.dirname(__file__), "run_tournament.py")
            result = subprocess.run(
                [sys.executable, script, "--round-robin"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            tournament_status["output"] = result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            tournament_status["output"] = "Tournament timed out after 10 minutes."
        except Exception as e:
            tournament_status["output"] = f"Error: {e}"
        finally:
            tournament_status["running"] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    flash("Tournament started! Refresh to see progress.", "success")
    return redirect(url_for("index"))


@app.route("/api/tournament-status")
@require_admin
def api_tournament_status():
    return jsonify(tournament_status)


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  Bot Royale — Admin Server")
    print("  Running on http://0.0.0.0:5002")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5002, debug=True)
