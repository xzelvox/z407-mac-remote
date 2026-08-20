# Security Policy

## Reporting a Vulnerability

This is an open-source project maintained on a best-effort basis. I take security issues seriously and appreciate responsible disclosure.

If you discover a security vulnerability, please **do not open a public issue**. Instead, report it privately so it can be resolved prior to public disclosure.

### How to Report

Please submit security reports via a **Private Vulnerability Report** on GitHub:

<https://github.com/xzelvox/z407-mac-remote/security/advisories/new>

If you are unable to use GitHub Security Advisories, please contact the maintainer privately (e.g., via the email listed on their GitHub profile).

### What to Include

To help triage and resolve the issue quickly, please provide:

- A clear description of the vulnerability and its potential impact
- Step-by-step instructions to reproduce (or a minimal PoC)
- Affected version(s) or commit hash
- Any proposed fix or mitigation (optional)

### Response & Triage

I will do my best to acknowledge reports within a few days and keep you updated on fixes and releases. Because this is a personal side project, response and patch timelines are provided on a best-effort basis.

## Scope

### In Scope

- Source code in this repository (Python application, menu bar integration, helper scripts)
- Packaging and installation scripts (`setup.py`, `install.sh`, etc.)

### Out of Scope

- Upstream dependencies (e.g., `bleak`, `pyobjc`) — please report vulnerabilities directly to the respective upstream maintainers.
- Hardware/firmware-level vulnerabilities of the Logitech Z407 device itself.