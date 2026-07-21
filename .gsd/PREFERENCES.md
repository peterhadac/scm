---
version: 1
mode: team
models:
  research: localhost/Intel/Qwen3-Coder-Next-int4-AutoRound
  planning: localhost/Intel/Qwen3-Coder-Next-int4-AutoRound
git:
  isolation: worktree
  main_branch: main
  auto_push: false
dynamic_routing:
  enabled: false
  capability_routing: false
  escalate_on_failure: false
  budget_pressure: false
  cross_provider: false
  hooks: false
  allow_flat_rate_providers: false
  tier_models:
    light: Intel/Qwen3-Coder-Next-int4-AutoRound
    standard: Intel/Qwen3-Coder-Next-int4-AutoRound
    heavy: Intel/Qwen3-Coder-Next-int4-AutoRound
token_profile: quality
service_tier: priority
verification_commands:
  - pnpm test
  - pnpm run build
  - pytest
---
# GSD Skill Preferences

See `~/.gsd/agent/extensions/gsd/docs/preferences-reference.md` for full field documentation and examples.
