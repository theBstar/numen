# Security Policy

## Reporting a vulnerability

**Please do not open a public issue.**

Report privately through GitHub's [private vulnerability
reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
on this repository, under the Security tab.

Useful to include: what an attacker can do, the steps to reproduce it, and the
version or commit you tested. A proof of concept helps but is not required.

You can expect an acknowledgement within a few days and an assessment within
about a week. If a fix is warranted, we will agree a disclosure timeline with
you and credit you in the release notes unless you would rather we did not.

## Scope

Numen holds a company's work data - tickets, code review, conversations - so
the boundaries that matter most are:

- **Tenant isolation.** Anything letting one organisation read or write
  another's data. Queries are scoped by `org_id` and enforced by Postgres
  row-level security.
- **Authentication and authorisation.** Session handling, API key validation,
  role checks, and the surface-based permissions described below.
- **Webhook verification.** Signature checks for Slack, GitHub, Linear and Jira.
- **Secret handling.** OAuth tokens are encrypted at rest; anything that leaks
  them, or leaks them into logs or model output, is in scope.
- **Prompt and output safety.** The agent must not disclose its instructions,
  configuration, or credentials.

Also worth knowing, since it is easy to test and easy to get wrong: an answer
delivered somewhere other people can read it, such as a Slack channel, is
restricted - no private document retrieval, and no writes. Ways around that are
in scope.

## Not in scope

- Findings that need an already-compromised host or database.
- Denial of service through sheer volume against your own instance.
- Missing hardening headers with no demonstrated impact.
- Vulnerabilities in a dependency with no exploitable path through Numen.
  Report those upstream.

## Self-hosting notes

Numen is designed to be run by the organisation whose data it holds. A few
things are your responsibility rather than the project's:

- Set `SECRET_KEY`, `JWT_SECRET_KEY` and `ENCRYPTION_KEY` explicitly in
  production. Startup refuses to run without them. Never rotate
  `ENCRYPTION_KEY` after first use; existing OAuth tokens become unreadable.
- Set `SIGNUP_MODE=domain` or `invite`. The default, `open`, admits anyone
  whose email domain matches an existing organisation.
- Keep `ALLOW_HEADER_AUTH` off outside local development. It is refused in
  production, but do not rely on that alone.
- Restrict who can reach the instance. Numen has no opinion about your network.
