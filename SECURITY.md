<!-- Template: replace REPLACE_ME@example.com and the repository slug in the advisory link. -->

# Security Policy

## Supported versions

| Version                  | Supported                       |
| ------------------------ | ------------------------------- |
| Latest release (`main`)  | Yes, security fixes             |
| `next` (release staging) | Best effort                     |
| `dev` (integration)      | Best effort                     |
| Older releases           | No, upgrade to the latest       |

Fixes land through the normal flow: a `fix/<slug>` PR into `dev`, or into the
in-flight `release/vX.Y.Z` branch for hotfixes. See
[`.github/BRANCH-AND-RELEASE-POLICY.md`](.github/BRANCH-AND-RELEASE-POLICY.md).

## Reporting a vulnerability

Do not open a public issue, PR, or discussion for a suspected vulnerability.

1. Preferred: use GitHub private vulnerability reporting. Go to the
   **Security** tab, then **Report a vulnerability**
   ([direct link](https://github.com/exegia/corpora-template/security/advisories/new)).
2. Fallback: email `REPLACE_ME@example.com`.

### What to include

- Affected component, version, or commit
- Description of the issue and its impact
- Steps to reproduce, or a proof of concept
- Any suggested fix or mitigation
- Whether the issue is already public or has a disclosure deadline

Do not include live credentials or personal data in your report.

## Response targets

| Stage                  | Target             |
| ---------------------- | ------------------ |
| Acknowledgement        | 3 business days    |
| Triage and severity    | 7 days             |
| Fix or mitigation plan | Shared after triage |

Timelines for fixes depend on severity and complexity. We will keep you updated
until the report is resolved.

## Disclosure policy

We follow coordinated disclosure. We ask reporters to keep details private until
a fix is released. After the fix ships, we publish a GitHub Security Advisory
(with a CVE where applicable) and credit the reporter unless they prefer to stay
anonymous.

## Secrets

If you committed a credential (API key, token, password, private key):

1. Rotate or revoke it first. Treat it as compromised, even if the commit was
   never pushed or the branch was deleted.
2. Then remove it from the working tree and, if needed, from history.
3. Never bypass hooks with `--no-verify`. If a hook fires, fix the cause.

Real values belong in `.env` (gitignored). Commit `.env.example` with
placeholders only.

Automated safeguards in this template:

- `gitleaks` pre-commit hook (installed by `make setup`)
- `Secret Scan` CI workflow (`make secrets-scan` runs it locally)
- GitHub secret scanning with push protection
- Dependabot alerts and security updates
- CodeQL code scanning
