# Security Policy

Marmot is a local system maintenance tool for Debian Linux. It includes high-risk operations such as cache cleanup, package purging, service optimization, and directory analysis. We treat safety boundaries, deletion logic, privilege escalation boundaries, and release integrity as security-sensitive areas.

## Reporting a Vulnerability

Please report suspected security issues privately.

- Email: the.nv2418988@sis.hust.edu.vn
- Subject line: Marmot security report

Do not open a public GitHub issue for an unpatched vulnerability.

If GitHub Security Advisories private reporting is enabled for the repository, you may use that channel instead of email.

Include as much of the following as possible:

- Marmot version and install method
- Debian / OS version
- Exact command or workflow involved
- Reproduction steps or proof of concept
- Whether the issue involves deletion boundaries, symlinks, pkexec/sudo privilege escalation, path validation, or release/install integrity

## Response Expectations

- We aim to acknowledge new reports within 7 calendar days.
- We aim to provide a status update within 30 days if a fix or mitigation is not yet available.
- We will coordinate disclosure after a fix, mitigation, or clear user guidance is ready.

Response times are best-effort for a maintainer-led open source project, but security reports are prioritized over normal bug reports.

## Supported Versions

Security fixes are only guaranteed for:

- The latest published release
- The current main branch
