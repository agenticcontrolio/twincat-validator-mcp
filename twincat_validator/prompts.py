"""MCP Prompt templates for TwinCAT Validator.

Prompts encode canonical validation/fix workflows as reusable templates.
The LLM client calls listPrompts, picks a template, fills parameters, and
receives a ready-made instruction it can follow — no need to rediscover the
correct tool call sequence on every conversation.

Registration: call register_prompts(mcp) from server.py after creating the
FastMCP instance.

Pattern mirrors heilingbrunner/tiaportal-mcp's McpPrompts.cs design, adapted
for Python/FastMCP.
"""

from __future__ import annotations


def register_prompts(mcp) -> None:  # noqa: ANN001
    """Register all MCP prompt templates with the FastMCP server instance."""

    # -------------------------------------------------------------------------
    # P1 — validate_and_fix
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="validate_and_fix",
        description=(
            "Canonical one-shot workflow: validate a TwinCAT file, apply all "
            "auto-fixable issues, then re-validate to report remaining blockers. "
            "Use this for the standard LLM-generated-file → server-fixes → done flow."
        ),
    )
    def validate_and_fix(
        file_path: str,
        validation_level: str = "all",
    ) -> str:
        """Validate then autofix a TwinCAT file and report remaining blockers."""
        return (
            f"Please process the TwinCAT file at: {file_path}\n\n"
            "Workflow:\n"
            f"1. Call validate_file(file_path={file_path!r}, validation_level={validation_level!r}, "
            "profile='llm_strict') to see current issues.\n"
            f"2. Call autofix_file(file_path={file_path!r}, profile='llm_strict', "
            "format_profile='twincat_canonical', strict_contract=True) to apply all auto-fixable issues.\n"
            "3. If content_changed=True, call validate_file again to confirm remaining issues.\n"
            "4. Report: list any remaining blockers (safe_to_import=False or safe_to_compile=False), "
            "and confirm whether the file is ready for import.\n\n"
            "Stop after step 4. Do not attempt manual edits — only use the server tools."
        )

    # -------------------------------------------------------------------------
    # P2 — prepare_for_import
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="prepare_for_import",
        description=(
            "Check whether a TwinCAT file is safe to import into TwinCAT XAE. "
            "If not, list each blocker with a clear explanation. "
            "Use this before adding a generated file to a TwinCAT project."
        ),
    )
    def prepare_for_import(
        file_path: str,
    ) -> str:
        """Check import safety and explain any blockers."""
        return (
            f"Check whether this TwinCAT file is safe to import: {file_path}\n\n"
            "Workflow:\n"
            f"1. Call validate_for_import(file_path={file_path!r}).\n"
            "2. If safe_to_import=True: confirm the file is ready — no further action needed.\n"
            "3. If safe_to_import=False: for each entry in critical_issues, explain:\n"
            "   - What the issue is (in plain language)\n"
            "   - Why TwinCAT will reject the file\n"
            "   - What the developer must change to fix it\n"
            "4. Do not attempt fixes — only diagnose and explain."
        )

    # -------------------------------------------------------------------------
    # P3 — check_oop_compliance
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="check_oop_compliance",
        description=(
            "Run a full OOP compliance review on a TwinCAT .TcPOU file. "
            "Explains each OOP warning using knowledge-base excerpts and "
            "provides actionable fix suggestions. Use this for code review of "
            "Function Blocks that use EXTENDS, IMPLEMENTS, or ABSTRACT."
        ),
    )
    def check_oop_compliance(
        file_path: str,
        include_style: bool = False,
    ) -> str:
        """Full OOP validation review with knowledge-base explanations."""
        level = "all" if include_style else "all"
        oop_checks = [
            "extends_visibility",
            "override_marker",
            "override_signature",
            "interface_contract",
            "extends_cycle",
            "override_super_call",
            "inheritance_property_contract",
            "fb_init_signature",
            "fb_init_super_call",
            "this_pointer_consistency",
            "abstract_contract",
            "fb_exit_contract",
            "dynamic_creation_attribute",
            "pointer_delete_pairing",
            "composition_depth",
            "interface_segregation",
            "method_visibility_consistency",
            "diamond_inheritance_warning",
            "abstract_instantiation",
            "property_accessor_pairing",
            "method_count",
        ]
        checks_str = ", ".join(repr(c) for c in oop_checks)
        return (
            f"Perform an OOP compliance review for: {file_path}\n\n"
            "Workflow:\n"
            f"1. Call validate_file(file_path={file_path!r}, validation_level={level!r}, "
            "profile='full') to get the full validation result including explanations.\n"
            f"2. Call check_specific(file_path={file_path!r}, "
            f"check_names=[{checks_str}]) for focused OOP results.\n"
            "3. For each issue found:\n"
            "   a. State the check name and severity (error/warning)\n"
            "   b. Quote the relevant code snippet if available\n"
            "   c. Explain why it violates TwinCAT OOP contracts\n"
            "   d. Show the correct pattern with a code example\n"
            "4. Summarize: how many OOP errors (blocking) vs warnings (advisory)?\n"
            "5. Prioritize errors first, then warnings grouped by SOLID principle.\n\n"
            "Use the knowledge-base entries from the validation result for explanations."
        )

    # -------------------------------------------------------------------------
    # P4 — batch_normalize
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="batch_normalize",
        description=(
            "Canonicalize all TwinCAT PLC files in a directory: apply tab→space, "
            "GUID casing, LineIds, and formatting fixes. Reports which files needed "
            "changes and which were already canonical. "
            "Use this as a pre-commit normalization step."
        ),
    )
    def batch_normalize(
        directory_path: str,
        file_patterns: str = "**/*.TcPOU,**/*.TcIO,**/*.TcDUT,**/*.TcGVL",
        create_backup: bool = False,
    ) -> str:
        """Normalize all TwinCAT files in a directory."""
        patterns = [p.strip() for p in file_patterns.split(",")]
        patterns_repr = repr(patterns)
        return (
            f"Normalize all TwinCAT files in: {directory_path}\n\n"
            "Workflow:\n"
            f"1. Call autofix_batch(file_patterns={patterns_repr}, "
            f"directory_path={directory_path!r}, "
            f"create_backup={create_backup!r}, "
            "profile='llm_strict', format_profile='twincat_canonical') "
            "to apply all formatting fixes.\n"
            "2. Report:\n"
            "   - How many files were processed\n"
            "   - Which files had content_changed=True (needed normalization)\n"
            "   - Which files were already canonical (content_changed=False)\n"
            "   - Any files that failed (with error reason)\n"
            "3. If any file has safe_to_import=False after fixing, list its blockers.\n\n"
            "Do not open or edit files manually — only use autofix_batch."
        )

    # -------------------------------------------------------------------------
    # P5 — check_naming_only
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="check_naming_only",
        description=(
            "Run only the naming_conventions check on a TwinCAT file and list "
            "all violations with the expected naming pattern. "
            "Use this for quick naming compliance reviews."
        ),
    )
    def check_naming_only(
        file_path: str,
    ) -> str:
        """Naming conventions compliance check."""
        return (
            f"Check naming conventions for: {file_path}\n\n"
            "Workflow:\n"
            f"1. Call check_specific(file_path={file_path!r}, "
            "check_names=['naming_conventions']).\n"
            "2. For each violation:\n"
            "   - State the element name that violates the convention\n"
            "   - State the required prefix/pattern (e.g., FB_ for function blocks, "
            "I_ for interfaces, E_ for enums)\n"
            "   - Suggest the corrected name\n"
            "3. If no violations: confirm the file follows TwinCAT naming conventions.\n\n"
            "Naming convention reference:\n"
            "- Function Blocks: FB_<Name>\n"
            "- Interfaces: I_<Name>\n"
            "- Programs: PRG_<Name>\n"
            "- Functions: F_<Name> or FUNC_<Name>\n"
            "- Enums: E_<Name>\n"
            "- Structs: ST_<Name>\n"
            "- GVLs: GVL_<Name>"
        )

    # -------------------------------------------------------------------------
    # P6 — fix_then_verify
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="fix_then_verify",
        description=(
            "Apply canonical formatting to a TwinCAT file, then immediately "
            "validate to confirm the result is clean. Returns a pass/fail verdict "
            "with any remaining issues. Use this as the final step before "
            "committing a generated file."
        ),
    )
    def fix_then_verify(
        file_path: str,
        strict_contract: bool = True,
    ) -> str:
        """Apply autofix with canonical profile, then validate for confirmation."""
        return (
            f"Fix and verify the TwinCAT file at: {file_path}\n\n"
            "Workflow:\n"
            f"1. Call autofix_file(file_path={file_path!r}, "
            "profile='llm_strict', "
            "format_profile='twincat_canonical', "
            f"strict_contract={strict_contract!r}, "
            "create_backup=False).\n"
            "2. Call validate_file(file_path={file_path!r}, "
            "validation_level='all', profile='llm_strict').\n"
            "3. Report final verdict:\n"
            "   - PASS: safe_to_import=True AND safe_to_compile=True → file is ready\n"
            "   - FAIL: list blockers with check name, line number, and message\n"
            "4. Do not loop — report the verdict after exactly two tool calls."
        )

    # -------------------------------------------------------------------------
    # P7 — generate_and_validate
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="generate_and_validate",
        description=(
            "Generate a canonical TwinCAT skeleton file of the requested type, "
            "save it, and immediately validate it. Use this as a starting point "
            "when creating a new Function Block, Interface, DUT, or GVL."
        ),
    )
    def generate_and_validate(
        file_type: str,
        pou_subtype: str = "function_block",
        output_path: str = "",
    ) -> str:
        """Generate a skeleton TwinCAT file and validate it."""
        save_note = (
            f"Save the skeleton XML content to: {output_path}\n"
            f"   Then call validate_file(file_path={output_path!r}, "
            "profile='llm_strict') to confirm it is valid.\n"
            if output_path
            else (
                "Write the skeleton XML to a file path of your choice "
                "(use the POU name as the filename with the appropriate extension).\n"
                "   Then call validate_file on the saved file to confirm it is valid.\n"
            )
        )
        return (
            f"Generate a new TwinCAT {file_type} skeleton.\n\n"
            "Workflow:\n"
            f"1. Call generate_skeleton(file_type={file_type!r}, "
            f"subtype={pou_subtype!r}) to get the canonical XML scaffold.\n"
            f"2. {save_note}"
            "3. Report: is the generated file valid? List any issues found.\n\n"
            "Supported file_type values: 'TcPOU', 'TcIO', 'TcDUT', 'TcGVL'\n"
            "Supported subtype values (for TcPOU): "
            "'function_block', 'program', 'function'"
        )

    # -------------------------------------------------------------------------
    # P8 — explain_check
    # -------------------------------------------------------------------------
    @mcp.prompt(
        name="explain_check",
        description=(
            "Fetch the knowledge-base entry for a specific validation check and "
            "format it as a developer learning resource. Explains what the check "
            "detects, why it matters, shows correct and incorrect examples, and "
            "gives the fix suggestion. Use this when a developer asks 'what does "
            "this check mean?'"
        ),
    )
    def explain_check(
        check_id: str,
    ) -> str:
        """Explain a validation check using the server knowledge base."""
        return (
            f"Explain the TwinCAT validation check: '{check_id}'\n\n"
            "Workflow:\n"
            f"1. Call the MCP resource: knowledge-base://checks/{check_id}\n"
            "   (Use the read_resource MCP call with that URI)\n"
            "2. Format the response as a developer reference:\n"
            "   ## What this check detects\n"
            "   <explanation from knowledge base>\n\n"
            "   ## Why it matters\n"
            "   <why_it_matters from knowledge base>\n\n"
            "   ## Correct pattern\n"
            "   <correct_examples[0].code as a code block>\n\n"
            "   ## Common mistakes\n"
            "   <list each common_mistakes entry with mistake + reason>\n\n"
            "   ## How to fix\n"
            "   <fix_suggestion from knowledge base>\n\n"
            "3. If the check_id is not found, call get_validation_summary on any "
            "TcPOU file to see the list of registered check IDs, then suggest "
            "the closest match."
        )
