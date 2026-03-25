# Changelog

## [2.1.0] - 2026-03-25

### Added
- Three-path startup: warm start (config + healthcheck → instant), cold start (first-time guide), fallback (partial re-guide)
- CLI-level healthcheck commands per model in config (`healthcheck` field), verified: `codex exec --help`, `gemini -v`, `crush models`
- `schema_version` and `last_verified` fields in config for future-proofing
- Crush CLI section in docs with `--quiet` flag for clean output

### Changed
- Preflight downgraged from model-level (`echo "ping" | codex exec`) to CLI-level (help/version checks), runs once per session not per round
- Warm start skips user confirmation — non-blocking notification only
- Fixed Gemini invoke example: `gemini -p "{prompt}"` (not `echo | gemini -p` which leaves `-p` without a value)
- Fixed Crush invoke example: `crush run --quiet` (not `crush chat`)

### Fixed
- Gemini CLI syntax error in SKILL.md that caused 2-3 rounds of trial-and-error on first use
- Crush CLI subcommand error (`chat` → `run`) in config template
- Preflight wasting tokens by calling models to respond to "ping"

## [2.0.0] - 2026-03-23

### Added
- CLI configuration persistence (`~/.config/cross-review/models.yaml`): remember user's CLI tools and invocation methods across sessions
- Model name → CLI mapping: say "GLM-4.7" and it auto-resolves to the right CLI (e.g., `crush`)
- Output contract: suggested output skeleton + "no thinking/logs" constraint for all external model prompts
- Two-layer output validation: transport validation (non-empty, no auth noise) + semantic validation (expected headings, substance)
- Digest protocol (optional): lead model creates digests only when output exceeds 5000 words; default passes clean outputs directly
- Round 2.5 focused rebuttal (full mode): resolves critical conflicts before synthesis
- Round 4 emphasis assignment: all models do all 4 checks, but each has designated emphasis items for deeper analysis
- Round 4 → Round 3b loop: Critical findings trigger targeted revision instead of restarting
- `manifest.json` for checkpoint/resume across interruptions
- Preflight checks before each external model call
- `invalid/` subdirectory for failed validation outputs

### Changed
- Codex invocation: `--output-last-message` + `--ephemeral` + `--color never` to eliminate output bloat
- Round 3 reframed from "optimal solution" to "candidate synthesis" with assumption ledger
- Quick mode synthesis now requires explicit verdict on disagreements (not just listing)
- Round 2 prompt prohibits restating Round 1 content; only incremental contributions allowed
- Directory structure: timestamped run directories (`run-YYYYMMDD-HHmm/`) instead of flat directory
- File naming: strict `r{N}.{model}.md` format, no free-form suffixes

### Fixed
- Output bloat from Codex (25-50KB of session noise → clean final message via `--output-last-message`)
- Empty/corrupted files from Gemini (auth prompts, 0-byte outputs) caught by transport validation
- Naming chaos (free-form suffixes like `-ws`, `-session-fix`, `-v2`) prevented by strict naming rules
- Noise amplification across rounds (raw outputs with metadata fed to next round → now clean outputs via `--output-last-message`, with optional digest for very long outputs)
- Premature synthesis in Round 3 (presented as "final" → now explicitly "candidate")

## [1.0.0] - 2026-03-11

### Added
- Initial open-source release
- Quick mode (2-round) and Full mode (4-round) workflows
- Model-agnostic design supporting Claude, Codex, Gemini, and other AI CLI tools
- Perspective-based task assignment for technical, product, and creative tasks
- Adversarial Round 4 with devil's advocate and stress testing
- 4 mandatory attack checks: loop detection, scenario walkthrough, removal test, consensus blind spot detection
- Graceful degradation from 3 models to 1
- Bilingual trigger support (English + Chinese)
- Intermediate result management with session resume capability
