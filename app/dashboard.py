import json
import secrets
from datetime import date, timedelta
from flask import Blueprint, Response, flash, g, jsonify, redirect, render_template, request, session, url_for
from .db import get_db
from .security import check_csrf, csrf_token, login_required, token_hash
from .services import audit, calculate_stats, new_uuid, now, owned, seed_user_routine, snapshot_template, template_snapshot, validate_goal_parent, weekly_reflection

bp=Blueprint("dashboard",__name__)

def weekday_sql(day): return str(day.weekday())

@bp.get("/")
def root(): return redirect(url_for("dashboard.today") if session.get("user_id") else url_for("auth.login"))

@bp.route("/today",methods=("GET","POST"))
@login_required
def today():
    db=get_db(); day=date.today().isoformat()
    if request.method=="POST":
        check_csrf(); title=request.form.get("title","").strip()
        if title:
            uid=new_uuid(); stamp=now(); db.execute("INSERT INTO tasks(uuid,user_id,title,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?)",(uid,g.user["id"],title,day,stamp,stamp)); audit(g.user["id"],"create","task",uid); db.commit()
        return redirect(url_for("dashboard.today"))
    tasks=db.execute("SELECT t.*,c.name category_name,c.color category_color FROM tasks t LEFT JOIN categories c ON c.id=t.category_id WHERE t.user_id=? AND t.due_date=? AND t.deleted_at IS NULL ORDER BY t.status='completed',t.scheduled_time,t.position",(g.user["id"],day)).fetchall()
    habits=db.execute("SELECT h.*,s.time_of_day,e.completed,e.uuid entry_uuid FROM habits h JOIN habit_schedules s ON s.habit_id=h.id LEFT JOIN habit_entries e ON e.habit_id=h.id AND e.entry_date=? AND e.deleted_at IS NULL WHERE h.user_id=? AND h.active=1 AND h.deleted_at IS NULL AND instr(s.weekdays,?)>0 ORDER BY s.time_of_day,h.id",(day,g.user["id"],weekday_sql(date.today()))).fetchall()
    template=db.execute("SELECT * FROM recap_templates WHERE user_id=? AND active=1 AND deleted_at IS NULL",(g.user["id"],)).fetchone()
    recap=db.execute("SELECT * FROM recaps WHERE user_id=? AND recap_date=? AND deleted_at IS NULL",(g.user["id"],day)).fetchone()
    answers={}
    if recap: answers={r["field_key"]:json.loads(r["answer_json"]) for r in db.execute("SELECT * FROM recap_answers WHERE recap_id=? AND deleted_at IS NULL",(recap["id"],))}
    fields=db.execute("SELECT * FROM recap_template_fields WHERE template_id=? AND active=1 AND deleted_at IS NULL ORDER BY position",(template["id"],)).fetchall() if template else []
    total=len(tasks)+len(habits); done=sum(t["status"]=="completed" for t in tasks)+sum(bool(h["completed"]) for h in habits)
    return render_template("today.html",tasks=tasks,habits=habits,template=template,fields=fields,recap=recap,answers=answers,day=day,progress=round(done*100/total) if total else 0,csrf_token=csrf_token())

@bp.get("/week")
@login_required
def week():
    offset=int(request.args.get("offset",0)); start=date.today()-timedelta(days=date.today().weekday())+timedelta(weeks=offset); end=start+timedelta(days=6); db=get_db()
    tasks=db.execute("SELECT t.*,c.color category_color FROM tasks t LEFT JOIN categories c ON c.id=t.category_id WHERE t.user_id=? AND t.due_date BETWEEN ? AND ? AND t.deleted_at IS NULL ORDER BY due_date,scheduled_time,position",(g.user["id"],start.isoformat(),end.isoformat())).fetchall()
    habits=db.execute("SELECT h.*,s.weekdays,s.time_of_day FROM habits h JOIN habit_schedules s ON s.habit_id=h.id WHERE h.user_id=? AND h.active=1 AND h.deleted_at IS NULL",(g.user["id"],)).fetchall()
    days=[]
    for n in range(7):
        d=start+timedelta(days=n); days.append({"date":d,"tasks":[x for x in tasks if x["due_date"]==d.isoformat()],"habits":[x for x in habits if str(d.weekday()) in x["weekdays"].split(",")]})
    return render_template("week.html",days=days,offset=offset,csrf_token=csrf_token())

@bp.route("/goals",methods=("GET","POST"))
@login_required
def goals():
    db=get_db()
    if request.method=="POST":
        check_csrf(); goal_type=request.form.get("type"); parent=request.form.get("parent_id") or None; error=validate_goal_parent(g.user["id"],goal_type,parent)
        if error: flash(error,"error")
        else:
            uid=new_uuid(); stamp=now(); db.execute("INSERT INTO goals(uuid,user_id,parent_id,type,title,description,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid,g.user["id"],parent,goal_type,request.form.get("title","").strip(),request.form.get("description",""),request.form.get("start_date") or None,request.form.get("end_date") or None,stamp,stamp)); audit(g.user["id"],"create","goal",uid); db.commit()
        return redirect(url_for("dashboard.goals"))
    items=[dict(r) for r in db.execute("SELECT g.*,c.name category_name,c.color category_color FROM goals g LEFT JOIN categories c ON c.id=g.category_id WHERE g.user_id=? AND g.deleted_at IS NULL ORDER BY g.position,g.created_at",(g.user["id"],))]
    return render_template("goals.html",goals=items,csrf_token=csrf_token())

@bp.get("/statistics")
@login_required
def statistics(): return render_template("stats.html",stats=calculate_stats(g.user["id"]),reflection=weekly_reflection(g.user["id"]),csrf_token=csrf_token())

@bp.route("/settings",methods=("GET","POST"))
@login_required
def settings():
    db=get_db(); revealed=None
    if request.method=="POST":
        check_csrf(); action=request.form.get("action")
        if action=="profile":
            lang=request.form.get("language"); tz=request.form.get("timezone","Africa/Cairo").strip(); name=request.form.get("display_name","").strip()
            if lang in ("ar","en") and tz:
                capacity=max(0,min(int(request.form.get("outside_work_minutes",120)),1440))
                workdays=sorted({int(day) for day in request.form.getlist("workdays") if day.isdigit() and 0<=int(day)<=6})
                if not workdays: workdays=[0,1,2,3,4]
                db.execute("UPDATE users SET display_name=?,language=?,timezone=?,week_starts=?,workdays=?,work_start=?,work_end=?,outside_work_minutes=?,date_format=?,friday_family_day=?,friday_weekly_review=?,updated_at=?,version=version+1 WHERE id=?",(name,lang,tz,int(request.form.get("week_starts",0)),",".join(map(str,workdays)),request.form.get("work_start","09:00"),request.form.get("work_end","17:00"),capacity,request.form.get("date_format","locale"),int(bool(request.form.get("friday_family_day"))),int(bool(request.form.get("friday_weekly_review"))),now(),g.user["id"])); db.commit(); return redirect(url_for("dashboard.settings"))
        elif action=="token":
            scopes=request.form.getlist("scopes"); allowed={"tasks:read","tasks:write","goals:read","goals:write","habits:read","habits:write","recaps:read","recaps:write","stats:read","resources:read","resources:write"}
            if set(scopes)<=allowed:
                secret="northstar_"+secrets.token_urlsafe(32); uid=new_uuid(); cur=db.execute("INSERT INTO api_tokens(uuid,user_id,name,token_prefix,token_hash,scopes,created_at,expires_at) VALUES(?,?,?,?,?,?,?,?)",(uid,g.user["id"],request.form.get("name","Agent")[:80],secret[:12],token_hash(secret)," ".join(scopes),now(),request.form.get("expires_at") or None)); audit(g.user["id"],"create","api_token",uid,{"scopes":scopes}); db.commit(); revealed=secret
        elif action=="revoke_token":
            token=owned("api_tokens",request.form.get("token_id"),g.user["id"],True)
            if token: db.execute("UPDATE api_tokens SET revoked_at=? WHERE id=?",(now(),token["id"])); audit(g.user["id"],"revoke","api_token",token["uuid"]); db.commit()
        elif action=="seed": seed_user_routine(g.user["id"])
        elif action=="category_create":
            name=request.form.get("name","").strip()
            if name:
                db.execute("INSERT INTO categories(uuid,user_id,name,color,icon,position,updated_at) VALUES(?,?,?,?,?,?,?)",(new_uuid(),g.user["id"],name,request.form.get("color","#64748b"),request.form.get("icon","tag"),99,now())); db.commit()
        elif action=="habit_create":
            en=request.form.get("name_en","").strip(); ar=request.form.get("name_ar",en).strip(); stamp=now()
            if en:
                cur=db.execute("INSERT INTO habits(uuid,user_id,name_en,name_ar,created_at,updated_at) VALUES(?,?,?,?,?,?)",(new_uuid(),g.user["id"],en,ar,stamp,stamp)); db.execute("INSERT INTO habit_schedules(uuid,habit_id,weekdays,time_of_day,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),cur.lastrowid,request.form.get("weekdays","0,1,2,3,4,5,6"),request.form.get("time_of_day") or None,stamp)); db.commit()
        elif action=="template":
            tid=int(request.form["template_id"]); template=db.execute("SELECT * FROM recap_templates WHERE id=? AND user_id=?",(tid,g.user["id"])).fetchone()
            if template:
                stamp=now(); db.execute("UPDATE recap_templates SET name_en=?,name_ar=?,intro_en=?,intro_ar=?,current_version=current_version+1,version=version+1,updated_at=? WHERE id=?",(request.form.get("name_en",template["name_en"]),request.form.get("name_ar",template["name_ar"]),request.form.get("intro_en",template["intro_en"]),request.form.get("intro_ar",template["intro_ar"]),stamp,tid)); snapshot_template(tid); db.commit()
        elif action=="template_field":
            fid=int(request.form["field_id"]); field=db.execute("SELECT f.*,t.user_id FROM recap_template_fields f JOIN recap_templates t ON t.id=f.template_id WHERE f.id=? AND t.user_id=?",(fid,g.user["id"])).fetchone()
            if field:
                stamp=now(); db.execute("UPDATE recap_template_fields SET label_en=?,label_ar=?,placeholder_en=?,placeholder_ar=?,field_type=?,required=?,active=?,position=?,updated_at=?,version=version+1 WHERE id=?",(request.form.get("label_en",""),request.form.get("label_ar",""),request.form.get("placeholder_en",""),request.form.get("placeholder_ar",""),request.form.get("field_type","long_text"),int(bool(request.form.get("required"))),int(bool(request.form.get("active"))),int(request.form.get("position",0)),stamp,fid)); db.execute("UPDATE recap_templates SET current_version=current_version+1,updated_at=? WHERE id=?",(stamp,field["template_id"])); snapshot_template(field["template_id"]); db.commit()
        elif action=="restore":
            table={"goal":"goals","task":"tasks"}.get(request.form.get("kind")); uid=request.form.get("uuid")
            if table:
                row=owned(table,uid,g.user["id"],True)
                if row: db.execute(f"UPDATE {table} SET deleted_at=NULL,updated_at=?,version=version+1 WHERE id=?",(now(),row["id"])); audit(g.user["id"],"restore",request.form.get("kind"),uid); db.commit()
        elif action=="revoke_session":
            sid=request.form.get("session_uuid")
            db.execute("UPDATE user_sessions SET revoked_at=? WHERE uuid=? AND user_id=?",(now(),sid,g.user["id"])); audit(g.user["id"],"revoke","session",sid); db.commit()
    tokens=db.execute("SELECT * FROM api_tokens WHERE user_id=? ORDER BY created_at DESC",(g.user["id"],)).fetchall()
    categories=db.execute("SELECT * FROM categories WHERE user_id=? AND deleted_at IS NULL ORDER BY position",(g.user["id"],)).fetchall()
    audits=db.execute("SELECT * FROM audit_events WHERE user_id=? ORDER BY created_at DESC LIMIT 30",(g.user["id"],)).fetchall()
    trash=db.execute("SELECT 'goal' kind,uuid,title,deleted_at FROM goals WHERE user_id=? AND deleted_at IS NOT NULL UNION ALL SELECT 'task',uuid,title,deleted_at FROM tasks WHERE user_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC",(g.user["id"],g.user["id"])).fetchall()
    habits=db.execute("SELECT h.*,s.weekdays,s.time_of_day FROM habits h LEFT JOIN habit_schedules s ON s.habit_id=h.id WHERE h.user_id=? AND h.deleted_at IS NULL ORDER BY h.id",(g.user["id"],)).fetchall()
    template=db.execute("SELECT * FROM recap_templates WHERE user_id=? AND active=1 AND deleted_at IS NULL",(g.user["id"],)).fetchone()
    template_fields=db.execute("SELECT * FROM recap_template_fields WHERE template_id=? AND deleted_at IS NULL ORDER BY position",(template["id"],)).fetchall() if template else []
    sessions=db.execute("SELECT * FROM user_sessions WHERE user_id=? ORDER BY last_seen_at DESC",(g.user["id"],)).fetchall()
    return render_template("settings.html",tokens=tokens,categories=categories,habits=habits,template=template,template_fields=template_fields,sessions=sessions,audits=audits,trash=trash,revealed=revealed,csrf_token=csrf_token())

@bp.get("/settings/export.json")
@login_required
def export_data():
    db=get_db(); data={}
    for table in ("categories","tags","goals","tasks","habits","habit_entries","recaps","resources","audit_events"):
        # Recap answers are nested only in the private authenticated export, never in telemetry or logs.
        data[table]=[dict(r) for r in db.execute(f"SELECT * FROM {table} WHERE user_id=?",(g.user["id"],))]
    recaps={r["id"] for r in db.execute("SELECT id FROM recaps WHERE user_id=?",(g.user["id"],))}
    data["recap_answers"]=[dict(r) for r in db.execute(f"SELECT * FROM recap_answers WHERE recap_id IN ({','.join('?' for _ in recaps)})",tuple(recaps))] if recaps else []
    return Response(json.dumps(data,ensure_ascii=False,indent=2),mimetype="application/json",headers={"Content-Disposition":"attachment; filename=northstar-export.json"})

@bp.get("/api-docs")
def api_docs(): return render_template("api_docs.html")

@bp.get("/offline")
def offline(): return render_template("offline.html")
