"""
Leaderboard Server — Port 5001
Shows rankings, match history, team profiles, and game replays.
"""

import os
import sys
import json
from flask import Flask, render_template, jsonify

sys.path.insert(0, os.path.dirname(__file__))
from database import (
    init_db,
    get_leaderboard,
    get_matches,
    get_match,
    get_team,
    get_team_matches,
    get_team_stats,
)

app = Flask(__name__)


@app.route("/")
def index():
    rankings = get_leaderboard()
    recent_matches = get_matches(limit=20)
    return render_template("leaderboard.html", rankings=rankings, matches=recent_matches)


@app.route("/api/leaderboard")
def api_leaderboard():
    """JSON endpoint for auto-refresh."""
    rankings = get_leaderboard()
    return jsonify(
        [
            {
                "rank": i + 1,
                "team": r["team"],
                "wins": r["wins"],
                "losses": r["losses"],
                "draws": r["draws"],
                "points": r["points"],
            }
            for i, r in enumerate(rankings)
        ]
    )


@app.route("/api/matches")
def api_matches():
    """JSON endpoint for auto-refresh."""
    matches = get_matches(limit=20)
    return jsonify(
        [
            {
                "id": m["id"],
                "team1": m["team1"],
                "team2": m["team2"],
                "winner": m["winner"],
                "result_desc": m["result_desc"],
                "played_at": m["played_at"],
            }
            for m in matches
        ]
    )


@app.route("/match/<int:match_id>")
def match_detail(match_id):
    match = get_match(match_id)
    if match is None:
        return "Match not found", 404
    moves = json.loads(match["moves"]) if match["moves"] else []
    return render_template(
        "match_detail.html",
        match=match,
        moves=moves,
        moves_json=json.dumps(moves),
    )


@app.route("/team/<name>")
def team_profile(name):
    """Team profile page with stats and match history."""
    team = get_team(name)
    if team is None:
        return "Team not found", 404
    stats = get_team_stats(name)
    matches = get_team_matches(name, limit=50)
    return render_template(
        "team_profile.html",
        team=team,
        stats=stats,
        matches=matches,
    )


@app.route("/api/team/<name>/matches")
def api_team_matches(name):
    """JSON endpoint for team match history."""
    matches = get_team_matches(name, limit=50)
    return jsonify(
        [
            {
                "id": m["id"],
                "team1": m["team1"],
                "team2": m["team2"],
                "winner": m["winner"],
                "result_desc": m["result_desc"],
                "played_at": m["played_at"],
            }
            for m in matches
        ]
    )


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  Bot Royale — Leaderboard Server")
    print("  Running on http://0.0.0.0:5001")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5001, debug=True)
