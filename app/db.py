import sqlite3
import click
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

    @app.cli.command("configure-profile")
    @click.option("--email", required=True)
    @click.option("--name", required=True)
    def configure_profile(email, name):
        """Apply the documented personal work profile without handling credentials."""
        db=get_db(); user=db.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE",(email.strip(),)).fetchone()
        if not user: raise SystemExit("No user found for that email.")
        db.execute("UPDATE users SET display_name=?,timezone='Africa/Cairo',language='en',week_starts=0,workdays='0,1,2,3,4',work_start='09:00',work_end='17:00',outside_work_minutes=120,date_format='locale',friday_family_day=1,friday_weekly_review=1,updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE id=?",(name.strip(),user["id"]))
        palette={"spiritual":("#10b981",1),"marriage":("#f43f5e",2),"secops":("#3b82f6",3),"finance":("#d4a84f",4),"health":("#ef4444",5),"family_social":("#8b5cf6",6),"work":("#64748b",7),"personal":("#06b6d4",8)}
        for key,(color,position) in palette.items(): db.execute("UPDATE categories SET color=?,position=?,updated_at=CURRENT_TIMESTAMP,version=version+1 WHERE user_id=? AND name_key=?",(color,position,user["id"],key))
        db.commit(); print("Profile and categories updated.")

    @app.cli.command("seed-personal-plan")
    @click.option("--email", required=True)
    def seed_personal_plan_command(email):
        """Create Ahmed's dated 2026 plan for an existing account, idempotently."""
        from .personal_plan import seed_personal_plan
        user=get_db().execute("SELECT id FROM users WHERE email=? COLLATE NOCASE",(email.strip(),)).fetchone()
        if not user: raise SystemExit("No user found for that email.")
        result=seed_personal_plan(user["id"])
        print(result)
