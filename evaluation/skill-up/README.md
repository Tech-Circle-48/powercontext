# PowerContext Skill-up guidance regression suite

This suite is a versioned, reproducible regression check for the packaged Claude Code
`powercontext-project-context` Skill. It measures deterministic Skill-text-to-tool-selection
and result-reporting behavior through skill-up transcripts. It targets only the skill-up
`claude_code` engine with the PowerContext MCP transport: it is not evidence for Codex,
Hermes, WorkBuddy, OpenCode, Pi, OpenClaw, the portable Agent Plugin, or any other host.

The suite contains an ordinary-coding negative control, an explicit Memory-save positive
control, empty Memory search, read-only Artifact Candidate inspection, and a controlled
failed-write reporting case. The checked-in configuration keeps `cases.parallelism: 1`,
loads the vendored Skill, runs the loaded/unloaded benchmark, and requests JSON, JUnit,
HTML, and transcript artifacts.

## Prerequisites and isolated Server

Run all commands from the repository root with a Claude Code installation and credentials
that skill-up can use. The lock requires this exact CLI version:

```bash
test "$(skill-up version)" = "skill-up version 0.12.0"
evaluation/skill-up/sync-skill.sh --check
export POWERCONTEXT_SKILL_UP_ROOT="$(mktemp -d)"
export POWERCONTEXT_SERVER_DATABASE_URL="sqlite+aiosqlite:///$POWERCONTEXT_SKILL_UP_ROOT/powercontext.db"
export CLAUDE_PLUGIN_ROOT="$(pwd -P)/evaluation/skill-up/vendor/powercontext-plugin"
uv run powercontext server run --no-env-file
```

Keep this Server running in a dedicated terminal. Make a new
`POWERCONTEXT_SKILL_UP_ROOT` and database for every real run; do not point the suite at a
developer database or reuse a previous run's database. Serial case execution makes the
fresh database's state and case ordering deterministic.

The default real MCP endpoint is `http://127.0.0.1:8000/mcp`. Its Authorization header is
read from `evals/fixtures/mcp/powercontext.yaml` through `config_ref`, not from
`mcp.servers[]`; do not move the header into the server declaration. For an authenticated
isolated Server, use a disposable fixture token in both terminals before starting it:

```bash
export POWERCONTEXT_SERVER_ACCESS_MODE=enforced
export POWERCONTEXT_SERVER_AUTH_TOKEN=skill-up-fixture-token
export POWERCONTEXT_CLAUDE_AUTHORIZATION="Bearer skill-up-fixture-token"
```

An unauthenticated local Server may use an empty complete header only if skill-up and
Claude Code accept it. Otherwise, start the isolated Server with the fixture bearer token
above so the `config_ref` path is exercised consistently. Never commit a real credential.

## Validate and run

In the evaluation terminal, wait for readiness, export the complete header value when
authentication is enabled, validate the configuration, then run the positional evaluation
path. `--config` is global skill-up user configuration; it is not the evaluation path.

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/health/ready
export POWERCONTEXT_CLAUDE_AUTHORIZATION="Bearer <token>"
skill-up validate evaluation/skill-up/evals/eval.yaml
skill-up run evaluation/skill-up/evals/eval.yaml --baseline \
  --output-dir /tmp/powercontext-skill-up-first-run
```

The final command records Skill-loaded and unloaded benchmark results separately. Treat a
baseline comparison as a routing-regression comparison for this invocation, not as an
absolute model-quality score. Preserve the JSON, JUnit, HTML, and transcript artifacts from
the output directory selected by skill-up. Do not replace those artifacts with a summary
that omits a failed case.

## Transcript inventory and case interpretation

After a real run, inventory the recorded names before accepting or changing assertions. The
assertions use exact string equality in skill-up v0.12.0, so a similarly named operation or
an assumed namespace does not count.

```bash
rg -o '"name":"[^"]+"' /tmp/powercontext-skill-up-first-run -g '*.json' -g '*.jsonl' \
  | sort -u
```

The normal cases connect to the isolated real Server. A real-mode write is evidence only
for that fresh evaluation Server and must remain readable through its supported path before
it is described as persistence evidence. The failed-Memory-save case alone replaces the
`powercontext` server with a case-level mocked MCP fixture. That mock exposes the production
tool name and returns a controlled failure; it tests attempted routing and truthful reporting,
not real persistence or an end-to-end Server failure.

## Lifecycle and limitations

The runnable lifecycle is: verify the pinned skill and vendor lock; create a fresh SQLite
database; start the isolated Server; wait for readiness; validate; run the benchmark; inspect
the five case outcomes and baseline comparison; inventory transcript tool names; retain all
four report artifact kinds; then stop the Server and discard the temporary database. Generated
workspaces and reports stay outside the vendored Skill. Do not modify the local `.skill-up.yaml`,
temporary Skill-local `evals/`, or generated Skill workspace as part of this suite.

skill-up's Claude Code runner uses `disableAllHooks` and `bypassPermissions`. Consequently,
this suite does not measure bounded recall, automatic Capture/Flush, real host approval
prompts, Memory quality, successful injection into a later prompt, full persistence
correctness, or any host other than Claude Code + MCP. It does not prove automatic Skill
discovery, publication, installation, commitment, execution, or end-to-end approval behavior.
Mocked failures are never presented as real persistence evidence.
