PRAGMA foreign_keys = ON;
BEGIN;
/* ===================== employers ===================== */
CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    contacts_status TEXT,
    -- Статус контактов: not_checked/no_contacts/has_contacts
    site_url TEXT,
    alternate_url TEXT,
    open_vacancies INTEGER DEFAULT 0,
    total_responses INTEGER DEFAULT 0,
    avg_responses REAL DEFAULT 0.0,
    industries TEXT,
    -- JSON array
    area_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
/* ===================== ИНДЕКСЫ ===================== */
CREATE INDEX IF NOT EXISTS idx_employers_updated ON employers(updated_at);
/* ===================== ТРИГГЕРЫ (Всегда обновляют дату) ===================== */
CREATE TRIGGER IF NOT EXISTS trg_employers_updated
AFTER
UPDATE ON employers BEGIN
UPDATE employers
SET updated_at = CURRENT_TIMESTAMP
WHERE id = OLD.id;
END;
COMMIT;