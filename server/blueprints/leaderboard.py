"""
Leaderboard Blueprint — rankings, match history, team profiles, replays.
"""

import json
from flask import Blueprint, render_template, jsonify

from database import (
    get_leaderboard,
    get_matches,
    get_match,
    get_team,
    get_team_matches,
    get_team_stats,
)

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.route("/")
def index():
    rankings = get_leaderboard()
    recent_matches = get_matches(limit=20)
    return render_template("leaderboard.html", rankings=rankings, matches=recent_matches)


@leaderboard_bp.route("/api/leaderboard")
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


@leaderboard_bp.route("/api/matches")
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


@leaderboard_bp.route("/match/<int:match_id>")
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


@leaderboard_bp.route("/team/<name>")
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


@leaderboard_bp.route("/api/team/<name>/matches")
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
