"""Complex auto-fix operations for TwinCAT XML files.

Contains 1 complex fix extracted from server.py:
- LineIdsFix (fix_id="lineids", lines 1171-1349)
"""

import xml.etree.ElementTree as ET

from .base import BaseFix, FixRegistry
from ..file_handler import TwinCATFile


@FixRegistry.register
class LineIdsFix(BaseFix):
    """Generate missing LineIds for methods/properties.

    COMPLEX FIX - Copied exactly from server.py lines 1171-1349.
    Extracted from server.py lines 1171-1349.
    """

    fix_id = "lineids"

    def apply(self, file: TwinCATFile) -> bool:
        """Generate missing LineIds for all code sections.

        Algorithm:
        1. Parse XML to find all code sections (POU body, methods, properties)
        2. For each section, check if LineIds exist
        3. If missing, extract ST code and generate LineIds
        4. Insert generated LineIds before closing tag

        Args:
            file: TwinCATFile to modify

        Returns:
            True if LineIds were generated, False otherwise
        """
        try:
            # Parse XML from in-memory content (not disk) to stay consistent
            # with any prior fixes already applied to file.content
            root = ET.fromstring(file.content)

            # Track sections needing LineIds
            sections_to_generate = []

            # Get POU/DUT name for naming
            pou = root.find(".//POU")
            dut = root.find(".//DUT")
            itf = root.find(".//Itf")

            base_name = None
            if pou is not None:
                base_name = pou.get("Name")
            elif dut is not None:
                base_name = dut.get("Name")
            elif itf is not None:
                base_name = itf.get("Name")

            if not base_name:
                return False  # Can't generate LineIds without knowing the name

            # Check main POU body
            if pou is not None:
                impl = pou.find("./Implementation/ST")
                if impl is not None:
                    # Check if LineIds exist for main body
                    lineids_name = base_name
                    existing = root.find(f'.//LineIds[@Name="{lineids_name}"]')
                    if existing is None:
                        st_code = impl.text or ""
                        sections_to_generate.append((lineids_name, st_code))

            # Check all methods
            for method in root.findall(".//Method"):
                method_name = method.get("Name")
                if method_name:
                    impl = method.find("./Implementation/ST")
                    if impl is not None:
                        lineids_name = f"{base_name}.{method_name}"
                        existing = root.find(f'.//LineIds[@Name="{lineids_name}"]')
                        if existing is None:
                            st_code = impl.text or ""
                            sections_to_generate.append((lineids_name, st_code))

            # Check all properties (Get/Set)
            for prop in root.findall(".//Property"):
                prop_name = prop.get("Name")
                if prop_name:
                    # Check Get accessor
                    get_elem = prop.find("./Get/Implementation/ST")
                    if get_elem is not None:
                        lineids_name = f"{base_name}.{prop_name}.Get"
                        existing = root.find(f'.//LineIds[@Name="{lineids_name}"]')
                        if existing is None:
                            st_code = get_elem.text or ""
                            sections_to_generate.append((lineids_name, st_code))

                    # Check Set accessor
                    set_elem = prop.find("./Set/Implementation/ST")
                    if set_elem is not None:
                        lineids_name = f"{base_name}.{prop_name}.Set"
                        existing = root.find(f'.//LineIds[@Name="{lineids_name}"]')
                        if existing is None:
                            st_code = set_elem.text or ""
                            sections_to_generate.append((lineids_name, st_code))

            # Generate LineIds for missing sections
            if not sections_to_generate:
                return False

            # Find insertion point (before closing POU/DUT/Itf tag)
            closing_tag = None
            if pou is not None:
                closing_tag = "</POU>"
            elif dut is not None:
                closing_tag = "</DUT>"
            elif itf is not None:
                closing_tag = "</Itf>"

            if not closing_tag:
                return False

            # Generate LineIds XML for each section
            lineids_xml_parts = []
            for section_name, st_code in sections_to_generate:
                lineids_xml = self._generate_lineids_xml(section_name, st_code)
                lineids_xml_parts.append(lineids_xml)

            # Insert all LineIds before closing tag
            lineids_block = "\n".join(lineids_xml_parts)

            # Find the closing tag position
            closing_pos = file.content.rfind(closing_tag)
            if closing_pos <= 0:
                return False

            # Insert LineIds before closing tag
            new_content = (
                file.content[:closing_pos] + lineids_block + "\n" + file.content[closing_pos:]
            )

            # Safety check: verify the result is still valid XML
            try:
                ET.fromstring(new_content)
            except ET.ParseError:
                # LineIds generation produced invalid XML, revert
                return False

            file.content = new_content
            return True

        except Exception:
            # If generation fails, don't crash
            return False

    def _generate_lineids_xml(self, section_name: str, st_code: str) -> str:
        """Generate LineIds XML for a code section.

        Algorithm:
        - Empty code: <LineId Id="2" Count="0" />
        - N lines: <LineId Id="3" Count="N-1" />
                  <LineId Id="2" Count="0" />

        Args:
            section_name: Full section name (e.g., "FB_Example.M_Method")
            st_code: Structured Text code content

        Returns:
            LineIds XML string
        """
        # Split into lines (preserve all lines including empty)
        lines = st_code.split("\n") if st_code else []

        # Check if code is truly empty (all whitespace)
        has_content = any(line.strip() for line in lines)

        if not has_content:
            # Empty method - just end marker
            return f'    <LineIds Name="{section_name}">\n      <LineId Id="2" Count="0" />\n    </LineIds>'

        # Calculate line count and count value
        num_lines = len(lines)
        start_id = 3
        count = num_lines - 1

        # Generate LineIds XML
        return f"""    <LineIds Name="{section_name}">
      <LineId Id="{start_id}" Count="{count}" />
      <LineId Id="2" Count="0" />
    </LineIds>"""
