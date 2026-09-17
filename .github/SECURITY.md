# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities through [GitHub Security Advisories](https://github.com/bot-netizen/sqldesk/security/advisories/new) rather than a public issue. We will acknowledge receipt and keep you updated on progress.

Do not report SQLDesk vulnerabilities to the SQLDesk project. SQLDesk is an independent fork and its maintainers are not responsible for this code.

## Out of Scope
 
The following are known design characteristics of SQLDesk rather than vulnerabilities, and reports about them will generally be declined:
 
- **Code execution via the Python query runner.** The Python data source is intentionally not a security sandbox and is disabled by default. Anyone granted access to a Python data source should be trusted to run code in the SQLDesk worker environment. Sandbox escapes in the Python query runner (including RestrictedPython bypasses) are out of scope.
- **Requests to internal hosts from an admin-configured data source (SSRF).** Data sources can only be created or modified by admins (endpoints are gated by `@require_admin`), and connecting to arbitrary hosts — including internal ones — is a core function of the product. Deciding whether a data source may reach an internal address is left to the admin who configures it.
 
If you're unsure whether something falls in scope, email us anyway — we'd rather hear about it.
 
