# Demo Playbook · v0 (placeholder)

This file is a **generic example** of the playbook format the public engine
expects. Real per-brand playbooks (with tuned thresholds, account IDs, and
strategy) live in the proprietary `glitch-grow-ads-playbook` package and
are loaded at runtime if installed.

If `glitch_grow_ads_playbook` is not on sys.path, the engine falls back to
this directory — a brand named `"demo"` will resolve here.

## I · Operating context

| Attribute | Value |
|---|---|
| Brand | Demo |
| Vertical | — |
| Lifecycle stage | — |

## IX · Numeric rules

```yaml
# Placeholder — replace via the private playbook package.
pause_roas_threshold: 1.0
scale_roas_threshold: 3.0
dedup_hours: 24
```

## X · Per-node briefs

### `ideas` node

```
Generic demo brief. Install glitch-grow-ads-playbook for the real one.
```
