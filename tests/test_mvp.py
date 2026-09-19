import hashlib, json, uuid
from datetime import date, datetime, timedelta, timezone
from werkzeug.security import check_password_hash
from app.db import get_db
from app.services import calculate_stats, new_uuid, now, seed_user_routine
from conftest import api, register


def test_registration_login_and_password_hash(app,client):
    response=register(client,language="ar")
    assert response.status_code==302
    with app.app_context():
        user=get_db().execute("SELECT * FROM users").fetchone()
        assert user["language"]=="ar" and user["password_hash"]!="very-secure-password"
        assert check_password_hash(user["password_hash"],"very-secure-password")
        assert get_db().execute("SELECT COUNT(*) FROM categories").fetchone()[0]==8
        assert get_db().execute("SELECT COUNT(*) FROM recap_template_fields").fetchone()[0]==5
    client.post("/auth/logout",data={"csrf_token":"test-csrf"})
    with client.session_transaction() as s:s["csrf_token"]="test-csrf"
    assert client.post("/auth/login",data={"csrf_token":"test-csrf","email":"one@example.com","password":"bad"}).status_code==200
    assert client.post("/auth/login",data={"csrf_token":"test-csrf","email":"one@example.com","password":"very-secure-password"}).status_code==302


def test_arabic_rtl_and_language_preference(app,client):
    register(client,language="ar")
    page=client.get("/today")
    assert b'<html lang="ar" dir="rtl">' in page.data
    assert "محاسبة المساء" in page.get_data(as_text=True)
    api(client,"POST","/settings") if False else None
    response=client.post("/settings",data={"csrf_token":"test-csrf","action":"profile","language":"en","timezone":"Africa/Cairo"})
    assert response.status_code==302
    assert b'<html lang="en" dir="ltr">' in client.get("/today").data


def test_user_data_isolation_and_goal_hierarchy(app,client):
    register(client)
    root=api(client,"POST","/api/v1/goals",{"type":"lifetime","title":"Purpose"}).get_json()["data"]
    invalid=api(client,"POST","/api/v1/goals",{"type":"month","title":"Wrong","parent_id":root["id"]})
    assert invalid.status_code==422
    client.post("/auth/logout",data={"csrf_token":"test-csrf"}); register(client,"two@example.com")
    assert api(client,"GET",f'/api/v1/goals/{root["uuid"]}').status_code==404


def test_batch_hierarchy_is_atomic(app,user):
    payload={"goals":[{"type":"lifetime","title":"Life","children":[{"type":"year","title":"2026","children":[{"type":"month","title":"Invalid skip"}]}]}]}
    assert api(user,"POST","/api/v1/goals/tree",payload).status_code==422
    assert api(user,"GET","/api/v1/goals").get_json()["pagination"]["count"]==0
    payload["goals"][0]["children"][0]["children"]=[{"type":"quarter","title":"Q1","children":[{"type":"month","title":"January","children":[{"type":"week","title":"W1"}]}]}]
    response=api(user,"POST","/api/v1/goals/tree",payload)
    assert response.status_code==201 and len(response.get_json()["data"]["created"])==5


def test_subtask_cycle_completion_soft_delete_restore(user):
    parent=api(user,"POST","/api/v1/tasks",{"title":"Parent","due_date":date.today().isoformat()}).get_json()["data"]
    child=api(user,"POST","/api/v1/tasks",{"title":"Child","parent_task_id":parent["id"]}).get_json()["data"]
    assert api(user,"PATCH",f'/api/v1/tasks/{parent["uuid"]}',{"parent_task_id":child["id"]}).status_code==422
    done=api(user,"POST",f'/api/v1/tasks/{parent["uuid"]}/complete',{"completed":True}).get_json()["data"]
    assert done["status"]=="completed"
    assert api(user,"DELETE",f'/api/v1/tasks/{parent["uuid"]}').status_code==200
    restored=api(user,"PATCH",f'/api/v1/tasks/{parent["uuid"]}',{"deleted_at":None})
    assert restored.status_code==200


def test_habit_entries_streaks_and_stats(app,user):
    habit=api(user,"POST","/api/v1/habits",{"name_en":"Quran","name_ar":"القرآن"}).get_json()["data"]
    for n in range(3):
        d=date.today()-timedelta(days=n)
        assert api(user,"POST",f'/api/v1/habits/{habit["uuid"]}/entries',{"entry_date":d.isoformat(),"completed":True}).status_code==200
    task=api(user,"POST","/api/v1/tasks",{"title":"Focus","due_date":date.today().isoformat()}).get_json()["data"]
    api(user,"POST",f'/api/v1/tasks/{task["uuid"]}/complete',{})
    stats=api(user,"GET","/api/v1/stats").get_json()["data"]
    streak=next(x for x in stats["habit_streaks"] if x["uuid"]==habit["uuid"])
    assert streak["current_streak"]==3 and streak["longest_streak"]==3 and stats["today_completion"]==100


def make_token(app,user_id,scopes,expires=None,revoked=None):
    secret="northstar_"+uuid.uuid4().hex; db=get_db()
    db.execute("INSERT INTO api_tokens(uuid,user_id,name,token_prefix,token_hash,scopes,created_at,expires_at,revoked_at) VALUES(?,?,?,?,?,?,?,?,?)",(new_uuid(),user_id,"test",secret[:12],hashlib.sha256(secret.encode()).hexdigest(),scopes,now(),expires,revoked)); db.commit(); return secret


def test_api_token_scopes_revoked_expired_and_agent_audit(app,user):
    with app.app_context():
        uid=get_db().execute("SELECT id FROM users").fetchone()[0]
        read=make_token(app,uid,"tasks:read"); revoked=make_token(app,uid,"tasks:read",revoked=now()); expired=make_token(app,uid,"tasks:read",expires=(datetime.now(timezone.utc)-timedelta(days=1)).isoformat())
    headers=lambda token:{"Authorization":f"Bearer {token}"}
    assert user.get("/api/v1/tasks",headers=headers(read)).status_code==200
    assert user.post("/api/v1/tasks",headers=headers(read),json={"title":"No"}).status_code==403
    assert user.get("/api/v1/tasks",headers=headers(revoked)).status_code==401
    assert user.get("/api/v1/tasks",headers=headers(expired)).status_code==401
    with app.app_context():
        write=make_token(app,uid,"tasks:write tasks:read")
    created=user.post("/api/v1/tasks",headers=headers(write),json={"title":"Agent work"})
    assert created.status_code==201
    with app.app_context(): assert get_db().execute("SELECT 1 FROM audit_events WHERE actor_type='agent' AND action='create'").fetchone()


def test_recap_scope_isolation_arabic_and_mixed_content(app,user):
    recap=api(user,"POST","/api/v1/recaps",{"recap_date":"2026-09-19","answers":{"gratitude":"الحمد لله for family","dua":"اللهم ارزقني خيرًا"}}).get_json()["data"]
    with app.app_context():
        uid=get_db().execute("SELECT id FROM users").fetchone()[0]; task_token=make_token(app,uid,"tasks:read"); recap_token=make_token(app,uid,"recaps:read")
    assert user.get(f'/api/v1/recaps/{recap["uuid"]}',headers={"Authorization":f"Bearer {task_token}"}).status_code==403
    data=user.get(f'/api/v1/recaps/{recap["uuid"]}',headers={"Authorization":f"Bearer {recap_token}"}).get_json()["data"]
    assert data["answers"]["gratitude"]=="الحمد لله for family"
    user.post("/auth/logout",data={"csrf_token":"test-csrf"}); register(user,"other@example.com")
    assert api(user,"GET",f'/api/v1/recaps/{recap["uuid"]}').status_code==404


def test_template_edit_reorder_restore_and_history_snapshot(app,user):
    with app.app_context(): template=dict(get_db().execute("SELECT * FROM recap_templates").fetchone())
    recap=api(user,"POST","/api/v1/recaps",{"recap_date":"2026-09-18","answers":{"gratitude":"Original"}}).get_json()["data"]
    before=api(user,"GET",f'/api/v1/recaps/{recap["uuid"]}').get_json()["data"]["template_snapshot"]
    item=api(user,"GET",f'/api/v1/recap-templates/{template["uuid"]}').get_json()["data"]
    field=item["fields"][0]
    assert api(user,"PATCH",f'/api/v1/recap-templates/{template["uuid"]}/fields/{field["uuid"]}',{"label_en":"Changed","position":4}).status_code==200
    after=api(user,"GET",f'/api/v1/recaps/{recap["uuid"]}').get_json()["data"]["template_snapshot"]
    assert before==after and before["fields"][0]["label_en"]!="Changed"
    restored=api(user,"POST",f'/api/v1/recap-templates/{template["uuid"]}/restore-default',{}).get_json()["data"]
    assert restored["fields"][0]["stable_key"]=="gratitude"


def test_recap_version_conflict(user):
    recap=api(user,"POST","/api/v1/recaps",{"recap_date":"2026-09-17","answers":{"gratitude":"One"}}).get_json()["data"]
    api(user,"PATCH",f'/api/v1/recaps/{recap["uuid"]}',{"base_version":1,"answers":{"gratitude":"Two"}})
    conflict=api(user,"PATCH",f'/api/v1/recaps/{recap["uuid"]}',{"base_version":1,"answers":{"gratitude":"Stale"}})
    assert conflict.status_code==409 and conflict.get_json()["error"]["code"]=="version_conflict"


def test_sync_idempotency_conflict_and_offline_recap(user):
    task=api(user,"POST","/api/v1/tasks",{"title":"Sync me"}).get_json()["data"]; mid=str(uuid.uuid4())
    mutation={"mutation_uuid":mid,"entity_type":"task","entity_uuid":task["uuid"],"operation":"update","base_version":task["version"],"payload":{"status":"completed"}}
    first=api(user,"POST","/api/v1/sync",{"cursor":0,"mutations":[mutation]}).get_json()["data"]
    second=api(user,"POST","/api/v1/sync",{"cursor":0,"mutations":[mutation]}).get_json()["data"]
    assert first["results"][0]["status"]=="applied" and second["results"][0]["status"]=="already_applied"
    stale={**mutation,"mutation_uuid":str(uuid.uuid4()),"payload":{"title":"stale"}}
    assert api(user,"POST","/api/v1/sync",{"mutations":[stale]}).get_json()["data"]["conflicts"]
    recap_uuid=str(uuid.uuid4()); offline={"mutation_uuid":str(uuid.uuid4()),"entity_type":"recap","entity_uuid":recap_uuid,"operation":"create","base_version":0,"payload":{"recap_date":"2026-09-16","status":"draft","answers":{"gratitude":"نعمة"}}}
    result=api(user,"POST","/api/v1/sync",{"mutations":[offline]}).get_json()["data"]["results"][0]
    assert result["status"]=="applied"
    assert api(user,"GET",f"/api/v1/recaps/{recap_uuid}").get_json()["data"]["answers"]["gratitude"]=="نعمة"


def test_logout_clears_private_browser_storage_header(user):
    response=user.post("/auth/logout",data={"csrf_token":"test-csrf"})
    assert response.headers["Clear-Site-Data"]=='"storage"'


def test_openapi_manifest_and_service_worker(client):
    assert client.get("/api/openapi.json").status_code==200
    spec=client.get("/api/openapi.json").get_json()
    assert spec["openapi"].startswith("3.") and "/api/v1/sync" in spec["paths"]
    assert client.get("/static/manifest.webmanifest").status_code==200
    assert client.get("/static/sw.js").status_code==200


def test_personal_profile_preferences_and_plan_seed(app,user):
    from app.personal_plan import seed_personal_plan
    with app.app_context():
        db=get_db(); uid=db.execute("SELECT id FROM users").fetchone()[0]
        db.execute("UPDATE users SET display_name='Ahmed Wael Wanas',timezone='Africa/Cairo',language='en',week_starts=0,workdays='0,1,2,3,4',work_start='09:00',work_end='17:00',outside_work_minutes=120 WHERE id=?",(uid,)); db.commit()
        assert "successfully" in seed_personal_plan(uid)
        assert "already exists" in seed_personal_plan(uid)
        profile=db.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        assert profile["display_name"]=="Ahmed Wael Wanas" and profile["outside_work_minutes"]==120
        categories=db.execute("SELECT name_key,position FROM categories WHERE user_id=? ORDER BY position",(uid,)).fetchall()
        assert [(x["name_key"],x["position"]) for x in categories]==[("spiritual",1),("marriage",2),("secops",3),("finance",4),("health",5),("family_social",6),("work",7),("personal",8)]
        assert db.execute("SELECT COUNT(*) FROM goals WHERE user_id=?",(uid,)).fetchone()[0]==95
        challenge=db.execute("SELECT * FROM habits WHERE user_id=? AND key='pmo_free'",(uid,)).fetchone()
        assert challenge["privacy"]=="private" and challenge["end_date"]=="2026-11-16"
        assert db.execute("SELECT COUNT(*) FROM resources WHERE user_id=?",(uid,)).fetchone()[0]==3
