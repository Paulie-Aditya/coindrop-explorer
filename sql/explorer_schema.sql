-- Additive-only. Own table, no foreign keys into the bot/api schema.
-- Run manually against the shared `coindrop` DB (see deploy/deploy.sh).

CREATE TABLE IF NOT EXISTS visits (
    id          BIGINT       AUTO_INCREMENT PRIMARY KEY,
    chain_id    INT          NULL,
    chain_slug  VARCHAR(20)  NULL,
    tx_hash     VARCHAR(128) NOT NULL,
    token_valid TINYINT(1)   NOT NULL DEFAULT 0,
    referrer    VARCHAR(255) NULL,
    user_agent  VARCHAR(255) NULL,
    ip_hash     CHAR(64)     NULL,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    KEY idx_chain_created (chain_id, created_at),
    KEY idx_tx_hash (tx_hash)
);
