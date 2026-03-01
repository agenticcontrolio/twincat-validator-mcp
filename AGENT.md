# AGENT.md

> This file is an example guide prompt for LLM agents using the TwinCAT Validator
> MCP server. Copy it into your project, client system prompt, or agent instructions
> and customise it to match your workflow.

## Purpose

This file defines how LLM agents must use the TwinCAT Validator MCP server.
Tool schemas alone are not enough. Follow this document to keep outputs
deterministic, policy-compliant, import-safe, and compile-safe.

## Scope

Applies to all TwinCAT artifacts touched by an agent:

- `.TcPOU`
- `.TcIO`
- `.TcDUT`
- `.TcGVL`

## Core Operating Principle

Use MCP tools as the source of truth for correctness. Never mark work complete
from manual inspection alone.

The server enforces policy server-side, but agents must still run the correct
workflow and report results correctly.

## MCP Tool Catalog (Current)

### Orchestration tools (default first choice)

1. `process_twincat_single`
   - Purpose: full strict pipeline for one file (`validate -> autofix -> validate`).
   - Use when: a task targets a single file.
   - Returns: final safety flags, blockers, done/next-action semantics.

2. `process_twincat_batch`
   - Purpose: full strict pipeline for multiple files/patterns.
   - Use when: subsystem, folder, or multi-file generation.
   - Returns: aggregated status with deterministic follow-up guidance.
   - Tip: use `response_mode="compact"` for large batches to avoid oversized payloads.

3. `get_effective_oop_policy`
   - Purpose: resolve effective OOP policy for a path (defaults + project override).
   - Use when: planning OOP architecture decisions, explaining rule behavior.
   - Note: policy is also included in orchestration responses.

4. `verify_determinism_batch`
   - Purpose: run strict orchestration twice and confirm per-file stability.
   - Use when: final acceptance for multi-file work.
   - Returns: `stable` plus first/second-pass `content_changed` flags.

5. `get_context_pack`
   - Purpose: get curated knowledge base entries and OOP policy scoped by workflow stage.
   - Stages:
     - `pre_generation`: high-priority non-fixable checks to get right on first pass.
     - `troubleshooting`: KB entries for specific `check_ids` (from blockers).
   - Use when: before generating code or after orchestration returns blockers.
   - Params: `stage`, `check_ids` (required for troubleshooting), `target_path`,
     `max_entries` (default 10), `include_examples` (default true).
   - Returns: `entries[]` with explanation/why_it_matters/examples, `effective_oop_policy`,
     `missing_check_ids`, truncation info.
   - Tip: pass `include_examples=false` to save tokens when only explanations needed.

### Validation/debug tools

6. `validate_file`
   - Purpose: validate one file with selected level/profile.
   - Use when: targeted diagnosis after orchestration blockers.

7. `validate_for_import`
   - Purpose: import/compile safety gate for one file.
   - Use when: user requests explicit import readiness confirmation.

8. `check_specific`
   - Purpose: run named checks only.
   - Use when: focused troubleshooting (for example `pou_structure_interface`).

9. `get_validation_summary`
   - Purpose: concise overview of validation results/check status.
   - Use when: reporting or triage.

10. `suggest_fixes`
    - Purpose: map issues to likely fix actions.
    - Use when: orchestration indicates unresolved blockers.

### Fix/generation tools

11. `autofix_file`
    - Purpose: apply registered fixes and return strict status.
    - Use when: orchestration unavailable or user asks manual flow.

12. `extract_methods_to_xml`
    - Purpose: promote inline ST `METHOD...END_METHOD` into proper `<Method>` XML.
    - Use when: blockers report inline-method structural violations.

13. `generate_skeleton`
    - Purpose: emit canonical skeleton for requested file type/subtype.
    - Use when: creating new files; always start from skeleton.

### Batch low-level tools

14. `validate_batch`
    - Purpose: validate file set without fixing.
    - Use when: manual diagnostics for many files.

15. `autofix_batch`
    - Purpose: apply fixes to file set without full orchestration wrapper.
    - Use when: manual batch remediation requested.

### Policy tools

16. `lint_oop_policy`
    - Purpose: validate the nearest `.twincat-validator.json` config file — checks key
      names, types, and value ranges.
    - Use when: a project uses a custom OOP policy file and validation behaves unexpectedly.

## Tool Selection Rules (Mandatory)

1. Resolve task scope first.
   - Single file: use `process_twincat_single`.
   - Multi-file/folder: use `process_twincat_batch`.

2. Do not start with low-level tools when an orchestration tool applies.

3. Use low-level tools only when:
   - orchestration returns unresolved issues and asks for targeted action, or
   - user explicitly asks for manual/debug flow.

## Prompt Intent Routing (Mandatory)

Before generation, classify the user request as either procedural PLC or OOP TwinCAT.

1. Procedural intent (no OOP requested)
   - Use `intent_profile="procedural"` in orchestration and validation tools.
   - Prefer procedural architecture (PROGRAM/FUNCTION_BLOCK without EXTENDS/IMPLEMENTS).
   - Do not force OOP patterns unless the prompt explicitly asks for them.
   - For guidance, call `get_context_pack(stage="pre_generation", intent_profile="procedural", target_path=...)`.

2. OOP intent (user asks for inheritance/interfaces/polymorphism/abstract base)
   - Use `intent_profile="oop"` in orchestration and validation tools.
   - Enforce full OOP policy and contracts.
   - For guidance, call `get_context_pack(stage="pre_generation", intent_profile="oop", target_path=...)`.

3. Ambiguous intent
   - Use `intent_profile="auto"` and report resolved intent from tool output (`intent_profile_resolved`).
   - If results conflict with user goals, rerun explicitly with `intent_profile="procedural"` or `intent_profile="oop"`.

4. Reporting requirement
   - Final report must include: `intent_profile_requested`, `intent_profile_resolved`, and
     `check_categories_executed`.

## OOP Workflow Contract (Mandatory)

For any OOP generation/modification task:

1. Call `get_effective_oop_policy(target_path=...)` at planning start.
2. Call `get_context_pack(stage="pre_generation", target_path=...)` for generation guidance.
3. Create files from `generate_skeleton` (never freehand full XML).
4. Write minimal required content.
5. Run orchestration (`process_twincat_single` or `process_twincat_batch`).
   For larger file sets, call `process_twincat_batch(..., response_mode="compact")`.
6. If blocked, call `get_context_pack(stage="troubleshooting", check_ids=[...from blockers...])`.
7. Apply one focused correction per iteration.
8. Re-run orchestration.
9. Stop on deterministic no-progress condition.

## Standard Autofix Profile (when manual flow is needed)

Use this default call unless user requests otherwise:

- `profile="llm_strict"`
- `create_backup=false`
- `strict_contract=true`
- `create_implicit_files=true`
- `orchestration_hints=true`
- `format_profile="twincat_canonical"`

### GUID integrity

- All GUIDs must be valid and lowercase.
- Placeholders/repeated-char fake GUIDs are not acceptable.

### Server-side rule design (generic first)

- Do not enforce domain behavior using hardcoded method names like `M_DoControl` or
  `M_InternalRecover`.
- Prefer structural/policy-driven checks (signatures, visibility, override markers,
  interface integrity, determinism).
- If semantic conventions are needed, make them configurable by policy or explicit
  attributes, not fixed names.

## Stop Conditions and Iteration Limits

1. Max 3 correction iterations per file.
2. Stop immediately when:
   - `no_change_detected == true` and file remains unsafe, or
   - `issue_fingerprint` repeats with `no_progress_count >= 2`.
3. Report exact blockers and mark as unresolved.

## Reporting Contract (Mandatory)

Every final report must include, per file:

1. `safe_to_import`
2. `safe_to_compile`
3. `blocking_count`
4. `fixes_applied`
5. whether content changed

Notes:
- Accept either `fixes_applied` or server-native `fixes_applied_count`.
- Keep field naming consistent within a single report.

For multi-file tasks, include:

1. created/modified file list
2. pass/fail summary table
3. unresolved blockers grouped by file
4. determinism result from second pass

## Structured Output Strategy (Mandatory)

Agent final reports should be deterministic and machine-parseable.
JSON-first is preferred when the user asks for structured output.

Required top-level JSON shape:

```json
{
  "workflow": {
    "tool": "process_twincat_single|process_twincat_batch",
    "policy_checked": true,
    "determinism_pass": true
  },
  "summary": {
    "total_files": 0,
    "passed": 0,
    "failed": 0,
    "warnings": 0
  },
  "files": [
    {
      "path": "",
      "safe_to_import": true,
      "safe_to_compile": true,
      "blocking_count": 0,
      "fixes_applied": 0,
      "content_changed": false
    }
  ],
  "blockers": [
    {
      "path": "",
      "check": "",
      "message": "",
      "line": 0
    }
  ],
  "status": "done|blocked"
}
```

Rules:
- Do not output `status: "done"` unless all changed files have:
  - `safe_to_import == true`
  - `safe_to_compile == true`
  - `blocking_count == 0`
  - determinism pass with `content_changed == false` on second pass
- If any blocker exists, set `status: "blocked"` and populate `blockers`.
- Do not substitute prose summaries for required JSON fields.

## Determinism Requirement

After a passing run, execute one more orchestration pass.
Expected result:

- no additional fixes
- unchanged content fingerprints
- stable safety flags

If not stable, result is not done.

## Definition of Done

A TwinCAT task is complete only when all changed files satisfy:

1. strict orchestration/autofix contract
2. `safe_to_import == true`
3. `safe_to_compile == true`
4. no unresolved blockers
5. determinism pass confirms no changes

## If MCP Is Unavailable

If MCP cannot be used:

1. explicitly state results are unverified
2. provide best-effort edits only
3. require MCP validation before acceptance
