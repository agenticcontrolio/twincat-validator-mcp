# TwinCAT Validator — Desktop Extension

Validate and auto-fix TwinCAT/Beckhoff PLC XML files directly from Claude Desktop or any MCP-compatible desktop client.

## What It Provides

- **16 MCP Tools** — validation, auto-fix, skeleton generation, OOP checks, and orchestration pipelines
- **34 Validation Checks** — structure, GUIDs, style, naming, and 21 IEC 61131-3 OOP checks
- **9 Auto-fix Operations** — deterministic, idempotent, dependency-ordered
- **Supported files**: `.TcPOU`, `.TcIO`, `.TcDUT`, `.TcGVL`

## Requirements

- **Python 3.11+** installed on your system
- **pip** for package installation

## Installation

### 1. Install the Python package

```bash
pip install twincat-validator-mcp
```

### 2. Install the extension in Claude Desktop

1. Download the `.dxt` file from the [latest release](https://github.com/jaimecalvente/twincat-validator-mcp/releases)
2. Open **Claude Desktop**
3. Go to **Settings** → **Extensions**
4. Click **Install Extension** and select the downloaded `.dxt` file
5. Restart Claude Desktop

### 3. Verify

Ask Claude:
```
What TwinCAT Validator tools are available?
```

You should see all 16 tools listed.

## Usage Examples

```
Validate this TwinCAT file: C:/project/FB_Motor.TcPOU
```

```
Auto-fix all issues in C:/project/FB_Motor.TcPOU and check if it's safe to import
```

```
Validate all TwinCAT files in C:/project/PLC/ and give me a summary
```

```
Generate a canonical Function Block skeleton for a new FB_Controller
```

## Troubleshooting

### Extension shows "Not Running"

1. Verify Python 3.11+ is installed: `python --version`
2. Verify the package is installed: `pip show twincat-validator-mcp`
3. Test the server manually: `twincat-validator-mcp` (Ctrl+C to stop)
4. Check Claude Desktop logs for startup errors mentioning "twincat-validator"

### Command not found

**Windows** — ensure Python's Scripts directory is in `PATH`:
```bash
python -m pip show twincat-validator-mcp
# Check "Location" field, add its Scripts/ subdirectory to PATH
```

**macOS/Linux**:
```bash
pip install --user twincat-validator-mcp
# or
pipx install twincat-validator-mcp
```

### Manual configuration fallback

If the extension doesn't load, add this to your client's MCP config file:

```json
{
  "mcpServers": {
    "twincat-validator": {
      "command": "twincat-validator-mcp",
      "args": []
    }
  }
}
```

## Links

- [Documentation](https://github.com/jaimecalvente/twincat-validator-mcp#readme)
- [Issues](https://github.com/jaimecalvente/twincat-validator-mcp/issues)
- [PyPI](https://pypi.org/project/twincat-validator-mcp/)
- [License: MIT](https://github.com/jaimecalvente/twincat-validator-mcp/blob/main/LICENSE)
