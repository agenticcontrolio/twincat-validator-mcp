# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-01

### Added - Core Server

- **8 MCP Tools**: validate_file, autofix_file, validate_batch, autofix_batch, validate_for_import, check_specific, get_validation_summary, suggest_fixes
- **7 MCP Resources**: validation-rules://, fix-capabilities://, naming-conventions://, config://server-info, knowledge-base://, knowledge-base://checks/{id}, knowledge-base://fixes/{id}
- **13 Validation Checks**: XML structure, GUID format/uniqueness, Property VAR blocks, LineIds count, file ending, indentation, tabs, CDATA, naming conventions, element ordering, excessive blank lines, POU structure
- **9 Auto-fix Capabilities**: tabs, GUID case, file ending, property VAR blocks, property newlines, CDATA, excessive blanks, indentation, LineIds
- **Modular Architecture**: 5-layer design (Foundation, Validation, Fix, Orchestration, MCP)
- **JSON Configuration**: validation_rules.json, fix_capabilities.json, naming_conventions.json, knowledge_base.json
- **File Type Support**: .TcPOU (FB/PRG/FUNC), .TcIO (interfaces), .TcDUT (structs/enums), .TcGVL
- **Health Score System**: 0-100 scoring for code quality
- **Batch Processing**: Glob pattern support for multi-file operations
- **Backup System**: Automatic backup creation before fixes

### Added - LLM Context Enrichment

- **ValidationIssue Enrichment**: code_snippet, explanation, correct_example fields
- **Knowledge Base**: Comprehensive knowledge_base.json with explanations, examples, common mistakes, TwinCAT concepts
- **Snippet Extraction**: Line-based, element-based, GUID-based, XML parse error context
- **Educational Resources**: 5 priority checks populate enrichment fields

### Added - Deterministic LLM Mode

- **Deterministic Fix Order**: Explicit ordering in config (tabs→file_ending→newlines→cdata→var_blocks→excessive_blanks→indentation→guid_case→lineids)
- **Profile Modes**: "full" (verbose, default) vs "llm_strict" (minimal, 45-50% smaller)
- **Safe Flags**: safe_to_import, safe_to_compile for LLM decision-making
- **Idempotency Guarantee**: Running autofix twice produces byte-identical output
- **Token Optimization**: llm_strict mode omits enrichment for 5-10x response size reduction

### Added - OOP Validation & Orchestration

- **21 OOP Validation Checks**: extends visibility, override marker/signature, interface contract, extends cycle, override super call, inheritance property contract, FB_init signature/super call, THIS pointer consistency, abstract contract, FB_exit contract, dynamic creation attribute, pointer delete pairing, composition depth, interface segregation, method visibility consistency, diamond inheritance warning, abstract instantiation, property accessor pairing, method count
- **6 Orchestration MCP Tools**: process_twincat_single, process_twincat_batch, verify_determinism_batch, get_effective_oop_policy, generate_skeleton, extract_methods_to_xml
- **4 Additional MCP Resources**: generation-contract://, generation-contract://types/{file_type}, oop-policy://defaults, oop-policy://effective/{target_path}
- **8 MCP Prompts**: Reusable workflow templates for canonical LLM validation flows
- **Policy-aware response contract** (`response_version: "2"`) with policy proof fields
- **Enforcement mode** parameter on OOP-sensitive tools (`strict` default, `compat` opt-in)
- **Intent profile** parameter on all validation/fix tools; procedural workflows skip OOP checks automatically
- **Batch auto OOP detection**: scans `.TcPOU` files for EXTENDS/IMPLEMENTS keywords
- **VAR_PROTECTED prevention**: Forbidden pattern detection and generation contract guard

### Added - Release & Distribution

- **Contract Tests**: Exact API schema enforcement for llm_strict responses
- **Determinism Regression Gate**: Fix order stability, blocker logic stability, safe flag determinism
- **Golden-file Byte Stability**: Baseline golden files + hash registry for autofix output verification
- **Multi-client Documentation**: Cursor, VS Code, Windsurf, Cline, generic stdio
- **Entry Points**: twincat-validator-mcp console script, python -m twincat_validator
- **Desktop Extension (.dxt)**: One-click install package with manifest, healthcheck, and build automation
- **Release Automation**: GitHub Actions workflow builds wheel, source dist, and .dxt on tag push
- **Test Suite**: 1000+ tests, >80% coverage, pytest + pytest-cov + pytest-asyncio

### Documentation

- README.md with 5 LLM client configurations (Cursor, VS Code, Windsurf, Cline, generic stdio)
- CONTRIBUTING.md with full development guide
- LICENSE (MIT)
- AGENT.md with AI assistant guidance
