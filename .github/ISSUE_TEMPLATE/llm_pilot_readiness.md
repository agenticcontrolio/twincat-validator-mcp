---
name: LLM pilot readiness
about: Track Phase 5A.1 real-model pilot readiness and evidence
title: "[PILOT] Phase 5A.1 LLM pilot readiness"
labels: pilot, phase-5, tracking
assignees: ""
---

## Goal

Track readiness to start and complete the real-LLM pilot (Phase 5A.1).

## Scope Confirmation

- [ ] Workflow under test is exactly: `write file -> autofix_file(profile="llm_strict") -> branch on safe/blockers`
- [ ] File scope is single-file only (`.TcPOU`, `.TcDUT`, `.TcGVL`, `.TcIO`)
- [ ] Model scope is fixed (1-2 models max) with fixed prompts and fixed evaluation corpus

## Required Prep

- [ ] README contract-freeze note exists for `llm_strict` response fields
  - Evidence:
- [ ] End-to-end tests call public MCP tools for:
  - [ ] fixable path
  - [ ] warning-only path
  - [ ] unfixable blocker path
  - Evidence:
- [ ] Minimal telemetry is captured per call:
  - [ ] `tool_name`
  - [ ] `duration_ms`
  - [ ] `file_type`
  - [ ] `fixes_applied_count`
  - [ ] `blocking_count`
  - Evidence:
- [ ] Reference harness exists and is documented:
  - [ ] writes generated file
  - [ ] calls `autofix_file(profile="llm_strict")`
  - [ ] applies branch logic from `safe_to_import` and `blockers`
  - Evidence:

## Pilot Metrics (Pass/Fail)

- [ ] Determinism drift: `0` mismatches on repeated identical inputs
  - Result:
  - Evidence:
- [ ] Import safety: `>=95%` of fixable corpus ends with `safe_to_import=True` in one pass
  - Result:
  - Evidence:
- [ ] Compile safety proxy: `>=90%` of corpus ends with `safe_to_compile=True` in one pass
  - Result:
  - Evidence:
- [ ] Blocker precision: `100%` of known-unfixable fixtures report `blocking_count > 0`
  - Result:
  - Evidence:
- [ ] Latency budget:
  - [ ] p95 `autofix_file <= 500ms`
  - [ ] p99 `autofix_file <= 1000ms`
  - Result:
  - Evidence:
- [ ] Token/size budget: median strict response `<= 600 bytes` on standard fixture set
  - Result:
  - Evidence:

## Exit Criteria

- [ ] All pilot metrics pass in `3` consecutive runs
- [ ] No `llm_strict` contract/schema changes required
- [ ] No flaky failures in determinism/contract test suites

## Final Decision

- [ ] Ready to proceed beyond pilot
- [ ] Not ready (requires remediation)

## Notes

Add blockers, follow-ups, and links to runs/PRs here.
