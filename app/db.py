import sqlite3
from pathlib import Path
from flask import current_app, g


def get_db():
    if "db" not in g:
        path = Path(current_app.config["DATABASE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def migrate():
    db = get_db()
    root = Path(current_app.root_path).parent / "migrations"
    db.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    applied = {r[0] for r in db.execute("SELECT version FROM schema_migrations")}
    for file in sorted(root.glob("*.sql")):
        if file.name not in applied:
            db.executescript(file.read_text())
            db.execute("INSERT INTO schema_migrations(version) VALUES(?)", (file.name,))
            db.commit()


def init_app(app):
    @app.cli.command("db-migrate")
    def db_migrate():
        migrate()
        print("Database migrated.")

    @app.cli.command("seed-routine")
    def seed_routine():
        from .services import seed_user_routine
        db = get_db()
        users = db.execute("SELECT id FROM users").fetchall()
        if not users:
            raise SystemExit("Register a user first; this command never creates credentials.")
        for user in users:
            seed_user_routine(user["id"])
        print(f"Seeded routine for {len(users)} user(s).")

