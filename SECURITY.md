# Security Policy

## Supported Versions

Currently supported versions of TwinCAT Validator MCP Server:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take the security of TwinCAT Validator MCP Server seriously. If you discover a security vulnerability, please follow these steps:

### How to Report

1. **DO NOT** open a public issue on GitHub
2. Email the maintainer at: jaimecalvente@users.noreply.github.com
3. Include the following information:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Response Time**: We aim to respond within 48 hours
- **Updates**: We will keep you informed of the progress
- **Disclosure**: We follow responsible disclosure practices
- **Credit**: Security researchers will be credited (unless they prefer to remain anonymous)

### Security Best Practices for Users

When using this MCP server:

1. **File Validation**: Always validate files from untrusted sources in isolated environments
2. **Backup Creation**: Enable backup creation (`create_backup=True`) when using auto-fix
3. **Access Control**: Restrict server access to trusted users only
4. **Regular Updates**: Keep the package updated to the latest version
5. **Configuration**: Review custom validation configurations before deploying

### Known Security Considerations

- **XML Parsing**: The server parses XML files - ensure files come from trusted sources
- **File System Access**: The server reads/writes files - proper file permissions should be set
- **Auto-fix Operations**: Auto-fix modifies files - always review changes or use backups

### Scope

The following are **in scope** for security reports:

- XML parsing vulnerabilities (XXE, billion laughs, etc.)
- File system access issues
- Code injection vulnerabilities
- Denial of service vulnerabilities

The following are **out of scope**:

- Issues in third-party dependencies (report to respective maintainers)
- Social engineering attacks
- Issues requiring physical access to the system
- Theoretical vulnerabilities without proof of concept

Thank you for helping keep TwinCAT Validator MCP Server secure!
