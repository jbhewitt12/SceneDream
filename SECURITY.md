# Security Policy

## Supported Versions

Security fixes are applied to the latest release and the `main` branch.

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| `main` | Yes |
| Older releases | No |

## Reporting a Vulnerability

Do not open a public issue for suspected vulnerabilities.

Use one of these private reporting paths:

1. Preferred: GitHub private vulnerability reporting in this repository's Security tab (`Report a vulnerability`).
2. Fallback: contact the maintainer directly via GitHub at [@jbhewitt12](https://github.com/jbhewitt12) and request a private disclosure channel.

Please include:

- affected component(s) and impact
- reproduction steps or proof of concept
- suggested mitigation, if available

## Disclosure Process

- We will acknowledge receipt as soon as possible.
- We will investigate, triage severity, and work on a fix.
- After a fix is available, we will coordinate responsible disclosure details.

## Scope Notes

This project orchestrates local pipelines and integrates external AI services. Reports are especially useful for:

- secret handling and credential leaks
- unsafe file/path handling
- unauthorized data exposure
- dependency or supply-chain risks in shipped code
