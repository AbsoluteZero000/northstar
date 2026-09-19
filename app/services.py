import json
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone
from flask import g
from .db import get_db

UTC = timezone.utc
GOAL_PARENT = {"lifetime": None, "year": "lifetime", "quarter": "year", "month": "quarter", "week": "month"}


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_uuid():
    return str(uuid.uuid4())


def owned(table, ident, user_id, include_deleted=False):
    key = "id" if str(ident).isdigit() else "uuid"
    sql = f"SELECT * FROM {table} WHERE {key}=? AND user_id=?"
    args = [ident, user_id]
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    return get_db().execute(sql, args).fetchone()


def audit(user_id, action, entity_type, entity_uuid=None, metadata=None, actor=None, token_id=None):
    # Sensitive values (especially recap answers) must never be passed as metadata.
    get_db().execute(
        "INSERT INTO audit_events(uuid,user_id,actor_type,token_id,action,entity_type,entity_uuid,metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (new_uuid(), user_id, actor or getattr(g, "actor_type", "user"), token_id or getattr(g, "token_id", None), action, entity_type, entity_uuid, json.dumps(metadata or {}), now()),
    )


DEFAULT_CATEGORIES = [
    ("spiritual", "Spiritual", "#10b981", "crescent"), ("marriage", "Marriage", "#f43f5e", "heart"),
    ("secops", "SecOps", "#3b82f6", "shield"), ("finance", "Finance", "#d4a84f", "wallet"),
    ("health", "Health", "#ef4444", "activity"), ("family_social", "Family/Social", "#8b5cf6", "users"),
    ("work", "Work", "#64748b", "briefcase"), ("personal", "Personal", "#06b6d4", "user"),
]

DEFAULT_FIELDS = [
    ("gratitude", "A blessing I thank Allah for today", "نعمة أحمد الله عليها اليوم", "What blessing, ease or moment of goodness are you grateful for?", "ما النعمة أو التيسير أو اللحظة الطيبة التي تشكر الله عليها؟", 1),
    ("good_deed", "A good deed Allah enabled me to do", "عمل صالح وفقني الله إليه", "What beneficial or kind action went well today?", "ما العمل النافع أو الطيب الذي وُفقت إليه اليوم؟", 1),
    ("shortcoming", "A shortcoming I seek forgiveness for and want to improve", "تقصير أستغفر الله منه وأسعى لإصلاحه", "What went wrong, and what practical step can help you correct it?", "ما الذي قصرت فيه؟ وما الخطوة العملية التي تساعدك على إصلاحه؟", 1),
    ("tomorrow_intention", "My sincere intention and most important action for tomorrow", "نيتي وأهم عمل لي غدًا", "What is the one outcome you intend to prioritize tomorrow?", "ما أهم نتيجة تنوي أن تجعلها أولوية غدًا؟", 1),
    ("dua", "A duʿāʾ I want to make", "دعاء أريد أن أدعو به", "Write a personal supplication or something you want to ask Allah for.", "اكتب دعاءً شخصيًا أو أمرًا تريد أن تسأل الله إياه.", 0),
]


def provision_user(user_id):
    db = get_db(); stamp = now()
    for pos, (key, name, color, icon) in enumerate(DEFAULT_CATEGORIES,1):
        db.execute("INSERT INTO categories(uuid,user_id,name_key,name,color,icon,position,updated_at) VALUES(?,?,?,?,?,?,?,?)", (new_uuid(),user_id,key,name,color,icon,pos,stamp))
    template_uuid = new_uuid()
    cur = db.execute("INSERT INTO recap_templates(uuid,user_id,name_en,name_ar,intro_en,intro_ar,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (template_uuid,user_id,"Nightly Muḥāsabah","محاسبة المساء","A quiet moment of gratitude, reflection and sincere intention before ending the day.","لحظة هادئة للشكر والمراجعة وتجديد النية قبل أن ينتهي اليوم.",stamp,stamp))
    tid = cur.lastrowid
    for pos, row in enumerate(DEFAULT_FIELDS):
        db.execute("INSERT INTO recap_template_fields(uuid,template_id,stable_key,label_en,label_ar,placeholder_en,placeholder_ar,required,position,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (new_uuid(),tid,*row,pos,stamp))
    snapshot_template(tid)
    db.commit()


def template_snapshot(template_id):
    db=get_db(); t=db.execute("SELECT * FROM recap_templates WHERE id=?",(template_id,)).fetchone()
    fields=db.execute("SELECT * FROM recap_template_fields WHERE template_id=? AND active=1 AND deleted_at IS NULL ORDER BY position",(template_id,)).fetchall()
    return {"name_en":t["name_en"],"name_ar":t["name_ar"],"intro_en":t["intro_en"],"intro_ar":t["intro_ar"],"fields":[dict(f) for f in fields]}


def snapshot_template(template_id):
    db=get_db(); t=db.execute("SELECT current_version FROM recap_templates WHERE id=?",(template_id,)).fetchone()
    db.execute("INSERT OR REPLACE INTO recap_template_versions(uuid,template_id,version_number,snapshot_json,created_at) VALUES(?,?,?,?,?)",(new_uuid(),template_id,t["current_version"],json.dumps(template_snapshot(template_id),ensure_ascii=False),now()))


def validate_goal_parent(user_id, goal_type, parent_id):
    required=GOAL_PARENT.get(goal_type, "invalid")
    if required == "invalid": return "invalid_goal_type"
    if required is None: return None if not parent_id else "lifetime_has_no_parent"
    if not parent_id: return f"{goal_type}_requires_{required}_parent"
    parent=owned("goals",parent_id,user_id)
    if not parent: return "parent_not_found"
    return None if parent["type"] == required else f"{goal_type}_requires_{required}_parent"


def task_would_cycle(user_id, task_id, parent_id):
    if not parent_id: return False
    current=owned("tasks",parent_id,user_id)
    seen=set()
    while current:
        if current["id"] == task_id or current["id"] in seen: return True
        seen.add(current["id"])
        current=owned("tasks",current["parent_task_id"],user_id) if current["parent_task_id"] else None
    return False


def seed_user_routine(user_id):
    db=get_db(); stamp=now()
    existing=db.execute("SELECT 1 FROM habits WHERE user_id=? LIMIT 1",(user_id,)).fetchone()
    if existing: return
    category={r["name_key"]:r["id"] for r in db.execute("SELECT id,name_key FROM categories WHERE user_id=?",(user_id,))}
    habits=[
      ("fajr","Fajr","الفجر","spiritual","0,1,2,3,4,5,6","05:00"),("dhuhr","Dhuhr","الظهر","spiritual","0,1,2,3,4,5,6","12:00"),
      ("asr","Asr","العصر","spiritual","0,1,2,3,4,5,6","15:30"),("maghrib","Maghrib","المغرب","spiritual","0,1,2,3,4,5,6","18:00"),("isha","Isha","العشاء","spiritual","0,1,2,3,4,5,6","19:30"),
      ("quran","Quran","القرآن","spiritual","0,1,2,3,4,5,6",None),("brush_am","Brush teeth — morning","تنظيف الأسنان — صباحًا","health","0,1,2,3,4,5,6","07:00"),
      ("brush_pm","Brush teeth — evening","تنظيف الأسنان — مساءً","health","0,1,2,3,4,5,6","22:00"),("gym","Gym","النادي الرياضي","health","0,1,3,5",None),
      ("secops","SecOps study","دراسة أمن العمليات","secops","0,2,3,6",None),("finance","Finance study","دراسة المالية","finance","1,5",None),
      ("marriage","Marriage preparation","الاستعداد للزواج","marriage","2,4",None),("family","Family/social time","وقت العائلة والأصدقاء","family_social","4",None),
      ("weekly_review","Weekly Reflection","المراجعة الأسبوعية","personal","4",None),("nightly_recap","Nightly Muḥāsabah","محاسبة المساء","spiritual","0,1,2,3,4,5,6","22:15")]
    for key,en,ar,cat,days,time in habits:
        huuid=new_uuid(); cur=db.execute("INSERT INTO habits(uuid,user_id,category_id,key,name_en,name_ar,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",(huuid,user_id,category.get(cat),key,en,ar,stamp,stamp))
        db.execute("INSERT INTO habit_schedules(uuid,habit_id,weekdays,time_of_day,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),cur.lastrowid,days,time,stamp))
    # Editable work blocks are tasks with recurrence metadata.
    db.execute("INSERT INTO tasks(uuid,user_id,category_id,title,due_date,scheduled_time,recurrence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",(new_uuid(),user_id,category.get("work"),"Work",date.today().isoformat(),"09:00","weekdays:0,1,2,3,4;end:17:00",stamp,stamp))
    db.commit()


def calculate_stats(user_id, today=None):
    db=get_db(); today=today or date.today(); start=today-timedelta(days=today.weekday()); end=start+timedelta(days=6)
    def rate(done,total): return round(done*100/total) if total else 0
    t=db.execute("SELECT COUNT(*) total,SUM(status='completed') done FROM tasks WHERE user_id=? AND due_date=? AND deleted_at IS NULL",(user_id,today.isoformat())).fetchone()
    w=db.execute("SELECT COUNT(*) total,SUM(status='completed') done FROM tasks WHERE user_id=? AND due_date BETWEEN ? AND ? AND deleted_at IS NULL",(user_id,start.isoformat(),end.isoformat())).fetchone()
    categories=[dict(r) for r in db.execute("SELECT c.name,c.color,COUNT(t.id) total,COALESCE(SUM(t.status='completed'),0) done FROM categories c LEFT JOIN tasks t ON t.category_id=c.id AND t.deleted_at IS NULL WHERE c.user_id=? GROUP BY c.id",(user_id,))]
    habits=[]
    for h in db.execute("SELECT * FROM habits WHERE user_id=? AND active=1 AND deleted_at IS NULL",(user_id,)):
        dates={r[0] for r in db.execute("SELECT entry_date FROM habit_entries WHERE habit_id=? AND completed=1 AND deleted_at IS NULL",(h["id"],))}
        current=0; d=today
        while d.isoformat() in dates: current+=1; d-=timedelta(days=1)
        longest=run=0; previous=None
        for value in sorted(dates):
            current_date=date.fromisoformat(value); run=run+1 if previous and current_date==previous+timedelta(days=1) else 1; longest=max(longest,run); previous=current_date
        habits.append({"uuid":h["uuid"],"key":h["key"],"name_en":h["name_en"],"name_ar":h["name_ar"],"current_streak":current,"longest_streak":longest})
    recaps=db.execute("SELECT COUNT(*) total,SUM(status='completed') done FROM recaps WHERE user_id=? AND recap_date BETWEEN ? AND ? AND deleted_at IS NULL",(user_id,start.isoformat(),end.isoformat())).fetchone()
    weekly_entries={r["key"]:r["done"] for r in db.execute("SELECT h.key,COUNT(e.id) done FROM habits h LEFT JOIN habit_entries e ON e.habit_id=h.id AND e.completed=1 AND e.deleted_at IS NULL AND e.entry_date BETWEEN ? AND ? WHERE h.user_id=? AND h.deleted_at IS NULL GROUP BY h.id",(start.isoformat(),end.isoformat(),user_id))}
    prayer_done=sum(weekly_entries.get(k,0) for k in ("fajr","dhuhr","asr","maghrib","isha")); prayer_total=5*7
    goal_rows=[dict(r) for r in db.execute("SELECT id,parent_id,uuid,title FROM goals WHERE user_id=? AND deleted_at IS NULL",(user_id,))]; children={}
    for row in goal_rows:children.setdefault(row["parent_id"],[]).append(row["id"])
    def descendants(gid):
        result={gid}
        for child in children.get(gid,[]):result|=descendants(child)
        return result
    goal_progress=[]
    for goal in goal_rows:
        ids=descendants(goal["id"]); marks=",".join("?" for _ in ids); counts=db.execute(f"SELECT COUNT(*) total,COALESCE(SUM(status='completed'),0) done FROM tasks WHERE user_id=? AND goal_id IN ({marks}) AND deleted_at IS NULL",(user_id,*ids)).fetchone(); goal_progress.append({"uuid":goal["uuid"],"title":goal["title"],"completed":counts["done"],"total":counts["total"],"progress":rate(counts["done"],counts["total"])})
    return {"date":today.isoformat(),"today_completion":rate(t["done"] or 0,t["total"]),"weekly_completion":rate(w["done"] or 0,w["total"]),"categories":[{**c,"completion":rate(c["done"],c["total"])} for c in categories],"habit_streaks":habits,"recap_consistency":rate(recaps["done"] or 0,7),"prayer_completion":rate(prayer_done,prayer_total),"quran_consistency":rate(weekly_entries.get("quran",0),7),"gym_sessions":weekly_entries.get("gym",0),"focus_sessions":weekly_entries.get("secops",0)+weekly_entries.get("finance",0),"goal_progress":goal_progress}


def weekly_reflection(user_id, today=None):
    db=get_db(); today=today or date.today(); start=today-timedelta(days=today.weekday())
    rows=db.execute("SELECT ra.field_key,ra.answer_json,r.recap_date FROM recap_answers ra JOIN recaps r ON r.id=ra.recap_id WHERE r.user_id=? AND r.recap_date BETWEEN ? AND ? AND r.deleted_at IS NULL ORDER BY r.recap_date",(user_id,start.isoformat(),today.isoformat())).fetchall()
    grouped={k:[] for k in ("gratitude","good_deed","shortcoming","tomorrow_intention")}
    for row in rows:
        if row["field_key"] in grouped:
            value=json.loads(row["answer_json"])
            if value:grouped[row["field_key"]].append({"date":row["recap_date"],"text":value})
    habits=db.execute("SELECT h.key,h.name_en,h.name_ar,COUNT(e.id) completed FROM habits h LEFT JOIN habit_entries e ON e.habit_id=h.id AND e.completed=1 AND e.entry_date BETWEEN ? AND ? AND e.deleted_at IS NULL WHERE h.user_id=? AND h.deleted_at IS NULL GROUP BY h.id ORDER BY completed DESC",(start.isoformat(),today.isoformat(),user_id)).fetchall()
    return {"start":start.isoformat(),"end":today.isoformat(),"entries":grouped,"habits":[dict(x) for x in habits]}
