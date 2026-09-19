import functools
import hashlib
import hmac
import secrets
from flask import abort, g, jsonify, redirect, request, session, url_for


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def check_csrf():
    supplied = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not supplied or not hmac.compare_digest(supplied, session.get("csrf_token", "")):
        abort(400, "invalid_csrf")


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if not g.get("user"):
            return redirect(url_for("auth.login", next=request.path))
        return view(**kwargs)
    return wrapped


def token_hash(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def json_error(code, message, details=None):
    payload = {"error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return jsonify(payload)
