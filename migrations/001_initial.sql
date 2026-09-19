PRAGMA foreign_keys=ON;
CREATE TABLE users (
 id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password_hash TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '', timezone TEXT NOT NULL DEFAULT 'Africa/Cairo',
 language TEXT NOT NULL DEFAULT 'en' CHECK(language IN ('ar','en')), created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT
);
CREATE TABLE categories (
 id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), name_key TEXT,
 name TEXT NOT NULL, color TEXT NOT NULL, icon TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
 position INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT,
 UNIQUE(user_id,name)
);
CREATE TABLE tags (id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT, UNIQUE(user_id,name));
CREATE TABLE goals (
 id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), parent_id INTEGER REFERENCES goals(id),
 type TEXT NOT NULL CHECK(type IN ('lifetime','year','quarter','month','week')), title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 category_id INTEGER REFERENCES categories(id), start_date TEXT, end_date TEXT, status TEXT NOT NULL DEFAULT 'active', position INTEGER NOT NULL DEFAULT 0,
 progress_mode TEXT NOT NULL DEFAULT 'descendants', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived_at TEXT, deleted_at TEXT, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE tasks (
 id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), goal_id INTEGER REFERENCES goals(id), parent_task_id INTEGER REFERENCES tasks(id),
 category_id INTEGER REFERENCES categories(id), title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', priority INTEGER NOT NULL DEFAULT 0,
 due_date TEXT, scheduled_time TEXT, estimated_minutes INTEGER, recurrence TEXT, position INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT, archived_at TEXT, deleted_at TEXT, version INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE task_tags(task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE, tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE, PRIMARY KEY(task_id,tag_id));
CREATE TABLE habits (
 id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), category_id INTEGER REFERENCES categories(id),
 key TEXT, name_en TEXT NOT NULL, name_ar TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, selected_for_recap INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT
);
CREATE TABLE habit_schedules(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, habit_id INTEGER NOT NULL REFERENCES habits(id), weekdays TEXT NOT NULL DEFAULT '0,1,2,3,4,5,6', time_of_day TEXT, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT);
CREATE TABLE habit_entries(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, habit_id INTEGER NOT NULL REFERENCES habits(id), user_id INTEGER NOT NULL REFERENCES users(id), entry_date TEXT NOT NULL, completed INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT, UNIQUE(habit_id,entry_date));
CREATE TABLE recap_templates(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), name_en TEXT NOT NULL, name_ar TEXT NOT NULL, intro_en TEXT NOT NULL, intro_ar TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, current_version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT);
CREATE TABLE recap_template_versions(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, template_id INTEGER NOT NULL REFERENCES recap_templates(id), version_number INTEGER NOT NULL, snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(template_id,version_number));
CREATE TABLE recap_template_fields(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, template_id INTEGER NOT NULL REFERENCES recap_templates(id), stable_key TEXT NOT NULL, label_en TEXT NOT NULL, label_ar TEXT NOT NULL, placeholder_en TEXT NOT NULL DEFAULT '', placeholder_ar TEXT NOT NULL DEFAULT '', field_type TEXT NOT NULL DEFAULT 'long_text', required INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL, config_json TEXT NOT NULL DEFAULT '{}', updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT, UNIQUE(template_id,stable_key));
CREATE TABLE recaps(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), recap_date TEXT NOT NULL, template_id INTEGER REFERENCES recap_templates(id), template_version INTEGER NOT NULL, template_snapshot_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT, UNIQUE(user_id,recap_date));
CREATE TABLE recap_answers(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, recap_id INTEGER NOT NULL REFERENCES recaps(id) ON DELETE CASCADE, field_key TEXT NOT NULL, answer_json TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT, UNIQUE(recap_id,field_key));
CREATE TABLE resources(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), goal_id INTEGER REFERENCES goals(id), task_id INTEGER REFERENCES tasks(id), title TEXT NOT NULL, url TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', resource_type TEXT NOT NULL, provider TEXT, completed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, deleted_at TEXT);
CREATE TABLE api_tokens(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL, token_prefix TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, scopes TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT, last_used_at TEXT, revoked_at TEXT);
CREATE TABLE audit_events(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), actor_type TEXT NOT NULL, token_id INTEGER REFERENCES api_tokens(id), action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_uuid TEXT, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE TABLE sync_changes(id INTEGER PRIMARY KEY, cursor INTEGER NOT NULL UNIQUE, mutation_uuid TEXT UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), entity_type TEXT NOT NULL, entity_uuid TEXT NOT NULL, operation TEXT NOT NULL, record_json TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE user_sessions(id INTEGER PRIMARY KEY, uuid TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, revoked_at TEXT, user_agent TEXT);
CREATE INDEX idx_goals_owner_parent ON goals(user_id,parent_id,deleted_at);
CREATE INDEX idx_tasks_owner_due ON tasks(user_id,due_date,deleted_at);
CREATE INDEX idx_habit_entries_owner_date ON habit_entries(user_id,entry_date);
CREATE INDEX idx_recaps_owner_date ON recaps(user_id,recap_date);
CREATE INDEX idx_sync_owner_cursor ON sync_changes(user_id,cursor);
CREATE INDEX idx_audit_owner_time ON audit_events(user_id,created_at);
