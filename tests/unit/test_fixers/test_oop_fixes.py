"""Unit tests for OOP-specific fixers (Phase 5A)."""

from twincat_validator.file_handler import TwinCATFile
from twincat_validator.fixers.oop_fixes import OverrideAttributeFix


class TestOverrideAttributeFix:
    """Tests for OverrideAttributeFix."""

    def test_replaces_method_override_keyword_with_attribute(self, tmp_path):
        """Test that METHOD OVERRIDE is replaced with {attribute 'override'}."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            "    <Declaration><![CDATA[FUNCTION_BLOCK FB_Derived EXTENDS FB_Base\n"
            "END_VAR\n"
            "]]></Declaration>\n"
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD OVERRIDE M_Start : BOOL\n"
            "VAR_INPUT\nEND_VAR\n"
            "]]></Declaration>\n"
            "      <Implementation><ST><![CDATA[M_Start := TRUE;]]></ST></Implementation>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is True
        assert "METHOD OVERRIDE" not in file.content
        assert "{attribute 'override'}" in file.content
        assert "METHOD M_Start : BOOL" in file.content

    def test_preserves_indentation(self, tmp_path):
        """Test that indentation is preserved after replacement."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Stop" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[\n"
            "        METHOD OVERRIDE M_Stop : BOOL\n"
            "        VAR_INPUT\n"
            "        END_VAR\n"
            "      ]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is True
        # Check that attribute and METHOD are both indented at the same level
        assert "        {attribute 'override'}\n        METHOD M_Stop : BOOL" in file.content

    def test_handles_multiple_override_methods(self, tmp_path):
        """Test that all OVERRIDE methods in a file are replaced."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD OVERRIDE M_Start : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="M_Stop" Id="{a3333333-3333-3333-3333-333333333333}">\n'
            "      <Declaration><![CDATA[METHOD OVERRIDE M_Stop : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            '    <Method Name="Execute" Id="{a4444444-4444-4444-4444-444444444444}">\n'
            "      <Declaration><![CDATA[METHOD OVERRIDE Execute\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is True
        assert file.content.count("{attribute 'override'}") == 3
        assert "METHOD OVERRIDE" not in file.content

    def test_case_insensitive_matching(self, tmp_path):
        """Test that METHOD override (lowercase) is also replaced."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[method override M_Start : bool\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is True
        assert "{attribute 'override'}" in file.content
        # Note: Fixer normalizes to uppercase METHOD (TwinCAT canonical form)
        assert "METHOD M_Start : bool" in file.content

    def test_no_change_when_no_override_keyword(self, tmp_path):
        """Test that files without METHOD OVERRIDE are not changed."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Base" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD M_Start : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Base.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        original_content = file.content
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is False
        assert file.content == original_content

    def test_no_change_when_already_using_attribute_syntax(self, tmp_path):
        """Test that files already using attribute syntax are not changed."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[{attribute 'override'}\n"
            "METHOD M_Start : BOOL\n"
            "]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        original_content = file.content
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is False
        assert file.content == original_content

    def test_idempotent(self, tmp_path):
        """Test that applying the fix twice produces the same result."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD OVERRIDE M_Start : BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()

        # First application
        changed1 = fix.apply(file)
        content_after_first = file.content

        # Second application (on same file object, already modified in memory)
        changed2 = fix.apply(file)
        content_after_second = file.content

        assert changed1 is True
        assert changed2 is False  # No changes on second pass
        assert content_after_first == content_after_second

    def test_handles_extra_whitespace(self, tmp_path):
        """Test that extra whitespace in METHOD OVERRIDE is handled."""
        content = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.12">\n'
            '  <POU Name="FB_Derived" Id="{a1111111-1111-1111-1111-111111111111}">\n'
            '    <Method Name="M_Start" Id="{a2222222-2222-2222-2222-222222222222}">\n'
            "      <Declaration><![CDATA[METHOD   OVERRIDE   M_Start  :  BOOL\n]]></Declaration>\n"
            "    </Method>\n"
            "  </POU>\n"
            "</TcPlcObject>\n"
        )
        file_path = tmp_path / "FB_Derived.TcPOU"
        file_path.write_text(content, encoding="utf-8")

        file = TwinCATFile(file_path)
        fix = OverrideAttributeFix()
        changed = fix.apply(file)

        assert changed is True
        assert "{attribute 'override'}" in file.content
        # Note: Fixer normalizes whitespace between METHOD and method name
        assert "METHOD M_Start  :  BOOL" in file.content  # Preserves spacing in signature
