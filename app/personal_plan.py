"""Idempotent seed for Ahmed's September–December 2026 personal plan."""
from datetime import date
from .db import get_db
from .services import new_uuid, now

START="2026-09-18"; END="2026-12-18"

LIFETIME={
 "spiritual":("Live a life pleasing to Allah through consistent worship, repentance, discipline and good character.","Establish consistent worship, complete the 60-day PMO-free challenge and build a lasting muḥāsabah habit"),
 "marriage":("Build and lead a peaceful Islamic marriage and a stable, loving family.","Become personally, emotionally and financially ready to begin a serious marriage search"),
 "secops":("Become an excellent security engineer with strong practical SecOps skills and meaningful work.","Build a practical SOC Level 1 foundation and produce demonstrable security work"),
 "finance":("Achieve halal financial stability and provide responsibly for my future family.","Understand my financial position and create a realistic marriage and 2027 financial plan"),
 "health":("Maintain the physical health, energy and discipline required to fulfil my responsibilities.","Establish a sustainable four-days-per-week gym routine"),
}

OUTCOMES={
 "spiritual":"Complete the 60-day PMO-free challenge.\nMaintain the five daily prayers.\nRead Quran daily for 20 minutes.\nComplete the nightly Islamic recap.\nBuild a sustainable routine beyond day 60.",
 "marriage":"Understand the responsibilities of a husband.\nImprove communication and conflict-resolution knowledge.\nDefine spouse-selection criteria.\nPrepare the marriage budget.\nBegin the search process after day 30.\nResearch housing, appliances and household management.",
 "secops":"Progress through the TryHackMe SOC Level 1 path.\nStudy SIEM, Windows logs, networking and MITRE ATT&CK.\nPractise phishing analysis and incident response.\nCreate at least one practical security project.\nPrepare explanations suitable for interviews.",
 "finance":"Track spending and calculate net worth.\nCreate monthly and marriage budgets.\nSet an emergency-fund target.\nUnderstand inflation, investing and Islamic-finance fundamentals.\nDefine personal Sharia-screening and investment rules.\nCreate a 2027 financial plan.",
 "health":"Attend the gym four times each week.\nMaintain the routine without sacrificing sleep or recovery.",
}

MONTHS=[
 ("Month 1 — Establish the foundation","2026-09-18","2026-10-15",{
  "spiritual":"Establish the prayer, Quran, PMO-free and recap routines","marriage":"Study husband responsibilities, communication, conflict and selection criteria","secops":"Cover SOC introduction, SIEM, Windows/Sysmon and network foundations","finance":"Understand spending, budgeting, net worth and emergency funds","health":"Complete four gym sessions each week"}),
 ("Month 2 — Move into practical preparation","2026-10-16","2026-11-12",{
  "spiritual":"Continue the challenge through day 56 and identify recurring triggers","marriage":"Begin searching and research budgets, housing, appliances and household finance","secops":"Study MITRE ATT&CK, phishing, incident response and Active Directory","finance":"Prepare the marriage budget and study inflation, investing and Islamic finance","health":"Maintain four weekly gym sessions"}),
 ("Month 3 — Consolidate and plan forward","2026-11-13","2026-12-18",{
  "spiritual":"Reach day 60 and convert the challenge into a permanent lifestyle","marriage":"Study boundaries and parenting, review progress and define next steps","secops":"Practise detection, threat hunting and projects, then review everything","finance":"Study Sharia screening and gold, define investment rules and create the 2027 plan","health":"Maintain the gym routine and review physical progress"}),
]

WEEKS=[
 ("2026-09-18","2026-09-24","SOC Level 1 introduction","Record all spending","Responsibilities of a husband"),
 ("2026-09-25","2026-10-01","SIEM fundamentals","Create a monthly budget","Healthy communication"),
 ("2026-10-02","2026-10-08","Windows logs and Sysmon","Calculate net worth","Conflict resolution"),
 ("2026-10-09","2026-10-15","Networking fundamentals","Set emergency-fund target","Define spouse-selection criteria"),
 ("2026-10-16","2026-10-22","MITRE ATT&CK","Create marriage budget","Begin the serious search process"),
 ("2026-10-23","2026-10-29","Phishing analysis","Understand inflation","Housing options and requirements"),
 ("2026-10-30","2026-11-05","Incident response","Investing fundamentals","Appliance and furniture requirements"),
 ("2026-11-06","2026-11-12","Active Directory security","Islamic-finance fundamentals","Household financial management"),
 ("2026-11-13","2026-11-19","Detection engineering","Sharia investment screening","Healthy boundaries"),
 ("2026-11-20","2026-11-26","Threat hunting","Gold as savings/investment","Parenting principles"),
 ("2026-11-27","2026-12-03","Build a practical project","Write personal investment rules","Review marriage readiness gaps"),
 ("2026-12-04","2026-12-10","Review SOC concepts","Draft the 2027 financial plan","Define next practical steps"),
 ("2026-12-11","2026-12-18","Finish project and interview notes","Final financial review","Final readiness review"),
]

def seed_personal_plan(user_id):
 db=get_db(); stamp=now()
 if db.execute("SELECT 1 FROM goals WHERE user_id=? AND type='year' AND title=? AND deleted_at IS NULL",(user_id,LIFETIME["spiritual"][1])).fetchone(): return "Personal plan already exists; no duplicate data created."
 cats={r["name_key"]:r["id"] for r in db.execute("SELECT id,name_key FROM categories WHERE user_id=? AND deleted_at IS NULL",(user_id,))}
 if not all(k in cats for k in LIFETIME): raise RuntimeError("Required categories are missing; profile provisioning must run first.")
 def goal(parent,typ,title,cat,start=None,end=None,description="",position=0,priority=0):
  cur=db.execute("INSERT INTO goals(uuid,user_id,parent_id,type,title,description,category_id,start_date,end_date,status,position,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'active',?,?,?,?)",(new_uuid(),user_id,parent,typ,title,description,cats[cat],start,end,position,priority,stamp,stamp)); return cur.lastrowid
 def task(title,cat,due=None,goal_id=None,parent=None,description="",minutes=None,recurrence=None,priority=0,time=None,status="open"):
  uid=new_uuid(); cur=db.execute("INSERT INTO tasks(uuid,user_id,goal_id,parent_task_id,category_id,title,description,status,priority,due_date,scheduled_time,estimated_minutes,recurrence,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(uid,user_id,goal_id,parent,cats.get(cat),title,description,status,priority,due,time,minutes,recurrence,stamp,stamp)); return cur.lastrowid
 roots={}; years={}; quarters={}; month_ids={}
 for pos,(cat,(life_title,year_title)) in enumerate(LIFETIME.items(),1):
  roots[cat]=goal(None,"lifetime",life_title,cat,description=life_title,position=pos)
  years[cat]=goal(roots[cat],"year",year_title,cat,"2026-01-01","2026-12-31",position=1)
  quarters[cat]=goal(years[cat],"quarter","Foundation Block: Discipline, Readiness and Growth",cat,START,END,OUTCOMES[cat],1,3)
  for mpos,(block,start,end,titles) in enumerate(MONTHS,1): month_ids[(cat,mpos)]=goal(quarters[cat],"month",titles[cat],cat,start,end,block,mpos,3)
 for index,(start,end,secops,finance,marriage) in enumerate(WEEKS,1):
  month=1 if index<=4 else 2 if index<=8 else 3
  titles={"secops":secops,"finance":finance,"marriage":marriage,"spiritual":f"Week {index}: prayer, Quran, PMO-free and muḥāsabah consistency","health":f"Week {index}: four sustainable gym sessions"}
  for cat,title in titles.items():
   wid=goal(month_ids[(cat,month)],"week",title,cat,start,end,f"Week {index}: {start} to {end}",index,3)
   task(title,cat,end,wid,minutes=45 if cat!="health" else 240,priority=2)
   if cat=="secops": task("Complete at least four SecOps focus blocks",cat,end,wid,minutes=180)
   elif cat=="spiritual":
    task("Quran — seven sessions",cat,end,wid); task("Five prayers — daily",cat,end,wid); task("Nightly muḥāsabah — seven opportunities",cat,end,wid); task("Friday weekly review", "personal",end,wid,minutes=30)
   elif cat=="health": task("Gym — four sessions",cat,end,wid,minutes=240)
 # Private challenge parent and milestones.
 challenge=task("60-Day PMO-Free Challenge","spiritual","2026-11-16",quarters["spiritual"],description="Private daily challenge. Record triggers without explicit detail, recover immediately, and avoid all-or-nothing thinking.",priority=3,recurrence="daily:2026-09-18..2026-11-16")
 for title,due,action in [("Day 1","2026-09-18","Start challenge and write reasons"),("Day 7","2026-09-24","Review triggers from the first week"),("Day 14","2026-10-01","Review routine and vulnerable times"),("Day 21","2026-10-08","Confirm replacement habits"),("Day 30","2026-10-17","Begin serious marriage searching"),("Day 40","2026-10-27","Review emotional and spiritual progress"),("Day 50","2026-11-06","Prepare the post-challenge routine"),("Day 60","2026-11-16","Complete challenge and write lessons learned")]: task(f"{title}: {action}","spiritual",due,quarters["spiritual"],challenge,priority=2)
 for title in ("Avoid triggering content","Follow the planned evening routine","Keep the phone away from bed","Record triggers without explicit detail","Recover immediately after a difficult moment","Make duʿāʾ and renew intention"): task(title,"spiritual",START,quarters["spiritual"],challenge,recurrence="daily:through:2026-11-16")
 # Habits: update known defaults, create missing entries, archive dormant defaults.
 habits=[("fajr","Fajr prayer","صلاة الفجر","spiritual","0,1,2,3,4,5,6","prayer_time",None),("dhuhr","Dhuhr prayer","صلاة الظهر","spiritual","0,1,2,3,4,5,6","prayer_time",None),("asr","Asr prayer","صلاة العصر","spiritual","0,1,2,3,4,5,6","prayer_time",None),("maghrib","Maghrib prayer","صلاة المغرب","spiritual","0,1,2,3,4,5,6","prayer_time",None),("isha","Isha prayer","صلاة العشاء","spiritual","0,1,2,3,4,5,6","prayer_time",None),("quran","Quran portion","ورد القرآن","spiritual","0,1,2,3,4,5,6","after_fajr","20 minutes"),("pmo_free","PMO-free day","يوم بلا محتوى إباحي","spiritual","0,1,2,3,4,5,6","all_day",None),("brush_am","Brush teeth — morning","تنظيف الأسنان — صباحًا","health","0,1,2,3,4,5,6","morning",None),("brush_pm","Brush teeth — night","تنظيف الأسنان — ليلًا","health","0,1,2,3,4,5,6","before_sleep",None),("family_daily","Family time without screens","وقت عائلي بلا شاشات","family_social","0,1,2,3,4,5,6","flexible","30 minutes"),("nightly_recap","Nightly muḥāsabah","محاسبة المساء","spiritual","0,1,2,3,4,5,6","before_sleep","5 minutes"),("weekly_review","Weekly review","المراجعة الأسبوعية","personal","4","flexible","30 minutes"),("gym","Gym","النادي الرياضي","health","0,1,3,5","flexible","60 minutes")]
 for key,en,ar,cat,days,tod,measurement in habits:
  h=db.execute("SELECT * FROM habits WHERE user_id=? AND key=?",(user_id,key)).fetchone()
  private="private" if key=="pmo_free" else "normal"; hstart=START if key=="pmo_free" else None; hend="2026-11-16" if key=="pmo_free" else None; failure="Record trigger, recover immediately and avoid all-or-nothing thinking" if key=="pmo_free" else None
  if h: db.execute("UPDATE habits SET name_en=?,name_ar=?,category_id=?,active=1,privacy=?,start_date=?,end_date=?,measurement=?,failure_handling=?,archived_at=NULL,deleted_at=NULL,updated_at=?,version=version+1 WHERE id=?",(en,ar,cats[cat],private,hstart,hend,measurement,failure,stamp,h["id"])); hid=h["id"]
  else: hid=db.execute("INSERT INTO habits(uuid,user_id,category_id,key,name_en,name_ar,active,privacy,start_date,end_date,measurement,failure_handling,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?,?)",(new_uuid(),user_id,cats[cat],key,en,ar,private,hstart,hend,measurement,failure,stamp,stamp)).lastrowid
  schedule=db.execute("SELECT id FROM habit_schedules WHERE habit_id=?",(hid,)).fetchone()
  if schedule: db.execute("UPDATE habit_schedules SET weekdays=?,time_of_day=?,updated_at=?,version=version+1 WHERE id=?",(days,tod,stamp,schedule["id"]))
  else: db.execute("INSERT INTO habit_schedules(uuid,habit_id,weekdays,time_of_day,updated_at) VALUES(?,?,?,?,?)",(new_uuid(),hid,days,tod,stamp))
 for key,en in (("leetcode","LeetCode"),("github_commit","GitHub commit"),("bootdev","Boot.dev"),("generic_reading","Generic reading habit")):
  if not db.execute("SELECT 1 FROM habits WHERE user_id=? AND key=?",(user_id,key)).fetchone(): db.execute("INSERT INTO habits(uuid,user_id,key,name_en,name_ar,active,selected_for_recap,privacy,created_at,updated_at,archived_at) VALUES(?,?,?,?,?,0,0,'normal',?,?,?)",(new_uuid(),user_id,key,en,en,stamp,stamp,stamp))
 # Flexible weekly routine templates.
 for title,cat,day,minutes in [("SecOps focus block","secops",0,45),("Gym","health",0,60),("Finance focus block","finance",1,45),("Gym","health",1,60),("SecOps focus block","secops",2,45),("Marriage preparation","marriage",2,45),("SecOps focus block","secops",3,45),("Gym","health",3,60),("Marriage preparation","marriage",4,45),("Weekly review and family","family_social",4,90),("Finance focus block","finance",5,45),("Gym","health",5,60),("SecOps focus block","secops",6,90),("Family/social time","family_social",6,60)]: task(title,cat,START,recurrence=f"weekly:{day}",minutes=minutes)
 # First day priority and subtasks.
 first=task("Complete the SOC Level 1 introduction","secops",START,month_ids[("secops",1)],description="First-day priority",minutes=45,priority=3)
 for title in ("Finish the room","Capture five useful notes","Write one concept I could explain in an interview"): task(title,"secops",START,month_ids[("secops",1)],first)
 # Explicit decisions: no invented financial or personal values.
 for title in ("Choose monthly income value","Choose current savings value","Choose monthly savings target","Choose emergency-fund target","Choose marriage-budget target"): task(title,"finance","2026-09-24",month_ids[("finance",1)],priority=2)
 for title in ("Choose marriage-search method and people involved","Choose preferred gym session time","Choose preferred nightly recap time"): task(title,"personal","2026-09-24",priority=2)
 # Verified primary/reference/optional resources on the SecOps yearly goal.
 for title,url,description,provider in [("TryHackMe SOC Level 1","https://tryhackme.com/path/outline/blueteam","Primary practical path covering SOC operations, SIEM, phishing, monitoring, malware, threat intelligence and capstones.","TryHackMe"),("MITRE ATT&CK","https://attack.mitre.org/","Reference for the MITRE ATT&CK week.","MITRE"),("Google Cybersecurity Professional Certificate","https://www.coursera.org/professional-certificates/google-cybersecurity","Optional secondary course; do not run simultaneously unless workload allows.","Coursera / Google")]: db.execute("INSERT INTO resources(uuid,user_id,goal_id,title,url,description,resource_type,provider,completed,updated_at) VALUES(?,?,?,?,?,?, 'course',?,0,?)",(new_uuid(),user_id,years["secops"],title,url,description,provider,stamp))
 db.commit(); return "Personal 2026 plan created successfully."
