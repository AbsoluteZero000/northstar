import uuid
from datetime import datetime, timezone
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db
from .security import check_csrf, csrf_token, login_required
from .services import now, provision_user

bp=Blueprint("auth",__name__,url_prefix="/auth")

@bp.route("/register",methods=("GET","POST"))
def register():
    if request.method=="POST":
        check_csrf(); email=request.form.get("email","").strip().lower(); password=request.form.get("password",""); language=request.form.get("language","en")
        error=None
        if "@" not in email or len(email)>254: error="Enter a valid email address."
        elif len(password)<10: error="Password must contain at least 10 characters."
        elif language not in ("ar","en"): error="Invalid language."
        if not error:
            db=get_db(); stamp=now()
            try:
                cur=db.execute("INSERT INTO users(uuid,email,password_hash,language,created_at,updated_at) VALUES(?,?,?,?,?,?)",(str(uuid.uuid4()),email,generate_password_hash(password),language,stamp,stamp))
                provision_user(cur.lastrowid); session.clear(); session["user_id"]=cur.lastrowid; session.permanent=True; return redirect(url_for("dashboard.today"))
            except Exception as exc:
                if "UNIQUE" in str(exc): error="An account with that email already exists."
                else: raise
        flash(error,"error")
    return render_template("auth/register.html",csrf_token=csrf_token())

@bp.route("/login",methods=("GET","POST"))
def login():
    if request.method=="POST":
        check_csrf(); user=get_db().execute("SELECT * FROM users WHERE email=? AND deleted_at IS NULL",(request.form.get("email","").strip().lower(),)).fetchone()
        if not user or not check_password_hash(user["password_hash"],request.form.get("password","")):
            flash("invalid_login","error")
        else:
            session.clear(); session["user_id"]=user["id"]; session.permanent=True
            return redirect(request.args.get("next") or url_for("dashboard.today"))
    return render_template("auth/login.html",csrf_token=csrf_token())

@bp.post("/logout")
@login_required
def logout():
    check_csrf(); session.clear()
    response=redirect(url_for("auth.login")); response.headers["Clear-Site-Data"]='"storage"'; return response
