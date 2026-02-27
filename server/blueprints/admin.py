"""
Admin Blueprint — dashboard for managing the Bot Royale platform.
All routes require admin authentication.
"""

import os
import sys
import subprocess
import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, session

from auth import login_required, check_password
from database import (
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

admin_bp = Blueprint("admin", __name__)

# Track tournament status
tournament_status = {"running": False, "output": ""}


# ------------------------------------------------------------------ #
#  Auth routes (no login_required)                                     #
# ------------------------------------------------------------------ #

@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin.index"))

    if request.method == "POST":
        password = request.form.get("password", "")
        if check_password(password):
            session["admin_authenticated"] = True
            next_url = request.args.get("next", url_for("admin.index"))
            flash("Logged in successfully!", "success")
            return redirect(next_url)
        else:
            flash("Invalid password.", "error")

    return render_template("admin_login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    session.pop("admin_authenticated", None)
    flash("Logged out.", "success")
    return redirect(url_for("upload.index"))


# ------------------------------------------------------------------ #
#  Protected admin routes                                              #
# ------------------------------------------------------------------ #

@admin_bp.route("/")
@login_required
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


@admin_bp.route("/settings", methods=["POST"])
@login_required
def update_settings():
    # Toggle submissions
    submissions = request.form.get("submissions_open", "0")
    set_setting("submissions_open", submissions)

    # Max moves
    max_moves = request.form.get("max_moves", "1000")
    try:
        moves_val = max(10, min(10000, int(max_moves)))
        set_setting("max_moves", str(moves_val))
    except ValueError:
        flash("Invalid max moves value.", "error")
        return redirect(url_for("admin.index"))

    # Time bank
    time_bank = request.form.get("time_bank", "60")
    try:
        tb_val = max(10, min(300, int(time_bank)))
        set_setting("time_bank", str(tb_val))
    except ValueError:
        flash("Invalid time bank value.", "error")
        return redirect(url_for("admin.index"))

    flash("Settings updated successfully!", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/team/<name>/toggle", methods=["POST"])
@login_required
def toggle_team(name):
    action = request.form.get("action", "deactivate")
    if action == "activate":
        activate_team(name)
        flash(f"Team '{name}' activated.", "success")
    else:
        deactivate_team(name)
        flash(f"Team '{name}' deactivated.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/reset-leaderboard", methods=["POST"])
@login_required
def reset_lb():
    reset_leaderboard()
    flash("Leaderboard has been reset to zero.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/clear-matches", methods=["POST"])
@login_required
def clear_matches():
    delete_all_matches()
    flash("All match history has been cleared.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route("/run-tournament", methods=["POST"])
@login_required
def run_tournament():
    if tournament_status["running"]:
        flash("A tournament is already running!", "error")
        return redirect(url_for("admin.index"))

    def _run():
        tournament_status["running"] = True
        tournament_status["output"] = "Starting tournament...\n"
        try:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "run_tournament.py")
            script = os.path.normpath(script)
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
    return redirect(url_for("admin.index"))


@admin_bp.route("/api/tournament-status")
@login_required
def api_tournament_status():
    return jsonify(tournament_status)
