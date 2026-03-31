PRAGMA foreign_keys = ON;
BEGIN;

/* ===================== employers ===================== */
CREATE TABLE IF NOT EXISTS employers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    site_url TEXT,
    alternate_url TEXT,
    open_vacancies INTEGER DEFAULT 0,
    total_responses INTEGER DEFAULT 0,
    avg_responses REAL DEFAULT 0.0,
    industries TEXT,  -- JSON array
    area_name TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

/* ===================== vacancies ===================== */
CREATE TABLE IF NOT EXISTS vacancies (
    id INTEGER PRIMARY KEY,
    employer_id INTEGER NOT NULL,
    name TEXT,
    responses_count INTEGER DEFAULT 0,
    total_responses INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employer_id) REFERENCES employers(id)
);

/* ===================== ИНДЕКСЫ ===================== */
CREATE INDEX IF NOT EXISTS idx_employers_updated ON employers(updated_at);
CREATE INDEX IF NOT EXISTS idx_vacancies_employer ON vacancies(employer_id);

/* ===================== ТРИГГЕРЫ (Всегда обновляют дату) ===================== */
CREATE TRIGGER IF NOT EXISTS trg_employers_updated
AFTER
UPDATE ON employers BEGIN
UPDATE employers
SET updated_at = CURRENT_TIMESTAMP
WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_vacancies_updated
AFTER
UPDATE ON vacancies BEGIN
UPDATE vacancies
SET updated_at = CURRENT_TIMESTAMP
WHERE id = OLD.id;
END;

COMMIT;