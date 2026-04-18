"""Shared defaults for discovery providers.

Provider-specific protocol constants should live in the provider module. This
module only holds defaults that are intentionally reused across providers.
"""

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_BROWSER_TIMEOUT_MS = 60_000
MAX_BROWSER_PAGES = 10

TECHNICAL_TITLE_HINTS = (
    "engineer",
    "engineering",
    "developer",
    "research",
    "researcher",
    "scientist",
    "software",
    "hardware",
    "architect",
    "specialist",
    "crypt",
    "protocol",
    "verification",
)

NON_TECHNICAL_TITLE_HINTS = (
    "manager",
    "account executive",
    "recruit",
    "sales",
    "marketing",
    "finance",
    "people",
    "operations",
    "counsel",
    "legal",
    "workplace",
    "talent",
    "procurement",
    "facilities",
    "campus",
    "policy",
    "grc",
    "executive assistant",
)

SPECIALIZED_SIGNAL_TERMS = {
    "cryptography",
    "cryptographer",
    "applied cryptography",
    "privacy engineering",
    "privacy-preserving",
    "privacy-enhancing technologies",
    "pets",
    "security research",
    "protocol security",
    "digital identity",
    "key management",
    "post-quantum",
    "post-quantum cryptography",
    "pqc",
    "mpc",
    "multi-party computation",
    "zero-knowledge",
    "zk",
    "fhe",
    "homomorphic encryption",
    "smart card",
    "embedded security",
    "secure hardware",
    "hsm",
}
