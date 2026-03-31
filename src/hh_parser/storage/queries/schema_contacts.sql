-- Схема таблицы контактов работодателей
-- Добавляется к существующей схеме через миграцию
PRAGMA foreign_keys = ON;
/* ===================== contacts ===================== */
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employer_id INTEGER NOT NULL,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('email', 'phone')),
    value TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('api', 'site')),
    source_url TEXT,
    normalized_value TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employer_id) REFERENCES employers(id) ON DELETE CASCADE
);
/* ===================== ИНДЕКСЫ ===================== */
CREATE INDEX IF NOT EXISTS idx_contacts_employer ON contacts(employer_id);
CREATE INDEX IF NOT EXISTS idx_contacts_type ON contacts(contact_type);
CREATE INDEX IF NOT EXISTS idx_contacts_normalized ON contacts(normalized_value);
CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_unique ON contacts(employer_id, contact_type, normalized_value);
/* ===================== ТРИГГЕРЫ ===================== */
CREATE TRIGGER IF NOT EXISTS trg_contacts_updated
AFTER
UPDATE ON contacts BEGIN
UPDATE contacts
SET created_at = CURRENT_TIMESTAMP
WHERE id = OLD.id;
END;