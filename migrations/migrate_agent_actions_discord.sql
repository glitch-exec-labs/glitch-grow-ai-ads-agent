-- 2026-04-25 · Discord-side approval columns on ads_agent.agent_actions.
--
-- Telegram cols (telegram_chat_id, telegram_message_id) are kept so existing
-- pending rows continue to resolve via Telegram during the 48h cutover; new
-- rows can carry either or both. After cutover we'll keep the cols around
-- as historical attestation — never DROP without a separate migration.
--
-- approval_platform records which platform produced the resolved click:
--   'telegram'           — original behaviour
--   'discord'            — new
--   'dual'               — posted to both during cutover; resolved from one
--   NULL                 — pending, no resolution yet (use posted-platform)

ALTER TABLE ads_agent.agent_actions
  ADD COLUMN IF NOT EXISTS discord_channel_id  BIGINT,
  ADD COLUMN IF NOT EXISTS discord_message_id  BIGINT,
  ADD COLUMN IF NOT EXISTS approval_platform   TEXT,
  -- Platform-prefixed approver identity ("tg:12345" or "discord:987654321")
  -- alongside the legacy integer `approved_by` (Telegram user_id only).
  -- Resolver writes to *_by_text for all new resolutions; the old INT
  -- columns stop being written and remain only for historical rows.
  ADD COLUMN IF NOT EXISTS approved_by_text    TEXT,
  ADD COLUMN IF NOT EXISTS rejected_by_text    TEXT;

-- Convenience: index for the consumer's "find row by Discord message_id" lookup
CREATE INDEX IF NOT EXISTS agent_actions_discord_msg_idx
  ON ads_agent.agent_actions (discord_message_id)
  WHERE discord_message_id IS NOT NULL;
