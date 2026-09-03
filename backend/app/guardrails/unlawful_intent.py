"""Unlawful-intent detection.

A request can be perfectly on topic, free of injection markers and still be
something JourneyMesh must refuse - "plan a Dubai trip by hacking the airport
server" is a travel request wrapped around a crime.

Prompt injection is a different problem: that guard defends the system from
the request, this one refuses the task itself. Keeping them apart matters,
because they produce different messages and different audit events, and a
traveller who typed something careless deserves to be told which of the two
happened.

Each rule names the subject it detected so the refusal can say what it
objected to rather than emitting a generic wall.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# (rule_id, subject shown to the traveller, pattern)
_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "unauthorised_access",
        "hacking",
        re.compile(
            r"\b(hack|hacking|hacked|crack|cracking|breach|breaching|exploit|exploiting|"
            r"ddos|brute[\s-]?force|phish|phishing)\b[^.\n]{0,40}\b"
            r"(server|servers|system|systems|network|database|website|site|account|"
            r"accounts|firewall|wifi|wi-fi|security|airport|airline|portal|booking"
            r"\s+system|api)\b"
            r"|\b(server|system|network|database|account|firewall|airport|airline)\b"
            r"[^.\n]{0,25}\b(hack|hacking|breach|exploit)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "forged_documents",
        "forged travel documents",
        re.compile(
            r"\b(fake|faked|forge|forged|forging|counterfeit|counterfeited|"
            r"fraudulent|cloned|duplicate)\b[^.\n]{0,30}\b"
            r"(passport|passports|visa|visas|id|identity|identification|"
            r"boarding\s+pass|ticket|tickets|document|documents|permit)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "border_evasion",
        "evading border controls",
        re.compile(
            r"\b(evade|evading|bypass|bypassing|circumvent|circumventing|dodge|"
            r"dodging|sneak\s+(?:past|through|around)|smuggle\s+(?:past|through))\b"
            r"[^.\n]{0,35}\b"
            r"(immigration|customs|border|borders|passport\s+control|"
            r"security\s+check|security\s+screening|visa\s+requirement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "smuggling",
        "smuggling",
        re.compile(
            r"\b(smuggle|smuggling|smuggled|traffick(?:ing|ed)?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "contraband_transport",
        "transporting prohibited goods",
        re.compile(
            r"\b(carry|carrying|bring|bringing|transport|transporting|hide|hiding|"
            r"conceal|concealing|stash|stashing)\b[^.\n]{0,35}\b"
            r"(gun|guns|firearm|firearms|weapon|weapons|ammunition|explosive|"
            r"explosives|bomb|bombs|cocaine|heroin|methamphetamine|meth|"
            r"narcotics|illegal\s+drugs|contraband|ivory)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "payment_fraud",
        "payment fraud",
        re.compile(
            r"\b(stolen|cloned|hacked|someone\s+else'?s)\b[^.\n]{0,25}\b"
            r"(credit\s+card|debit\s+card|card\s+number|bank\s+account|"
            r"payment\s+method|air\s?miles|loyalty\s+account)\b"
            r"|\b(charge|book|pay)\b[^.\n]{0,25}\b(stolen|cloned)\b[^.\n]{0,20}\bcard\b",
            re.IGNORECASE,
        ),
    ),
]


@dataclass
class UnlawfulVerdict:
    blocked: bool = False
    subject: str | None = None
    reason: str | None = None
    matched_rules: list[str] = field(default_factory=list)


def scan(text: str) -> UnlawfulVerdict:
    """Look for a request to do something unlawful under cover of a trip.

    Unlike the injection classifier this is not weighted: these patterns
    require both an action and an object, so a single confident match is the
    whole signal. Ambiguous verbs are deliberately absent - "avoid the customs
    queue" is a reasonable thing to want, and only clearly evasive verbs are
    listed.
    """
    verdict = UnlawfulVerdict()
    if not text:
        return verdict

    for rule_id, subject, pattern in _RULES:
        if pattern.search(text):
            verdict.matched_rules.append(rule_id)
            if verdict.subject is None:
                verdict.subject = subject

    if verdict.matched_rules:
        verdict.blocked = True
        verdict.reason = f"Request involves {verdict.subject}, which is illegal and harmful."
    return verdict
