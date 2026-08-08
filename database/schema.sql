-- SQLite/PostgreSQL-optional conceptual schema for the next increment.
CREATE TABLE IF NOT EXISTS audit_logs (id INTEGER PRIMARY KEY, user_id TEXT, action TEXT, patient_id TEXT, created_at TEXT);
