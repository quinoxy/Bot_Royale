"""
Bot Royale — Unified Server
Single Flask application serving all pages:
  /              — Upload page
  /leaderboard   — Rankings & match history
  /match/<id>    — Match replay
  /team/<name>   — Team profile
  /admin         — Admin dashboard (password protected)
"""

import os
import sys
import json
import json
import subprocess
import threading
import functools
import time
from datetime import datetime, timezone

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    Response,
    session,
)
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(__file__))
from database import (
    init_db,
    register_team,
    verify_team_password,
    update_team_bot,
    get_team,
    get_all_teams,
    get_all_settings,
    get_setting,
    set_setting,
    get_all_teams_including_inactive,
    deactivate_team,
    activate_team,
    get_leaderboard,
    get_matches,
    get_match,
    get_team_matches,
    get_team_stats,
    get_teams_with_stats,
    reset_leaderboard,
    delete_all_matches,
    get_match_count,
    get_team_count,
)

from bot_runner import run_match

app = Flask(__name__)
# Try to load secret key from env, otherwise generate a secure default
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

# Bot upload config
BOTS_DIR = os.path.join(os.path.dirname(__file__), "bots")
MAX_FILE_SIZE = 100 * 1024  # 100KB
ALLOWED_EXTENSIONS = {".py"}
os.makedirs(BOTS_DIR, exist_ok=True)

# Admin credentials
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin")

# Tournament status (shared state)
tournament_status = {"running": False, "output": ""}

# Global Match Queue
MATCH_QUEUE = []        # list of tuples: (team1_name, team2_name)
QUEUE_PAUSED = True     # start paused by default
QUEUE_LOCK = threading.Lock()

def queue_worker():
    """Background thread that pops matches from the queue and runs them."""
    global MATCH_QUEUE, QUEUE_PAUSED
    while True:
        try:
            time.sleep(1)
            with QUEUE_LOCK:
                if QUEUE_PAUSED or not MATCH_QUEUE:
                    continue
                # Pop next match
                team1_name, team2_name = MATCH_QUEUE.pop(0)

            # Check if they still exist
            t1 = get_team(team1_name)
            t2 = get_team(team2_name)
            if not t1 or not t2:
                continue

            # Run the match
            try:
                move_timeout = float(get_setting("move_timeout", "60.0"))
            except ValueError:
                move_timeout = 60.0

            result = run_match(team1_name, t1["file_path"], team2_name, t2["file_path"], time_bank=move_timeout)
            record_match(team1_name, team2_name, result["winner"], result["result_desc"], result["moves"])
        except Exception as e:
            print(f"Queue worker error: {e}")

# Start background thread
threading.Thread(target=queue_worker, daemon=True).start()


# ------------------------------------------------------------------ #
#  Admin auth helpers                                                 #
# ------------------------------------------------------------------ #

def check_auth(username, password):
    return username == ADMIN_USER and password == ADMIN_PASS


def authenticate():
    return Response(
        "Access denied. Please provide valid admin credentials.",
        401,
        {"WWW-Authenticate": 'Basic realm="Bot Royale Admin"'},
    )


def require_admin(f):
    """Decorator to require HTTP Basic Auth on a route."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ------------------------------------------------------------------ #
#  Upload helpers                                                     #
# ------------------------------------------------------------------ #

def validate_team_name(name: str) -> str | None:
    """Return error message or None if valid."""
    if not name or not name.strip():
        return "Team name cannot be empty."
    name = name.strip()
    if len(name) > 30:
        return "Team name must be 30 characters or less."
    if name.lower() in ("admin", "administrator", "system", "root"):
        return "This team name is reserved."
    if not name.replace("_", "").replace("-", "").replace(" ", "").isalnum():
        return "Team name can only contain letters, numbers, spaces, hyphens, and underscores."
    return None


def save_bot_file(team_name: str, file) -> str | None:
    """Validate and save a bot file. Returns file_path on success, None on error (flashes error)."""
    if file is None or file.filename == "":
        flash("No file selected.", "error")
        return None

    _, ext = os.path.splitext(file.filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        flash(f"Only Python (.py) files are allowed. Got: {ext}", "error")
        return None

    content = file.read()
    if len(content) > MAX_FILE_SIZE:
        flash(f"File too large ({len(content)} bytes). Max is {MAX_FILE_SIZE} bytes.", "error")
        return None

    safe_name = secure_filename(team_name.replace(" ", "_").lower())
    if not safe_name:
        safe_name = "bot_" + str(hash(team_name))
        
    file_path = os.path.join(BOTS_DIR, f"{safe_name}_bot.py")
    with open(file_path, "wb") as f:
        f.write(content)
    return file_path


# ================================================================== #
#  AUTH & DASHBOARD ROUTES                                             #
# ================================================================== #

@app.route("/")
def index():
    """Landing page — register or login."""
    if session.get("team"):
        return redirect(url_for("dashboard"))
    teams = get_teams_with_stats()
    submissions_open = get_setting("submissions_open", "1") == "1"
    return render_template("upload.html", teams=teams, submissions_open=submissions_open)


@app.route("/register", methods=["POST"])
def register():
    """Register a new team."""
    if get_setting("submissions_open", "1") != "1":
        flash("Submissions are currently closed.", "error")
        return redirect(url_for("index"))

    team_name = request.form.get("team_name", "").strip()
    password = request.form.get("password", "")

    err = validate_team_name(team_name)
    if err:
        flash(err, "error")
        return redirect(url_for("index"))

    if len(password) < 4:
        flash("Password must be at least 4 characters.", "error")
        return redirect(url_for("index"))

    # Save bot file if provided
    file_path = None

    if register_team(team_name, password, file_path):
        session["team"] = team_name
        flash(f"Team '{team_name}' registered successfully!", "success")
        return redirect(url_for("dashboard"))
    else:
        flash("Team name already taken. Try a different name, or login.", "error")
        return redirect(url_for("index"))


@app.route("/login", methods=["POST"])
def login():
    """Login an existing team."""
    team_name = request.form.get("team_name", "").strip()
    password = request.form.get("password", "")

    if not team_name or not password:
        flash("Please enter team name and password.", "error")
        return redirect(url_for("index"))

    if verify_team_password(team_name, password):
        session["team"] = team_name
        return redirect(url_for("dashboard"))
    else:
        flash("Invalid team name or password.", "error")
        return redirect(url_for("index"))


@app.route("/logout")
def logout():
    """Clear session."""
    session.pop("team", None)
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    """Team dashboard — upload bot, view stats & replays."""
    team_name = session.get("team")
    if not team_name:
        flash("Please login first.", "error")
        return redirect(url_for("index"))

    team = get_team(team_name)
    if team is None:
        session.pop("team", None)
        flash("Team not found.", "error")
        return redirect(url_for("index"))

    stats = get_team_stats(team_name)
    matches = get_team_matches(team_name, limit=20)
    submissions_open = get_setting("submissions_open", "1") == "1"
    return render_template(
        "dashboard.html",
        team=team,
        stats=stats,
        matches=matches,
        submissions_open=submissions_open,
    )


@app.route("/dashboard/upload", methods=["POST"])
def dashboard_upload():
    """Upload/update bot from dashboard."""
    team_name = session.get("team")
    if not team_name:
        flash("Please login first.", "error")
        return redirect(url_for("index"))

    if get_setting("submissions_open", "1") != "1":
        flash("Submissions are currently closed.", "error")
        return redirect(url_for("dashboard"))

    if "bot_file" not in request.files or not request.files["bot_file"].filename:
        flash("No file selected.", "error")
        return redirect(url_for("dashboard"))

    # RATE LIMITING: 5 minutes between uploads, but SKIP if this is their first upload
    team_data = get_team(team_name)
    has_uploaded_before = bool(team_data and team_data["file_path"])
    
    if has_uploaded_before and team_data["uploaded_at"]:
        try:
            # Datetime format from SQL is an ISO string: 'YYYY-MM-DDTHH:MM:SS.mmmmmm'
            last_upload = datetime.fromisoformat(team_data["uploaded_at"])
            now = datetime.now()
            diff = (now - last_upload).total_seconds()
            
            if diff < 300: # 5 minutes
                remaining = int(300 - diff)
                flash(f"Please wait {remaining} seconds before uploading another bot.", "error")
                return redirect(url_for("dashboard"))
        except Exception as e:
            print(f"Cooldown parse error: {e}")


    file = request.files["bot_file"]
    file_path = save_bot_file(team_name, file)
    if file_path is None:
        return redirect(url_for("dashboard"))

    if update_team_bot(team_name, file_path):
        flash("Bot uploaded/updated successfully!", "success")
        
        # Enqueue matches against all other active teams that have a bot
        all_teams = get_all_teams()
        opponents = [t["name"] for t in all_teams if t["name"] != team_name and t["file_path"]]
        
        with QUEUE_LOCK:
            # First, clear any old instances of this team from the queue
            global MATCH_QUEUE
            MATCH_QUEUE = [m for m in MATCH_QUEUE if m[0] != team_name and m[1] != team_name]
            
            # Then add new matches (2 against each opponent)
            for opp in opponents:
                MATCH_QUEUE.append((team_name, opp))
                MATCH_QUEUE.append((opp, team_name))
        
        flash(f"Enqueued {len(opponents) * 2} matches.", "info")
    else:
        flash("Error updating bot. Please try again.", "error")

    return redirect(url_for("dashboard"))


# ================================================================== #
#  LEADERBOARD ROUTES                                                 #
# ================================================================== #

@app.route("/leaderboard")
def leaderboard():
    """Rankings and recent matches."""
    rankings = get_leaderboard()
    recent_matches = get_matches(limit=20)
    logged_in_team = session.get("team")
    return render_template("leaderboard.html", rankings=rankings, matches=recent_matches, logged_in_team=logged_in_team)


@app.route("/match/<int:match_id>")
def match_detail(match_id):
    """Match replay page — only accessible to participants or admin."""
    match = get_match(match_id)
    if match is None:
        return "Match not found", 404

    # Allow admin via Basic Auth
    auth = request.authorization
    is_admin = auth and check_auth(auth.username, auth.password)

    # Allow participants via session
    team_name = session.get("team")
    is_participant = team_name and (team_name == match["team1"] or team_name == match["team2"])

    if not is_admin and not is_participant:
        return "Access denied — you can only view replays of matches you participated in.", 403

    moves = json.loads(match["moves"]) if match["moves"] else []
    return render_template(
        "match_detail.html",
        match=match,
        moves=moves,
        moves_json=json.dumps(moves),
    )


@app.route("/team/<name>")
def team_profile(name):
    """Team profile with stats and match history."""
    team = get_team(name)
    if team is None:
        return "Team not found", 404
    stats = get_team_stats(name)
    matches = get_team_matches(name, limit=50)
    logged_in_team = session.get("team")
    return render_template(
        "team_profile.html",
        team=team,
        stats=stats,
        matches=matches,
        logged_in_team=logged_in_team,
    )


# ================================================================== #
#  API ROUTES (JSON)                                                  #
# ================================================================== #

@app.route("/api/leaderboard")
def api_leaderboard():
    rankings = get_leaderboard()
    return jsonify([
        {
            "rank": i + 1,
            "team": r["team"],
            "wins": r["wins"],
            "losses": r["losses"],
            "draws": r["draws"],
            "points": r["points"],
        }
        for i, r in enumerate(rankings)
    ])


@app.route("/api/matches")
def api_matches():
    matches = get_matches(limit=20)
    return jsonify([
        {
            "id": m["id"],
            "team1": m["team1"],
            "team2": m["team2"],
            "winner": m["winner"],
            "result_desc": m["result_desc"],
            "played_at": m["played_at"],
        }
        for m in matches
    ])


@app.route("/api/team/<name>/matches")
def api_team_matches(name):
    matches = get_team_matches(name, limit=50)
    return jsonify([
        {
            "id": m["id"],
            "team1": m["team1"],
            "team2": m["team2"],
            "winner": m["winner"],
            "result_desc": m["result_desc"],
            "played_at": m["played_at"],
        }
        for m in matches
    ])


@app.route("/api/tournament-status")
@require_admin
def api_tournament_status():
    return jsonify(tournament_status)


# ================================================================== #
#  ADMIN ROUTES (password protected)                                  #
# ================================================================== #

@app.route("/admin")
@require_admin
def admin_panel():
    """Admin dashboard."""
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


@app.route("/admin/settings", methods=["POST"])
@require_admin
def admin_update_settings():
    submissions = request.form.get("submissions_open", "0")
    set_setting("submissions_open", submissions)

    move_timeout = request.form.get("move_timeout", "2")
    try:
        timeout_val = max(1, min(30, int(move_timeout)))
        set_setting("move_timeout", str(timeout_val))
    except ValueError:
        flash("Invalid move timeout value.", "error")
        return redirect(url_for("admin_panel"))

    max_moves = request.form.get("max_moves", "1000")
    try:
        moves_val = max(10, min(10000, int(max_moves)))
        set_setting("max_moves", str(moves_val))
    except ValueError:
        flash("Invalid max moves value.", "error")
        return redirect(url_for("admin_panel"))

    flash("Settings updated successfully!", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/team/<name>/toggle", methods=["POST"])
@require_admin
def admin_toggle_team(name):
    action = request.form.get("action", "deactivate")
    if action == "activate":
        activate_team(name)
        flash(f"Team '{name}' activated.", "success")
    else:
        deactivate_team(name)
        flash(f"Team '{name}' deactivated.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/reset-leaderboard", methods=["POST"])
@require_admin
def admin_reset_lb():
    reset_leaderboard()
    flash("Leaderboard has been reset to zero.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/clear-matches", methods=["POST"])
@require_admin
def admin_clear_matches():
    delete_all_matches()
    flash("All match history has been cleared.", "success")
    return redirect(url_for("admin_panel"))


@app.route("/admin/run-tournament", methods=["POST"])
@require_admin
def admin_run_tournament():
    if tournament_status["running"]:
        flash("A tournament is already running!", "error")
        return redirect(url_for("admin_panel"))

    def _run():
        tournament_status["running"] = True
        tournament_status["output"] = "Starting tournament...\n"
        try:
            script = os.path.join(os.path.dirname(__file__), "run_tournament.py")
            process = subprocess.Popen(
                [sys.executable, "-u", script, "--round-robin"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in process.stdout:
                tournament_status["output"] += line
            process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            tournament_status["output"] += "\nTournament timed out after 10 minutes."
        except Exception as e:
            tournament_status["output"] += f"\nError: {e}"
        finally:
            tournament_status["running"] = False

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    flash("Tournament started! Refresh to see progress.", "success")
    return redirect(url_for("admin_panel"))


# ================================================================== #
#  MAIN                                                               #
# ================================================================== #

@app.route("/admin/queue-status")
@require_admin
def admin_queue_status():
    with QUEUE_LOCK:
        current_running = None
        # We don't track currently running explicitly in a variable right now, 
        # but the queue size and pause state are available.
        return jsonify({
            "paused": QUEUE_PAUSED,
            "length": len(MATCH_QUEUE),
            "next_matches": MATCH_QUEUE[:5]
        })

@app.route("/admin/queue-toggle", methods=["POST"])
@require_admin
def admin_queue_toggle():
    global QUEUE_PAUSED
    with QUEUE_LOCK:
        QUEUE_PAUSED = not QUEUE_PAUSED
    return jsonify({"paused": QUEUE_PAUSED})

@app.route("/admin/queue-clear", methods=["POST"])
@require_admin
def admin_queue_clear():
    global MATCH_QUEUE
    with QUEUE_LOCK:
        MATCH_QUEUE.clear()
    return jsonify({"success": True})

if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  Bot Royale — Unified Server")
    print("  Running on http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
