-- Agent actions queue — the "execute" arrow of the autonomous loop.
--
-- Lifecycle:
--   planner produces a row with status='pending_approval'
--     → notifier posts it to Telegram with Approve/Reject inline buttons
--       → user clicks Approve → status='approved'
--         → executor picks it up (cron every 5m) → status='executing'
--           → Meta MCP call made → status='executed' (with result_json) or 'failed'
--
--   If user clicks Reject → status='rejected', never runs
--   If 72h pass without action → status='expired', never runs
--   If action proves wrong afterward → status='rolled_back' (operator triggered)
--
-- ALL actions for Ayurpet go to Telegram group -5191631616 (Ayurpet X Glitch Grow)
-- and REQUIRE human approval before execution. No autonomy threshold bypass in v1.
--
-- Apply: sudo -u postgres psql -d shopify_app -f ops/scripts/migrate_agent_actions.sql

CREATE TABLE IF NOT EXISTS ads_agent.agent_actions (
    id                  bigserial PRIMARY KEY,
    created_at          timestamptz NOT NULL DEFAULT NOW(),
    expires_at          timestamptz NOT NULL DEFAULT NOW() + INTERVAL '72 hours',

    -- What & where
    store_slug          text        NOT NULL,
    action_kind         text        NOT NULL,   -- pause_adset | resume_adset | update_adset_budget | pause_ad | update_ad
    target_object_id    text        NOT NULL,   -- adset_id or ad_id
    target_object_name  text,                   -- human-readable name for UI
    params              jsonb       NOT NULL DEFAULT '{}'::jsonb,  -- {"new_daily_budget":15000} etc.
    rationale           text        NOT NULL,   -- why the agent proposes this — shown in Telegram

    -- Supporting evidence at time of proposal (freeze-dried snapshot)
    evidence            jsonb,                  -- {"current_roas":0.81,"spend_30d":26997, ...}
    expected_impact     jsonb,                  -- {"expected_roas_delta":+0.5,"expected_monthly_inr":25000}

    -- Lifecycle
    status              text        NOT NULL DEFAULT 'pending_approval'
                        CHECK (status IN ('pending_approval','approved','executing',
                                          'executed','rejected','expired','failed','rolled_back')),

    -- Approval audit
    telegram_message_id bigint,                 -- message ID of the Approve/Reject post, for edits
    telegram_chat_id    bigint,                 -- which group received it
    approved_by         bigint,                 -- telegram user id who clicked Approve
    approved_at         timestamptz,
    rejected_by         bigint,
    rejected_at         timestamptz,

    -- Execution audit
    executed_at         timestamptz,
    result              jsonb,                  -- MCP response or error
    prior_state         jsonb,                  -- snapshot of target before execute (for rollback)

    -- Rollback linkage (if this action rolls back another)
    rolls_back_action_id bigint REFERENCES ads_agent.agent_actions(id)
);

-- Index patterns
CREATE INDEX IF NOT EXISTS agent_actions_store_status_ts
    ON ads_agent.agent_actions (store_slug, status, created_at DESC);

CREATE INDEX IF NOT EXISTS agent_actions_pending_idx
    ON ads_agent.agent_actions (status, expires_at)
    WHERE status = 'pending_approval';

CREATE INDEX IF NOT EXISTS agent_actions_approved_idx
    ON ads_agent.agent_actions (status, approved_at)
    WHERE status = 'approved';

-- Grants
GRANT SELECT, INSERT, UPDATE ON ads_agent.agent_actions TO shopify_app;
GRANT USAGE, SELECT ON SEQUENCE ads_agent.agent_actions_id_seq TO shopify_app;
