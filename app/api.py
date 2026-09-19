import functools, json
from datetime import date, datetime, timedelta, timezone
from flask import Blueprint, current_app, g, jsonify, request, session
from .db import get_db
from .security import check_csrf, json_error, token_hash
from .services import audit, calculate_stats, new_uuid, now, owned, snapshot_template, task_would_cycle, template_snapshot, validate_goal_parent, DEFAULT_FIELDS

bp=Blueprint("api",__name__,url_prefix="/api")

def record(row): return dict(row) if row else None
def body(): return request.get_json(silent=True) or {}

def auth(required_scope=None):
 def deco(view):
  @functools.wraps(view)
  def wrapped(*args,**kwargs):
   db=get_db(); header=request.headers.get("Authorization","")
   if header.startswith("Bearer "):
    token=db.execute("SELECT * FROM api_tokens WHERE token_hash=?",(token_hash(header[7:]),)).fetchone()
    expired=token and token["expires_at"] and datetime.fromisoformat(token["expires_at"]).replace(tzinfo=timezone.utc)<=datetime.now(timezone.utc)
    if not token or token["revoked_at"] or expired: return json_error("unauthorized","Invalid, expired or revoked token."),401
    if required_scope and required_scope not in token["scopes"].split(): return json_error("insufficient_scope",f"Required scope: {required_scope}"),403
    g.api_user_id=token["user_id"]; g.actor_type="agent"; g.token_id=token["id"]; db.execute("UPDATE api_tokens SET last_used_at=? WHERE id=?",(now(),token["id"])); db.commit()
   elif session.get("user_id"):
    g.api_user_id=session["user_id"]; g.actor_type="user"; g.token_id=None
    if request.method not in ("GET","HEAD","OPTIONS"): check_csrf()
   else: return json_error("unauthorized","Authentication required."),401
   return view(*args,**kwargs)
  return wrapped
 return deco

def list_rows(table,where="",args=()):
 limit=min(max(int(request.args.get("limit",50)),1),200); offset=max(int(request.args.get("offset",0)),0)
 sql=f"SELECT * FROM {table} WHERE user_id=? AND deleted_at IS NULL"+where+" ORDER BY updated_at DESC LIMIT ? OFFSET ?"
 rows=[record(r) for r in get_db().execute(sql,(g.api_user_id,*args,limit,offset))]
 return jsonify({"data":rows,"pagination":{"limit":limit,"offset":offset,"count":len(rows)}})

@bp.get("/openapi.json")
def openapi():
 return current_app.send_static_file("openapi.json")

@bp.get("/v1/today")
@auth("tasks:read")
def today():
 day=request.args.get("date",date.today().isoformat()); db=get_db()
 tasks=[record(r) for r in db.execute("SELECT * FROM tasks WHERE user_id=? AND due_date=? AND deleted_at IS NULL",(g.api_user_id,day))]
 habits=[record(r) for r in db.execute("SELECT h.*,e.completed FROM habits h LEFT JOIN habit_entries e ON e.habit_id=h.id AND e.entry_date=? AND e.deleted_at IS NULL WHERE h.user_id=? AND h.deleted_at IS NULL",(day,g.api_user_id))]
 return jsonify({"data":{"date":day,"tasks":tasks,"habits":habits}})

@bp.get("/v1/week")
@auth("tasks:read")
def week():
 start=date.fromisoformat(request.args.get("start",(date.today()-timedelta(days=date.today().weekday())).isoformat())); end=start+timedelta(days=6)
 rows=[record(r) for r in get_db().execute("SELECT * FROM tasks WHERE user_id=? AND due_date BETWEEN ? AND ? AND deleted_at IS NULL ORDER BY due_date,scheduled_time",(g.api_user_id,start.isoformat(),end.isoformat()))]
 return jsonify({"data":{"start":start.isoformat(),"end":end.isoformat(),"tasks":rows}})

@bp.get("/v1/goals")
@auth("goals:read")
def goals_list(): return list_rows("goals")

def goal_tree_data():
 rows=[record(r) for r in get_db().execute("SELECT * FROM goals WHERE user_id=? AND deleted_at IS NULL ORDER BY position,created_at",(g.api_user_id,))]; by_parent={}
 for r in rows: by_parent.setdefault(r["parent_id"],[]).append(r)
 def build(item): item["children"]=[build(x) for x in by_parent.get(item["id"],[])]; return item
 return [build(x) for x in by_parent.get(None,[])]

@bp.get("/v1/goals/tree")
@auth("goals:read")
def goals_tree(): return jsonify({"data":goal_tree_data()})

@bp.post("/v1/goals/tree")
@auth("goals:write")
def goals_tree_create():
 payload=body(); roots=payload.get("goals",[]); db=get_db(); created=[]
 def add(node,parent_id=None):
  err=validate_goal_parent(g.api_user_id,node.get("type"),parent_id)
  if err: raise ValueError(err)
  title=str(node.get("title","")).strip()
  if not title: raise ValueError("title_required")
  uid=node.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO goals(uuid,user_id,parent_id,type,title,description,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,parent_id,node["type"],title,node.get("description",""),node.get("start_date"),node.get("end_date"),stamp,stamp)); created.append(uid)
  for child in node.get("children",[]): add(child,cur.lastrowid)
 try:
  db.execute("BEGIN")
  for root in roots: add(root)
  for uid in created: audit(g.api_user_id,"create","goal",uid)
  db.commit()
 except (ValueError,Exception) as exc:
  db.rollback(); code=str(exc) if isinstance(exc,ValueError) else "invalid_hierarchy"; return json_error("validation_error",code),422
 return jsonify({"data":{"created":created,"tree":goal_tree_data()}}),201

@bp.post("/v1/goals")
@auth("goals:write")
def goal_create():
 p=body(); err=validate_goal_parent(g.api_user_id,p.get("type"),p.get("parent_id"))
 if err:return json_error("validation_error",err),422
 if not str(p.get("title","")).strip():return json_error("validation_error","title_required"),422
 db=get_db(); uid=p.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO goals(uuid,user_id,parent_id,type,title,description,category_id,start_date,end_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,p.get("parent_id"),p["type"],p["title"].strip(),p.get("description",""),p.get("category_id"),p.get("start_date"),p.get("end_date"),stamp,stamp)); audit(g.api_user_id,"create","goal",uid); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM goals WHERE id=?",(cur.lastrowid,)).fetchone())}),201

@bp.route("/v1/goals/<ident>",methods=("GET","PATCH","DELETE"))
@auth()
def goal_item(ident):
 row=owned("goals",ident,g.api_user_id,request.method in ("PATCH","DELETE"))
 if not row:return json_error("not_found","Goal not found."),404
 required="goals:read" if request.method=="GET" else "goals:write"
 if g.actor_type=="agent":
  scopes=get_db().execute("SELECT scopes FROM api_tokens WHERE id=?",(g.token_id,)).fetchone()[0].split()
  if required not in scopes:return json_error("insufficient_scope",f"Required scope: {required}"),403
 if request.method=="GET":return jsonify({"data":record(row)})
 db=get_db(); p=body()
 if request.method=="DELETE": db.execute("UPDATE goals SET deleted_at=?,updated_at=?,version=version+1 WHERE id=?",(now(),now(),row["id"])); action="delete"
 else:
  if "type" in p or "parent_id" in p:
   err=validate_goal_parent(g.api_user_id,p.get("type",row["type"]),p.get("parent_id",row["parent_id"]))
   if err:return json_error("validation_error",err),422
  fields=[x for x in ("title","description","status","position","start_date","end_date","parent_id","category_id","archived_at","deleted_at") if x in p]
  if not fields:return jsonify({"data":record(row)})
  db.execute(f"UPDATE goals SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1 WHERE id=?",(*[p[x] for x in fields],now(),row["id"])); action="update"
 audit(g.api_user_id,action,"goal",row["uuid"],{"fields":list(p)}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM goals WHERE id=?",(row["id"],)).fetchone())})

@bp.get("/v1/tasks")
@auth("tasks:read")
def tasks_list():
 where=""; args=[]
 for key in ("due_date","status","goal_id","parent_task_id"):
  if request.args.get(key): where+=f" AND {key}=?"; args.append(request.args[key])
 return list_rows("tasks",where,args)

@bp.post("/v1/tasks")
@auth("tasks:write")
def task_create():
 p=body(); title=str(p.get("title","")).strip()
 if not title:return json_error("validation_error","title_required"),422
 if p.get("goal_id") and not owned("goals",p["goal_id"],g.api_user_id):return json_error("validation_error","goal_not_found"),422
 if p.get("parent_task_id") and not owned("tasks",p["parent_task_id"],g.api_user_id):return json_error("validation_error","parent_not_found"),422
 db=get_db(); uid=p.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO tasks(uuid,user_id,goal_id,parent_task_id,category_id,title,description,status,priority,due_date,scheduled_time,estimated_minutes,recurrence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,p.get("goal_id"),p.get("parent_task_id"),p.get("category_id"),title,p.get("description",""),p.get("status","open"),p.get("priority",0),p.get("due_date"),p.get("scheduled_time"),p.get("estimated_minutes"),p.get("recurrence"),stamp,stamp)); audit(g.api_user_id,"create","task",uid); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM tasks WHERE id=?",(cur.lastrowid,)).fetchone())}),201

def require_token_scope(scope):
 if g.actor_type!="agent":return None
 scopes=get_db().execute("SELECT scopes FROM api_tokens WHERE id=?",(g.token_id,)).fetchone()[0].split()
 return None if scope in scopes else (json_error("insufficient_scope",f"Required scope: {scope}"),403)

@bp.route("/v1/tasks/<ident>",methods=("GET","PATCH","DELETE"))
@auth()
def task_item(ident):
 row=owned("tasks",ident,g.api_user_id,request.method in ("PATCH","DELETE"))
 if not row:return json_error("not_found","Task not found."),404
 denied=require_token_scope("tasks:read" if request.method=="GET" else "tasks:write")
 if denied:return denied
 if request.method=="GET":return jsonify({"data":record(row)})
 db=get_db(); p=body()
 if request.method=="DELETE":db.execute("UPDATE tasks SET deleted_at=?,updated_at=?,version=version+1 WHERE id=?",(now(),now(),row["id"])); action="delete"
 else:
  if "parent_task_id" in p and task_would_cycle(g.api_user_id,row["id"],p["parent_task_id"]):return json_error("validation_error","circular_parent"),422
  fields=[x for x in ("title","description","status","priority","due_date","scheduled_time","estimated_minutes","recurrence","position","goal_id","parent_task_id","category_id","archived_at","deleted_at") if x in p]
  if fields:db.execute(f"UPDATE tasks SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1 WHERE id=?",(*[p[x] for x in fields],now(),row["id"]))
  action="update"
 audit(g.api_user_id,action,"task",row["uuid"],{"fields":list(p)}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM tasks WHERE id=?",(row["id"],)).fetchone())})

@bp.post("/v1/tasks/<ident>/complete")
@auth("tasks:write")
def task_complete(ident):
 row=owned("tasks",ident,g.api_user_id)
 if not row:return json_error("not_found","Task not found."),404
 completed=body().get("completed",True); status="completed" if completed else "open"; stamp=now(); db=get_db(); db.execute("UPDATE tasks SET status=?,completed_at=?,updated_at=?,version=version+1 WHERE id=?",(status,stamp if completed else None,stamp,row["id"])); audit(g.api_user_id,"complete" if completed else "reopen","task",row["uuid"]); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM tasks WHERE id=?",(row["id"],)).fetchone())})

@bp.post("/v1/tasks/<ident>/move")
@auth("tasks:write")
def task_move(ident):
 row=owned("tasks",ident,g.api_user_id); p=body()
 if not row:return json_error("not_found","Task not found."),404
 if task_would_cycle(g.api_user_id,row["id"],p.get("parent_task_id")):return json_error("validation_error","circular_parent"),422
 db=get_db(); db.execute("UPDATE tasks SET parent_task_id=?,goal_id=?,position=?,updated_at=?,version=version+1 WHERE id=?",(p.get("parent_task_id"),p.get("goal_id",row["goal_id"]),p.get("position",row["position"]),now(),row["id"])); audit(g.api_user_id,"move","task",row["uuid"]); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM tasks WHERE id=?",(row["id"],)).fetchone())})

@bp.get("/v1/habits")
@auth("habits:read")
def habits_list(): return list_rows("habits")

@bp.post("/v1/habits")
@auth("habits:write")
def habit_create():
 p=body(); en=str(p.get("name_en","")).strip(); ar=str(p.get("name_ar",en)).strip()
 if not en:return json_error("validation_error","name_required"),422
 db=get_db(); uid=p.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO habits(uuid,user_id,category_id,key,name_en,name_ar,selected_for_recap,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,p.get("category_id"),p.get("key"),en,ar,int(p.get("selected_for_recap",True)),stamp,stamp)); db.execute("INSERT INTO habit_schedules(uuid,habit_id,weekdays,time_of_day,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),cur.lastrowid,p.get("weekdays","0,1,2,3,4,5,6"),p.get("time_of_day"),stamp)); audit(g.api_user_id,"create","habit",uid); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM habits WHERE id=?",(cur.lastrowid,)).fetchone())}),201

@bp.patch("/v1/habits/<ident>")
@auth("habits:write")
def habit_update(ident):
 row=owned("habits",ident,g.api_user_id)
 if not row:return json_error("not_found","Habit not found."),404
 p=body(); fields=[x for x in ("name_en","name_ar","active","selected_for_recap","category_id","deleted_at") if x in p]; db=get_db()
 if fields:db.execute(f"UPDATE habits SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1 WHERE id=?",(*[p[x] for x in fields],now(),row["id"]))
 audit(g.api_user_id,"update","habit",row["uuid"],{"fields":fields}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM habits WHERE id=?",(row["id"],)).fetchone())})

@bp.post("/v1/habits/<ident>/entries")
@auth("habits:write")
def habit_entry(ident):
 habit=owned("habits",ident,g.api_user_id)
 if not habit:return json_error("not_found","Habit not found."),404
 p=body(); day=p.get("entry_date",date.today().isoformat()); completed=int(p.get("completed",True)); db=get_db(); stamp=now(); existing=db.execute("SELECT * FROM habit_entries WHERE habit_id=? AND entry_date=?",(habit["id"],day)).fetchone()
 if existing:db.execute("UPDATE habit_entries SET completed=?,deleted_at=NULL,updated_at=?,version=version+1 WHERE id=?",(completed,stamp,existing["id"])); eid=existing["id"]
 else:eid=db.execute("INSERT INTO habit_entries(uuid,habit_id,user_id,entry_date,completed,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(p.get("uuid") or new_uuid(),habit["id"],g.api_user_id,day,completed,stamp,stamp)).lastrowid
 audit(g.api_user_id,"complete" if completed else "reopen","habit",habit["uuid"],{"entry_date":day}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM habit_entries WHERE id=?",(eid,)).fetchone())})

@bp.get("/v1/recap-templates")
@auth("recaps:read")
def templates_list(): return list_rows("recap_templates")

@bp.post("/v1/recap-templates")
@auth("recaps:write")
def template_create():
 p=body(); db=get_db(); stamp=now(); uid=p.get("uuid") or new_uuid(); cur=db.execute("INSERT INTO recap_templates(uuid,user_id,name_en,name_ar,intro_en,intro_ar,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,p.get("name_en","Nightly Muḥāsabah"),p.get("name_ar","محاسبة المساء"),p.get("intro_en",""),p.get("intro_ar",""),int(p.get("active",False)),stamp,stamp)); snapshot_template(cur.lastrowid); audit(g.api_user_id,"create","recap_template",uid); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM recap_templates WHERE id=?",(cur.lastrowid,)).fetchone())}),201

@bp.route("/v1/recap-templates/<ident>",methods=("GET","PATCH"))
@auth()
def template_item(ident):
 row=owned("recap_templates",ident,g.api_user_id)
 if not row:return json_error("not_found","Template not found."),404
 denied=require_token_scope("recaps:read" if request.method=="GET" else "recaps:write")
 if denied:return denied
 db=get_db()
 if request.method=="GET":
  result=record(row); result["fields"]=[record(x) for x in db.execute("SELECT * FROM recap_template_fields WHERE template_id=? AND deleted_at IS NULL ORDER BY position",(row["id"],))]; return jsonify({"data":result})
 p=body(); fields=[x for x in ("name_en","name_ar","intro_en","intro_ar") if x in p]
 if fields:db.execute(f"UPDATE recap_templates SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1,current_version=current_version+1 WHERE id=?",(*[p[x] for x in fields],now(),row["id"])); snapshot_template(row["id"])
 audit(g.api_user_id,"update","recap_template",row["uuid"],{"fields":fields}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM recap_templates WHERE id=?",(row["id"],)).fetchone())})

@bp.post("/v1/recap-templates/<ident>/fields")
@auth("recaps:write")
def template_field_create(ident):
 t=owned("recap_templates",ident,g.api_user_id)
 if not t:return json_error("not_found","Template not found."),404
 p=body(); db=get_db(); stamp=now(); uid=p.get("uuid") or new_uuid(); cur=db.execute("INSERT INTO recap_template_fields(uuid,template_id,stable_key,label_en,label_ar,placeholder_en,placeholder_ar,field_type,required,active,position,config_json,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(uid,t["id"],p.get("stable_key") or uid,p.get("label_en","")[:300],p.get("label_ar","")[:300],p.get("placeholder_en",""),p.get("placeholder_ar",""),p.get("field_type","long_text"),int(p.get("required",False)),int(p.get("active",True)),int(p.get("position",99)),json.dumps(p.get("config",{}),ensure_ascii=False),stamp)); db.execute("UPDATE recap_templates SET current_version=current_version+1,updated_at=? WHERE id=?",(stamp,t["id"])); snapshot_template(t["id"]); audit(g.api_user_id,"create","recap_template_field",uid,{"template_uuid":t["uuid"]}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM recap_template_fields WHERE id=?",(cur.lastrowid,)).fetchone())}),201

@bp.route("/v1/recap-templates/<ident>/fields/<field_id>",methods=("PATCH","DELETE"))
@auth("recaps:write")
def template_field_item(ident,field_id):
 t=owned("recap_templates",ident,g.api_user_id)
 if not t:return json_error("not_found","Template not found."),404
 key="id" if field_id.isdigit() else "uuid"; db=get_db(); f=db.execute(f"SELECT * FROM recap_template_fields WHERE {key}=? AND template_id=? AND deleted_at IS NULL",(field_id,t["id"])).fetchone()
 if not f:return json_error("not_found","Field not found."),404
 stamp=now(); p=body()
 if request.method=="DELETE":db.execute("UPDATE recap_template_fields SET deleted_at=?,updated_at=?,version=version+1 WHERE id=?",(stamp,stamp,f["id"])); action="delete"
 else:
  fields=[x for x in ("label_en","label_ar","placeholder_en","placeholder_ar","field_type","required","active","position","config_json") if x in p]
  if fields:db.execute(f"UPDATE recap_template_fields SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1 WHERE id=?",(*[json.dumps(p[x]) if x=="config_json" and not isinstance(p[x],str) else p[x] for x in fields],stamp,f["id"])); action="update"
 db.execute("UPDATE recap_templates SET current_version=current_version+1,updated_at=? WHERE id=?",(stamp,t["id"])); snapshot_template(t["id"]); audit(g.api_user_id,action,"recap_template_field",f["uuid"],{"fields":list(p)}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM recap_template_fields WHERE id=?",(f["id"],)).fetchone())})

@bp.post("/v1/recap-templates/<ident>/restore-default")
@auth("recaps:write")
def template_restore(ident):
 t=owned("recap_templates",ident,g.api_user_id)
 if not t:return json_error("not_found","Template not found."),404
 db=get_db(); stamp=now(); db.execute("DELETE FROM recap_template_fields WHERE template_id=?",(t["id"],));
 for pos,row in enumerate(DEFAULT_FIELDS):db.execute("INSERT INTO recap_template_fields(uuid,template_id,stable_key,label_en,label_ar,placeholder_en,placeholder_ar,required,position,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(new_uuid(),t["id"],*row,pos,stamp))
 db.execute("UPDATE recap_templates SET name_en='Nightly Muḥāsabah',name_ar='محاسبة المساء',intro_en='A quiet moment of gratitude, reflection and sincere intention before ending the day.',intro_ar='لحظة هادئة للشكر والمراجعة وتجديد النية قبل أن ينتهي اليوم.',current_version=current_version+1,updated_at=? WHERE id=?",(stamp,t["id"])); snapshot_template(t["id"]); audit(g.api_user_id,"restore_default","recap_template",t["uuid"]); db.commit(); return jsonify({"data":template_snapshot(t["id"])})

@bp.post("/v1/recap-templates/<ident>/activate")
@auth("recaps:write")
def template_activate(ident):
 t=owned("recap_templates",ident,g.api_user_id)
 if not t:return json_error("not_found","Template not found."),404
 db=get_db(); db.execute("UPDATE recap_templates SET active=0 WHERE user_id=?",(g.api_user_id,)); db.execute("UPDATE recap_templates SET active=1,updated_at=?,version=version+1 WHERE id=?",(now(),t["id"])); audit(g.api_user_id,"activate","recap_template",t["uuid"]); db.commit(); return jsonify({"data":{"active":t["uuid"]}})

@bp.get("/v1/recaps")
@auth("recaps:read")
def recaps_list(): return list_rows("recaps")

@bp.post("/v1/recaps")
@auth("recaps:write")
def recap_create():
 p=body(); db=get_db(); day=p.get("recap_date",date.today().isoformat()); existing=db.execute("SELECT * FROM recaps WHERE user_id=? AND recap_date=? AND deleted_at IS NULL",(g.api_user_id,day)).fetchone()
 if existing:return json_error("conflict","A recap already exists for this date.",{"server":record(existing)}),409
 t=owned("recap_templates",p.get("template_id"),g.api_user_id) if p.get("template_id") else db.execute("SELECT * FROM recap_templates WHERE user_id=? AND active=1 AND deleted_at IS NULL",(g.api_user_id,)).fetchone()
 if not t:return json_error("validation_error","active_template_required"),422
 snapshot=template_snapshot(t["id"]); uid=p.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO recaps(uuid,user_id,recap_date,template_id,template_version,template_snapshot_json,status,created_at,updated_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,day,t["id"],t["current_version"],json.dumps(snapshot,ensure_ascii=False),p.get("status","draft"),stamp,stamp,stamp if p.get("status")=="completed" else None));
 for key,value in p.get("answers",{}).items():db.execute("INSERT INTO recap_answers(uuid,recap_id,field_key,answer_json,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),cur.lastrowid,key,json.dumps(value,ensure_ascii=False),stamp))
 audit(g.api_user_id,"create","recap",uid,{"date":day,"status":p.get("status","draft")}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM recaps WHERE id=?",(cur.lastrowid,)).fetchone())}),201

def recap_payload(row):
 result=record(row); result["template_snapshot"]=json.loads(result.pop("template_snapshot_json")); result["answers"]={x["field_key"]:json.loads(x["answer_json"]) for x in get_db().execute("SELECT * FROM recap_answers WHERE recap_id=? AND deleted_at IS NULL",(row["id"],))}; return result

@bp.route("/v1/recaps/<ident>",methods=("GET","PATCH"))
@auth()
def recap_item(ident):
 row=owned("recaps",ident,g.api_user_id)
 if not row:return json_error("not_found","Recap not found."),404
 denied=require_token_scope("recaps:read" if request.method=="GET" else "recaps:write")
 if denied:return denied
 if request.method=="GET":return jsonify({"data":recap_payload(row)})
 p=body()
 if "base_version" in p and p["base_version"]!=row["version"]:return json_error("version_conflict","The recap changed on another device.",{"server":recap_payload(row),"client":p}),409
 db=get_db(); stamp=now()
 for key,value in p.get("answers",{}).items():db.execute("INSERT INTO recap_answers(uuid,recap_id,field_key,answer_json,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(recap_id,field_key) DO UPDATE SET answer_json=excluded.answer_json,updated_at=excluded.updated_at,version=recap_answers.version+1",(new_uuid(),row["id"],key,json.dumps(value,ensure_ascii=False),stamp))
 db.execute("UPDATE recaps SET updated_at=?,version=version+1 WHERE id=?",(stamp,row["id"])); audit(g.api_user_id,"update","recap",row["uuid"],{"fields":list(p.get("answers",{}))}); db.commit(); return jsonify({"data":recap_payload(db.execute("SELECT * FROM recaps WHERE id=?",(row["id"],)).fetchone())})

@bp.post("/v1/recaps/<ident>/<action>")
@auth("recaps:write")
def recap_status(ident,action):
 if action not in ("complete","reopen"):return json_error("not_found","Unknown action."),404
 row=owned("recaps",ident,g.api_user_id)
 if not row:return json_error("not_found","Recap not found."),404
 status="completed" if action=="complete" else "draft"; stamp=now(); db=get_db(); db.execute("UPDATE recaps SET status=?,completed_at=?,updated_at=?,version=version+1 WHERE id=?",(status,stamp if status=="completed" else None,stamp,row["id"])); audit(g.api_user_id,action,"recap",row["uuid"]); db.commit(); return jsonify({"data":recap_payload(db.execute("SELECT * FROM recaps WHERE id=?",(row["id"],)).fetchone())})

@bp.get("/v1/resources")
@auth("resources:read")
def resources_list(): return list_rows("resources")

@bp.post("/v1/resources")
@auth("resources:write")
def resource_create():
 p=body()
 if not p.get("title") or not str(p.get("url","")).startswith(("http://","https://")):return json_error("validation_error","A title and HTTP(S) URL are required."),422
 db=get_db(); uid=p.get("uuid") or new_uuid(); stamp=now(); cur=db.execute("INSERT INTO resources(uuid,user_id,goal_id,task_id,title,url,description,resource_type,provider,completed,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,p.get("goal_id"),p.get("task_id"),p["title"],p["url"],p.get("description",""),p.get("resource_type","document"),p.get("provider"),int(p.get("completed",False)),stamp)); audit(g.api_user_id,"create","resource",uid); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM resources WHERE id=?",(cur.lastrowid,)).fetchone())}),201

@bp.patch("/v1/resources/<ident>")
@auth("resources:write")
def resource_update(ident):
 row=owned("resources",ident,g.api_user_id)
 if not row:return json_error("not_found","Resource not found."),404
 p=body(); fields=[x for x in ("title","url","description","resource_type","provider","completed","goal_id","task_id","deleted_at") if x in p]; db=get_db()
 if fields:db.execute(f"UPDATE resources SET {','.join(x+'=?' for x in fields)},updated_at=?,version=version+1 WHERE id=?",(*[p[x] for x in fields],now(),row["id"]))
 audit(g.api_user_id,"update","resource",row["uuid"],{"fields":fields}); db.commit(); return jsonify({"data":record(db.execute("SELECT * FROM resources WHERE id=?",(row["id"],)).fetchone())})

@bp.get("/v1/stats")
@auth("stats:read")
def stats(): return jsonify({"data":calculate_stats(g.api_user_id,date.fromisoformat(request.args["date"]) if request.args.get("date") else None)})

SYNC_TABLES={"task":"tasks","goal":"goals","habit":"habits","recap":"recaps","resource":"resources"}
@bp.post("/v1/sync")
@auth()
def sync():
 p=body(); db=get_db(); conflicts=[]; results=[]
 for m in p.get("mutations",[]):
  prior=db.execute("SELECT record_json FROM sync_changes WHERE user_id=? AND mutation_uuid=?",(g.api_user_id,m.get("mutation_uuid"),)).fetchone()
  if prior:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"already_applied","record":json.loads(prior[0])}); continue
  table=SYNC_TABLES.get(m.get("entity_type"))
  if m.get("entity_type")=="habit_entry" and m.get("operation")=="create":
   hp=m.get("payload",{}); habit=owned("habits",hp.get("habit_uuid"),g.api_user_id)
   if not habit:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"not_found"}); continue
   stamp=now(); entry=db.execute("SELECT * FROM habit_entries WHERE habit_id=? AND entry_date=?",(habit["id"],hp.get("entry_date"))).fetchone()
   if entry:db.execute("UPDATE habit_entries SET completed=?,updated_at=?,version=version+1,deleted_at=NULL WHERE id=?",(int(hp.get("completed",True)),stamp,entry["id"])); eid=entry["id"]
   else:eid=db.execute("INSERT INTO habit_entries(uuid,habit_id,user_id,entry_date,completed,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",(m.get("entity_uuid") or new_uuid(),habit["id"],g.api_user_id,hp.get("entry_date"),int(hp.get("completed",True)),stamp,stamp)).lastrowid
   changed=record(db.execute("SELECT * FROM habit_entries WHERE id=?",(eid,)).fetchone()); cursor=db.execute("SELECT COALESCE(MAX(cursor),0)+1 FROM sync_changes").fetchone()[0]; db.execute("INSERT INTO sync_changes(cursor,mutation_uuid,user_id,entity_type,entity_uuid,operation,record_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(cursor,m.get("mutation_uuid"),g.api_user_id,"habit_entry",changed["uuid"],"create",json.dumps(changed),stamp)); results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"applied","record":changed,"cursor":cursor}); continue
  if not table:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"invalid"}); continue
  row=owned(table,m.get("entity_uuid"),g.api_user_id,True)
  if not row and m.get("operation")=="create":
   cp=m.get("payload",{}); stamp=now(); uid=m.get("entity_uuid") or new_uuid()
   if table=="tasks":
    if not str(cp.get("title","")).strip():results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"invalid"}); continue
    rid=db.execute("INSERT INTO tasks(uuid,user_id,title,description,due_date,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(uid,g.api_user_id,cp["title"].strip(),cp.get("description",""),cp.get("due_date"),cp.get("status","open"),stamp,stamp)).lastrowid
   elif table=="recaps":
    template=db.execute("SELECT * FROM recap_templates WHERE user_id=? AND active=1 AND deleted_at IS NULL",(g.api_user_id,)).fetchone()
    if not template:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"invalid"}); continue
    snap=template_snapshot(template["id"]); rid=db.execute("INSERT INTO recaps(uuid,user_id,recap_date,template_id,template_version,template_snapshot_json,status,created_at,updated_at,completed_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(uid,g.api_user_id,cp.get("recap_date"),template["id"],template["current_version"],json.dumps(snap,ensure_ascii=False),cp.get("status","draft"),stamp,stamp,stamp if cp.get("status")=="completed" else None)).lastrowid
    for k,v in cp.get("answers",{}).items():db.execute("INSERT INTO recap_answers(uuid,recap_id,field_key,answer_json,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),rid,k,json.dumps(v,ensure_ascii=False),stamp))
   else:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"invalid"}); continue
   changed=record(db.execute(f"SELECT * FROM {table} WHERE id=?",(rid,)).fetchone()); cursor=db.execute("SELECT COALESCE(MAX(cursor),0)+1 FROM sync_changes").fetchone()[0]; db.execute("INSERT INTO sync_changes(cursor,mutation_uuid,user_id,entity_type,entity_uuid,operation,record_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(cursor,m.get("mutation_uuid"),g.api_user_id,m["entity_type"],uid,"create",json.dumps(changed),stamp)); audit(g.api_user_id,"create",m["entity_type"],uid,{"mutation_uuid":m.get("mutation_uuid")}); results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"applied","record":changed,"cursor":cursor}); continue
  if not row:results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"not_found"}); continue
  if int(m.get("base_version",0))!=row["version"] and not m.get("force"):
   conflicts.append({"mutation_uuid":m.get("mutation_uuid"),"entity_type":m["entity_type"],"entity_uuid":m["entity_uuid"],"server":record(row),"client":m}); continue
  allowed={"tasks":{"title","description","status","due_date","scheduled_time","completed_at","deleted_at"},"goals":{"title","description","status","deleted_at"},"habits":{"name_en","name_ar","active","deleted_at"},"resources":{"title","description","completed","deleted_at"},"recaps":{"status","completed_at","deleted_at"}}[table]
  values={k:v for k,v in m.get("payload",{}).items() if k in allowed}; stamp=now()
  if values:db.execute(f"UPDATE {table} SET {','.join(k+'=?' for k in values)},updated_at=?,version=version+1 WHERE id=?",(*values.values(),stamp,row["id"]))
  changed=record(db.execute(f"SELECT * FROM {table} WHERE id=?",(row["id"],)).fetchone()); cursor=(db.execute("SELECT COALESCE(MAX(cursor),0)+1 FROM sync_changes").fetchone()[0]); db.execute("INSERT INTO sync_changes(cursor,mutation_uuid,user_id,entity_type,entity_uuid,operation,record_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(cursor,m.get("mutation_uuid"),g.api_user_id,m["entity_type"],m["entity_uuid"],m.get("operation","update"),json.dumps(changed),stamp)); audit(g.api_user_id,"conflict_resolution" if m.get("force") else m.get("operation","update"),m["entity_type"],m["entity_uuid"],{"mutation_uuid":m.get("mutation_uuid")}); results.append({"mutation_uuid":m.get("mutation_uuid"),"status":"applied","record":changed,"cursor":cursor})
 db.commit(); cursor=int(p.get("cursor",0)); changes=[{**record(r),"record":json.loads(r["record_json"])} for r in db.execute("SELECT * FROM sync_changes WHERE user_id=? AND cursor>? ORDER BY cursor LIMIT 500",(g.api_user_id,cursor))];
 for c in changes:c.pop("record_json",None)
 return jsonify({"data":{"results":results,"conflicts":conflicts,"changes":changes,"cursor":changes[-1]["cursor"] if changes else cursor}})
