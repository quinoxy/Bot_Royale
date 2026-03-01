"""
Bot Royale — Static Tournament Viewer
======================================
Flask application:
  /              — Leaderboard (final tournament results)
  /replays       — Game replays with team search & real-time playback
  /replays/<id>  — Individual game replay
  /bots          — Download bot source code
"""

import os
import json
import glob

from flask import Flask, render_template, jsonify, abort, send_file

app = Flask(__name__)

# ── Locate tournament data ────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOURNAMENT_LOGS_DIR = os.path.join(BASE_DIR, "..", "tournament_logs")


def _find_latest_timestamp():
    """Find the latest tournament timestamp from leaderboard files."""
    pattern = os.path.join(TOURNAMENT_LOGS_DIR, "leaderboard_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    # Extract timestamp from filename like leaderboard_20260228_232808.json
    basename = os.path.basename(files[-1])
    # "leaderboard_20260228_232808.json" → "20260228_232808"
    ts = basename.replace("leaderboard_", "").replace(".json", "")
    return ts


TIMESTAMP = _find_latest_timestamp()


def _load_leaderboard():
    if not TIMESTAMP:
        return []
    path = os.path.join(TOURNAMENT_LOGS_DIR, f"leaderboard_{TIMESTAMP}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _load_tournament_summary():
    if not TIMESTAMP:
        return []
    path = os.path.join(TOURNAMENT_LOGS_DIR, f"tournament_{TIMESTAMP}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def _get_games_dir():
    if not TIMESTAMP:
        return None
    d = os.path.join(TOURNAMENT_LOGS_DIR, f"games_{TIMESTAMP}")
    return d if os.path.isdir(d) else None


def _load_game_index():
    """Build an index of all games from the tournament summary."""
    summary = _load_tournament_summary()
    games = []
    for i, entry in enumerate(summary):
        if entry is None:
            continue
        games.append({
            "id": i,
            "red_bot": entry.get("red_bot", ""),
            "blue_bot": entry.get("blue_bot", ""),
            "winner": entry.get("winner", ""),
            "reason": entry.get("reason", ""),
            "total_moves": entry.get("total_moves", 0),
            "num_moves": entry.get("num_moves", 0),
            "log_file": entry.get("log_file", ""),
            "red_time_remaining": entry.get("red_time_remaining", 0),
            "blue_time_remaining": entry.get("blue_time_remaining", 0),
        })
    return games


def _get_all_team_names():
    """Get sorted list of unique team names from the leaderboard."""
    lb = _load_leaderboard()
    return sorted([entry[0] for entry in lb])


BOTS_DIR = os.path.join(BASE_DIR, "..", "bots")


def _load_bot_index():
    """Build an index of bot files, matched with leaderboard rank."""
    bots = []
    for i, (name, stats) in enumerate(LEADERBOARD):
        filename = f"{name}.py"
        filepath = os.path.join(BOTS_DIR, filename)
        if os.path.isfile(filepath):
            bots.append({
                "name": name,
                "filename": filename,
                "rank": i + 1,
                "wins": stats.get("wins", 0) if isinstance(stats, dict) else getattr(stats, "wins", 0),
                "losses": stats.get("losses", 0) if isinstance(stats, dict) else getattr(stats, "losses", 0),
                "size": os.path.getsize(filepath),
            })
    return bots


# Cache data at startup
LEADERBOARD = _load_leaderboard()
GAME_INDEX = _load_game_index()
TEAM_NAMES = _get_all_team_names()
BOT_INDEX = _load_bot_index()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def leaderboard():
    return render_template("leaderboard.html", leaderboard=LEADERBOARD)


@app.route("/replays")
def replays():
    return render_template("replays.html", games=GAME_INDEX, team_names=TEAM_NAMES)


@app.route("/replays/<int:game_id>")
def replay_detail(game_id):
    """Serve the replay page for a specific game."""
    # Find the game in the index
    game_meta = None
    for g in GAME_INDEX:
        if g["id"] == game_id:
            game_meta = g
            break
    if game_meta is None:
        abort(404)

    return render_template("replay_detail.html", game=game_meta)


@app.route("/bots")
def bots():
    return render_template("bots.html", bots=BOT_INDEX, team_names=TEAM_NAMES)


@app.route("/bots/<name>/download")
def download_bot(name):
    """Download a bot's source code."""
    # Validate the name exists in our index
    bot = None
    for b in BOT_INDEX:
        if b["name"] == name:
            bot = b
            break
    if bot is None:
        abort(404)

    filepath = os.path.join(BOTS_DIR, bot["filename"])
    if not os.path.isfile(filepath):
        abort(404)

    return send_file(filepath, as_attachment=True, download_name=bot["filename"])


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/leaderboard")
def api_leaderboard():
    return jsonify(LEADERBOARD)


@app.route("/api/games")
def api_games():
    return jsonify(GAME_INDEX)


@app.route("/api/games/<int:game_id>")
def api_game_detail(game_id):
    """Return the full game log (including all moves) for replay."""
    game_meta = None
    for g in GAME_INDEX:
        if g["id"] == game_id:
            game_meta = g
            break
    if game_meta is None:
        abort(404)

    games_dir = _get_games_dir()
    if not games_dir or not game_meta.get("log_file"):
        abort(404)

    log_path = os.path.join(games_dir, game_meta["log_file"])
    if not os.path.exists(log_path):
        abort(404)

    with open(log_path) as f:
        game_data = json.load(f)

    return jsonify(game_data)


@app.route("/api/teams")
def api_teams():
    return jsonify(TEAM_NAMES)


@app.route("/api/bots")
def api_bots():
    return jsonify(BOT_INDEX)


@app.route("/api/bots/<name>/source")
def api_bot_source(name):
    """Return bot source code as plain text for preview."""
    bot = None
    for b in BOT_INDEX:
        if b["name"] == name:
            bot = b
            break
    if bot is None:
        abort(404)

    filepath = os.path.join(BOTS_DIR, bot["filename"])
    if not os.path.isfile(filepath):
        abort(404)

    with open(filepath, "r") as f:
        source = f.read()

    return source, 200, {"Content-Type": "text/plain; charset=utf-8"}


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  Bot Royale — Tournament Viewer")
    print(f"  Tournament data: {TIMESTAMP or 'NOT FOUND'}")
    print(f"  Games indexed: {len(GAME_INDEX)}")
    print(f"  Teams: {len(TEAM_NAMES)}")
    print("  Running on http://0.0.0.0:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)
