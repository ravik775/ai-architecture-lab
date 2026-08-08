CREATE TABLE chat_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       VARCHAR(64)  NOT NULL,
    user_sub        VARCHAR(128) NOT NULL,
    question        TEXT         NOT NULL,
    answer_snippet  VARCHAR(500) NOT NULL,
    trace_id        VARCHAR(64),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- Every tenant-scoped read in the app filters by tenant_id; this index is what keeps
-- that filter cheap instead of a sequential scan as the table grows.
CREATE INDEX idx_chat_audit_log_tenant_id ON chat_audit_log (tenant_id, created_at DESC);
