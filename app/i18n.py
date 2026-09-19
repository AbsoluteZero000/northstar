from flask import g

TRANSLATIONS = {
    "en": {
        "app_name": "Hayat", "today": "Today", "week": "Week", "goals": "Goals",
        "statistics": "Statistics", "settings": "Settings", "logout": "Log out",
        "login": "Log in", "register": "Create account", "email": "Email", "password": "Password",
        "language": "Language", "timezone": "Timezone", "save": "Save", "add_task": "Add task",
        "task_title": "What needs doing?", "progress": "Progress", "habits": "Habits",
        "tasks": "Tasks", "offline": "Offline", "online": "Online", "sync": "Sync now",
        "nightly_title": "Nightly Muḥāsabah",
        "nightly_intro": "A quiet moment of gratitude, reflection and sincere intention before ending the day.",
        "save_draft": "Save draft", "complete_recap": "Complete recap", "api_tokens": "API tokens",
        "categories": "Categories", "trash": "Trash", "audit": "Audit history", "no_items": "Nothing here yet.",
        "invalid_login": "Invalid email or password.", "csrf_error": "Your session expired. Please try again.",
    },
    "ar": {
        "app_name": "حياة", "today": "اليوم", "week": "الأسبوع", "goals": "الأهداف",
        "statistics": "الإحصاءات", "settings": "الإعدادات", "logout": "تسجيل الخروج",
        "login": "تسجيل الدخول", "register": "إنشاء حساب", "email": "البريد الإلكتروني", "password": "كلمة المرور",
        "language": "اللغة", "timezone": "المنطقة الزمنية", "save": "حفظ", "add_task": "إضافة مهمة",
        "task_title": "ما الذي تريد إنجازه؟", "progress": "التقدم", "habits": "العادات",
        "tasks": "المهام", "offline": "غير متصل", "online": "متصل", "sync": "مزامنة الآن",
        "nightly_title": "محاسبة المساء",
        "nightly_intro": "لحظة هادئة للشكر والمراجعة وتجديد النية قبل أن ينتهي اليوم.",
        "save_draft": "حفظ المسودة", "complete_recap": "إكمال المحاسبة", "api_tokens": "رموز API",
        "categories": "التصنيفات", "trash": "المحذوفات", "audit": "سجل التدقيق", "no_items": "لا توجد عناصر بعد.",
        "invalid_login": "البريد الإلكتروني أو كلمة المرور غير صحيحة.", "csrf_error": "انتهت الجلسة. حاول مرة أخرى.",
    },
}


def t(key, locale=None):
    lang = locale or getattr(g, "locale", "en")
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, key)

