"""
SQLite database layer for Bot Royale.
Tables: teams, matches, leaderboard.
"""

import sqlite3
import os
import json
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_royale.db")


def get_db():
    """Return a new connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT    UNIQUE NOT NULL,
            password_hash TEXT,
            file_path     TEXT,
            uploaded_at   TEXT    NOT NULL,
            active        INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            team1       TEXT    NOT NULL,
            team2       TEXT    NOT NULL,
            winner      TEXT,                -- NULL = draw, team name = winner, 'DQ:teamname' = disqualification
            result_desc TEXT,                -- human-readable result
            moves       TEXT,                -- JSON array of moves for replay
            played_at   TEXT    NOT NULL,
            FOREIGN KEY (team1) REFERENCES teams(name),
            FOREIGN KEY (team2) REFERENCES teams(name)
        );

        CREATE TABLE IF NOT EXISTS leaderboard (
            team        TEXT    PRIMARY KEY,
            wins        INTEGER DEFAULT 0,
            losses      INTEGER DEFAULT 0,
            draws       INTEGER DEFAULT 0,
            points      INTEGER DEFAULT 0,   -- 3 for win, 1 for draw, 0 for loss
            FOREIGN KEY (team) REFERENCES teams(name)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key         TEXT    PRIMARY KEY,
            value       TEXT    NOT NULL
        );
        """
    )
    # Migration: add password_hash column if it doesn't exist (for existing DBs)
    try:
        conn.execute("ALTER TABLE teams ADD COLUMN password_hash TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists

    # Seed default settings if they don't exist
    defaults = {
        "submissions_open": "1",
        "move_timeout": "2",
        "max_moves": "1000",
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
#  Settings helpers                                                   #
# ------------------------------------------------------------------ #

def get_setting(key: str, default=None):
    """Get a single setting value by key."""
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    """Set a setting value (upsert)."""
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def get_all_settings() -> dict:
    """Return all settings as a dict."""
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


# ------------------------------------------------------------------ #
#  Team helpers                                                       #
# ------------------------------------------------------------------ #

def register_team(name: str, password: str, file_path: str = None) -> bool:
    """Register a new team with a password. Returns True on success, False if name taken."""
    conn = get_db()
    now = datetime.now().isoformat()
    pw_hash = generate_password_hash(password)
    try:
        conn.execute(
            """
            INSERT INTO teams (name, password_hash, file_path, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, pw_hash, file_path or "", now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO leaderboard (team) VALUES (?)",
            (name,),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # team name already taken
    except sqlite3.Error as e:
        print(f"DB error: {e}")
        return False
    finally:
        conn.close()


def verify_team_password(name: str, password: str) -> bool:
    """Verify a team's password. Returns True if valid."""
    conn = get_db()
    row = conn.execute(
        "SELECT password_hash FROM teams WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    if row is None or row["password_hash"] is None:
        return False
    return check_password_hash(row["password_hash"], password)


def update_team_bot(name: str, file_path: str) -> bool:
    """Update a team's bot file. Returns True on success."""
    conn = get_db()
    now = datetime.now().isoformat()
    try:
        conn.execute(
            "UPDATE teams SET file_path = ?, uploaded_at = ?, active = 1 WHERE name = ?",
            (file_path, now, name),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"DB error: {e}")
        return False
    finally:
        conn.close()


def get_team(name: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM teams WHERE name = ?", (name,)).fetchone()
    conn.close()
    return row


def get_all_teams():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM teams WHERE active = 1 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def get_teams_with_stats():
    """Return all active teams joined with their leaderboard stats."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT t.name, t.uploaded_at,
               COALESCE(l.wins, 0)   AS wins,
               COALESCE(l.losses, 0) AS losses,
               COALESCE(l.draws, 0)  AS draws,
               COALESCE(l.points, 0) AS points
        FROM teams t
        LEFT JOIN leaderboard l ON t.name = l.team
        WHERE t.active = 1
        ORDER BY t.name
        """
    ).fetchall()
    conn.close()
    return rows


def get_all_teams_including_inactive():
    """Return all teams regardless of active status (for admin)."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM teams ORDER BY name").fetchall()
    conn.close()
    return rows


def deactivate_team(name: str):
    """Set team active = 0."""
    conn = get_db()
    conn.execute("UPDATE teams SET active = 0 WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def activate_team(name: str):
    """Set team active = 1."""
    conn = get_db()
    conn.execute("UPDATE teams SET active = 1 WHERE name = ?", (name,))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
#  Match helpers                                                      #
# ------------------------------------------------------------------ #

def record_match(team1: str, team2: str, winner, result_desc: str, moves: list):
    """Save a completed match."""
    conn = get_db()
    now = datetime.now().isoformat()
    conn.execute(
        """
        INSERT INTO matches (team1, team2, winner, result_desc, moves, played_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (team1, team2, winner, result_desc, json.dumps(moves), now),
    )

    # Update leaderboard
    if winner is None:
        # Draw
        conn.execute(
            "UPDATE leaderboard SET draws = draws + 1, points = points + 1 WHERE team = ?",
            (team1,),
        )
        conn.execute(
            "UPDATE leaderboard SET draws = draws + 1, points = points + 1 WHERE team = ?",
            (team2,),
        )
    elif winner.startswith("DQ:"):
        # Disqualification — the DQ'd team loses, the other wins
        dq_team = winner.split(":", 1)[1]
        win_team = team2 if dq_team == team1 else team1
        conn.execute(
            "UPDATE leaderboard SET wins = wins + 1, points = points + 3 WHERE team = ?",
            (win_team,),
        )
        conn.execute(
            "UPDATE leaderboard SET losses = losses + 1 WHERE team = ?",
            (dq_team,),
        )
    else:
        loser = team2 if winner == team1 else team1
        conn.execute(
            "UPDATE leaderboard SET wins = wins + 1, points = points + 3 WHERE team = ?",
            (winner,),
        )
        conn.execute(
            "UPDATE leaderboard SET losses = losses + 1 WHERE team = ?",
            (loser,),
        )

    conn.commit()
    conn.close()


def get_leaderboard():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT team, wins, losses, draws, points
        FROM leaderboard
        ORDER BY points DESC, wins DESC, team ASC
        """
    ).fetchall()
    conn.close()
    return rows


def get_matches(limit=50):
    conn = get_db()
    rows = conn.execute(
        "SELECT id, team1, team2, winner, result_desc, played_at FROM matches ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return rows


def get_match(match_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM matches WHERE id = ?", (match_id,)).fetchone()
    conn.close()
    return row


def get_team_matches(team_name: str, limit=50):
    """Get matches where team was team1 or team2."""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, team1, team2, winner, result_desc, played_at
        FROM matches
        WHERE team1 = ? OR team2 = ?
        ORDER BY id DESC LIMIT ?
        """,
        (team_name, team_name, limit),
    ).fetchall()
    conn.close()
    return rows


def get_team_stats(team_name: str):
    """Get leaderboard stats for a single team."""
    conn = get_db()
    row = conn.execute(
        "SELECT team, wins, losses, draws, points FROM leaderboard WHERE team = ?",
        (team_name,),
    ).fetchone()
    conn.close()
    return row


def reset_leaderboard():
    """Zero out all leaderboard stats."""
    conn = get_db()
    conn.execute("UPDATE leaderboard SET wins = 0, losses = 0, draws = 0, points = 0")
    conn.commit()
    conn.close()


def delete_all_matches():
    """Delete all match records."""
    conn = get_db()
    conn.execute("DELETE FROM matches")
    conn.commit()
    conn.close()


def get_match_count():
    """Return total number of matches."""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM matches").fetchone()
    conn.close()
    return row["cnt"]


def get_team_count():
    """Return number of active teams."""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM teams WHERE active = 1").fetchone()
    conn.close()
    return row["cnt"]
