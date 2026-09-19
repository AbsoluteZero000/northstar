from flask import Flask, g, request, session

from config import Config
from .db import close_db, init_app as init_db
from .i18n import TRANSLATIONS, t


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    app.config["JSON_SORT_KEYS"] = False
    app.jinja_env.globals.update(t=t)

    init_db(app)
    app.teardown_appcontext(close_db)

    from .auth import bp as auth_bp
    from .dashboard import bp as dashboard_bp
    from .api import bp as api_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def load_locale():
        g.locale = "en"
        if session.get("user_id"):
            from .db import get_db
            if session.get("session_uuid"):
                active=get_db().execute("SELECT * FROM user_sessions WHERE uuid=? AND user_id=? AND revoked_at IS NULL",(session["session_uuid"],session["user_id"])).fetchone()
                if not active:
                    session.clear(); g.user=None; return
                get_db().execute("UPDATE user_sessions SET last_seen_at=CURRENT_TIMESTAMP WHERE id=?",(active["id"],)); get_db().commit()
            user = get_db().execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
            g.user = user
            if user:
                g.locale = user["language"]
        else:
            g.user = None
            requested = request.accept_languages.best_match(["ar", "en"])
            g.locale = requested or "en"

    @app.context_processor
    def inject_locale():
        return {"locale": g.get("locale", "en"), "direction": "rtl" if g.get("locale") == "ar" else "ltr", "tr": TRANSLATIONS}

    return app
