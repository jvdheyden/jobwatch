# Roadmap

_Last updated: 2026-04-23_

## Conventions

- Statuses: `new`, `in progress`, `complete`, `parked`
- `in progress` means there is active work and a concrete next step
- Non-trivial active items should link to a file in `docs/plans/`
- `parked` items must include a reason and revisit condition
- Keep entries short; move implementation detail into linked plan docs
- Keep only recent completed items here; archive older ones elsewhere

Template:
RM-### — Title
- Status:
- Priority:
- Links:
- Next step:
- Notes:


## New

### RM-009 — Move secrets out of project directory and import at runtime
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: 
- Next steps: create implementation plan
- Notes: At the moment secrets (currently only SMPT password)  are in 
    unencrypted untracked file .env.local. 
    Only instructions prevent agent from reading .env.local. It would be safer
    to move secrets into extra file out of project directory and import them
    using deterministic scripts at runtime.
    Even better would be using keyrings, but that would create complications
    for scheduled non-interactive runs. Such a solution should be the long-term
    goal but for now we keep it simple.

### RM-010 — Add support for main email providers (gmail, fastmail, proton, hotmail)
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: 
- Next step: create implementation plan
- Notes: Replace one global SMTP config with a gitignored local file containing
    named accounts, for example 
    ```
    default_account = "personal"

    [accounts.personal]
    provider = "gmail"
    email = "you@gmail.com"
    transport = "smtp"
    auth = "oauth2"
    from = "you@gmail.com"
    to = ["you@gmail.com"]
    
    [accounts.fastmail]
    provider = "fastmail"
    email = "jobs@example.com"
    transport = "smtp"
    auth = "app_password"
    from = "jobs@example.com"
    to = ["you@example.com"]
    ```
    keep secrets out of that file.
    Add a small registry with defaults, not logic-heavy per-provider classes.
    ```
    PROVIDERS = {
        "gmail": {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "tls": "starttls",
            "supports": ["oauth2", "app_password"],
        },
        "outlook": {
            "smtp_host": "smtp-mail.outlook.com",
            "smtp_port": 587,
            "tls": "starttls",
            "supports": ["oauth2"],
        },
        "icloud": {
            "smtp_host": "smtp.mail.me.com",
            "smtp_port": 587,
            "tls": "starttls",
            "supports": ["app_password"],
        },
        "fastmail": {
            "smtp_host": "smtp.fastmail.com",
            "smtp_port": 465,
            "tls": "ssl",
            "supports": ["app_password"],
        },
    }
    ```
    This lets you support “custom SMTP” too.
    Separate auth from transport.
    Implement these auth backends:

    - AppPasswordAuth
    - OAuth2Auth
    - optionally PlainPasswordAuth for custom SMTP only

    That lets the SMTP sender stay mostly unchanged.
    No need for provider APIs.

### RM-011 — Nicer Emails
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: 
- Next step: create implementation plan
- Notes: this is a minor change. currently emails start with "Core Crypto job 
    digest
    Date: 2026-04-23"
    This is unnecessary because the date is obvious from the email and "core
    crypto digest" is obvious from the subject. best to start with the executive
    summary. the attachment is unnecessary I think.

### RM-012 — Telegram delivery for digests
- Status: new
- Priority: H
- Owner: Jonas
- Last updated: 2026-04-23
- Links: 
- Next step: create implementation plan
- Notes: keep setup lightweight for end users

## In progress

## Parked

## Completed

