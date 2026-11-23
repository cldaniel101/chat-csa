-- Migração isolada do painel administrativo do Chat CSA.
-- Usa exclusivamente tabelas prefixadas com `chat_csa_` e `IF NOT EXISTS`
-- para não impactar tabelas de outros projetos no mesmo banco PostgreSQL.

CREATE TABLE IF NOT EXISTS chat_csa_admin_users (
    id TEXT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'editor',
    is_superadmin BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    token_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_chat_csa_admin_users_username
    ON chat_csa_admin_users (username);

CREATE TABLE IF NOT EXISTS chat_csa_audit_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    username VARCHAR(64) NOT NULL,
    user_role VARCHAR(32) NOT NULL,
    action VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_created_at
    ON chat_csa_audit_logs (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_user_id
    ON chat_csa_audit_logs (user_id);

CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_action
    ON chat_csa_audit_logs (action);

CREATE INDEX IF NOT EXISTS idx_chat_csa_audit_logs_resource
    ON chat_csa_audit_logs (resource_type, resource_id);
