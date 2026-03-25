# Security Policy

## Supported Branches

Security fixes are applied on a best-effort basis to:

- `main`
- `develop`

Older commits, personal forks, and experimental branches may not receive security updates.

## Reporting a Vulnerability

If you discover a security issue, please do not open a public issue first.

Report it privately by email:

- `th0mg0y@proton.me`

Please include:

- a short description of the issue
- steps to reproduce it
- the affected files, endpoints, or features
- the potential impact
- logs, screenshots, or proof of concept if relevant

## What To Report Privately

Please report these privately:

- exposed secrets or tokens
- authentication or authorization bypasses
- remote code execution
- path traversal or arbitrary file access
- command injection
- dependency vulnerabilities with real impact on this repo

## Disclosure Expectations

I will review reports on a best-effort basis.

Please allow time for confirmation and a fix before public disclosure.

If a report is valid, I will try to:

- confirm the issue
- assess impact
- prepare a fix or mitigation
- publish the fix in the repository

## Secret Hygiene

If you accidentally expose a secret:

1. revoke it immediately
2. rotate it
3. remove it from the repository and any deployment environment
4. report the exposure if it may affect users
