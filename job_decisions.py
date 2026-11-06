"""Conservative recommendations for the user's suggested email batch."""

import re

from send_applications import (
    BASIC_FINNISH, CITIES, EMAIL_LINE, PASSPORT, PORTAL_ONLY, REQUIREMENT, match,
    parse_listing, published_contacts, role_for,
)

REGULATED = r"valvira|laillistett[ua]|registered (?:nurse|healthcare)|(?:nursing|practical nurse) qualification|(?:sairaanhoitajan|lähihoitajan) (?:tai lähihoitajan )?(?:koulutus|tutkinto)"
QUALIFICATION = r"(?:vaaditaan|edellytämme|edellytetään|kelpoisuusvaatimus|required|must have|mandatory)[^.!?\n]{0,90}(?:qualification|degree|certificate|license|licence|tutkint|pätevy|kortti)|(?:qualification|degree|certificate|license|licence|tutkint\w*|pätevy\w*|kortti)\s+(?:is required|is mandatory|vaaditaan|edellytetään)"
ADVANTAGE = r"an advantage|a plus|nice to have|katsotaan eduksi|on etu|plussaa"


def excerpt(description, pattern):
    for line in description.splitlines():
        hit = re.search(pattern, line, re.I)
        if hit:
            start = max(0, hit.start() - 45)
            return line[start:start + 220].strip()
    return ""


def batch_recipient(job, status, verified_recipient=None):
    """Choose one public recruiting address after verifying the worksite from the ad."""
    if status in {"skip", "held", "sent"} or match(PORTAL_ONLY, job.application + "\n" + job.description):
        return None
    # Search-page matches can contain an employer's office or omit other worksites.
    worksites = parse_listing(job.url, job.title, job.description).municipalities
    cities = {city.strip().casefold() for city in worksites if city.strip()}
    if not cities or not cities <= CITIES:
        return None
    if verified_recipient:
        return verified_recipient
    candidates = []
    for address, context in published_contacts(job).items():
        mailbox = address.split("@", 1)[0]
        if match(r"privacy|tietosuoja|media enquiries|press contact|unsubscribe", context):
            continue
        if match(EMAIL_LINE, context) and not match(r"questions?|enquiries|inquiries|lisätiedot|tiedustelut", context):
            priority = 3
        elif match(r"recruit|rekry|hiring|lisätiedot|yhteyshenkilö|contact person", context + " " + mailbox):
            priority = 2
        elif re.fullmatch(r"[\w-]+\.[\w-]+", mailbox):
            priority = 1
        else:
            continue
        candidates.append((-priority, address))
    return min(candidates)[1] if candidates else None


def assess(job, profile, status, reason, english):
    """Return a reason and evidence without changing the employer's application route."""
    if status in {"skip", "held", "sent"}:
        return {"fit": "outside", "reason": reason, "evidence": "", "priority": 0}

    def result(fit, explanation, pattern="", priority=0):
        return {"fit": fit, "reason": explanation,
                "evidence": excerpt(job.description, pattern) if pattern else "", "priority": priority}

    cities = {city.strip().casefold() for city in job.municipalities if city.strip()}
    if not cities or not cities <= CITIES:
        return result("check", "Confirm the actual worksite.")
    if match(REGULATED, job.description):
        return result("check", "The ad mentions a regulated qualification. Check that you meet it.", REGULATED)
    if match(QUALIFICATION, job.description):
        return result("check", "Check the qualification required in the ad.", QUALIFICATION)
    for line in job.description.splitlines():
        if (match(REQUIREMENT, line) or (match(PASSPORT, line) and not profile.get("hygiene_passport"))) and not match(ADVANTAGE, line):
            return {"fit": "check", "reason": "Check the licence, certificate, or experience mentioned.",
                    "evidence": line.strip()[:220], "priority": 0}
    if not role_for(job):
        return result("check", "Check whether this role matches your practical work preferences.")
    if not english and not match(BASIC_FINNISH, job.description):
        return result("check", "The ad does not clearly confirm English or basic Finnish.")
    if status == "portal":
        return result("online", "The role looks relevant. Follow the employer’s application instructions.")
    if status != "draft":
        return result("check", reason)
    return result("ready", "Local worksite, relevant role, and a verified application email.",
                  priority=2 if english else 1)
