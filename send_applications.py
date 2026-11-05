import argparse
import asyncio
import json
import re
import smtplib
import sqlite3
import ssl
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlsplit

BASE = "https://tyomarkkinatori.fi"
LISTINGS = "/henkiloasiakkaat/avoimet-tyopaikat"
CITIES = {"helsinki", "espoo", "vantaa"}
CITY_NAMES = {"091": "Helsinki", "049": "Espoo", "092": "Vantaa"}
DIRECTORY = Path(__file__).resolve().parent

SEARCH_QUERIES = [
    # Kitchen & Restaurant
    "tiskari", "astianpesijä", "keittiöapulainen", "salityöntekijä", 
    "blokkari", "ravintolatyöntekijä", "apukokki", "kahvilatyöntekijä", "pikaruokatyöntekijä",
    "dishwasher", "kitchen helper", "kitchen hand", "restaurant worker", "cafe worker",
    
    # Cleaning & Sanitation
    "siivooja", "porrussiivooja", "toimistosiivooja", "rakennussiivooja", "toimitilahuoltaja", "siivousapulainen",
    "cleaner", "housekeeper", "janitor",
    
    # Logistics, Warehouse & Packing
    "varastotyöntekijä", "hyllyttäjä", "keräilijä", "pakkaaja", "lajittelija", "terminaalityöntekijä", "varastoapulainen",
    "warehouse worker", "packer", "order picker", "sorter",
    
    # Manufacturing, Construction & General Labor
    "tuotantotyöntekijä", "aputyöntekijä", "rakennusapulainen", "raksa-apulainen", "apumies", "purkutyöntekijä", "kokoaja", "hanttimies",
    "production worker", "construction helper", "general labor", "assembly worker",
    
    # Ship & Port Workers
    "laivatyöntekijä", "laivasiivooja", "kansimies", "satamatyöntekijä",
    "ship worker", "deckhand", "port worker", "ferry worker",
    
    # General Entry Level, Delivery & Seasonal
    "jakelija", "postinjakaja", "muuttomies", "rengasasentaja", "autonpesijä", "pesulatyöntekijä", "tapahtumatyöntekijä", "ulkoaluetyöntekijä", "lumityöntekijä",
    "delivery driver", "mover", "car washer", "event worker", "snow clearer"
]

ROLE_ALIASES = (
    "keittiötyöntekijä", "kitchen assistant", "food production worker",
    "elintarviketyöntekijä", "food production operative", "warehouse operative",
    "cleaning operative", "general labourer", "general laborer",
)
SUPERVISOR = r"päällikkö|johtaja|asiantuntija|esihenkilö|esimies|supervisor|manager|team lead|director"
ENGLISH = r"english (?:is (?:accepted|sufficient|enough|required)|speaking|as (?:a|the) working language)|working language(?: is|:)? english|(?:finnish or english|english or finnish)|(?:työkieli(?:nä)? (?:on )?englanti|englanti (?:riittää|käy)|suomi tai englanti|englanti tai suomi|(?:suomen tai englannin|englannin tai suomen) kielen taito)"
FLUENT_FINNISH = r"(?:sujuv\w*|hyv\w*|erinomai\w*)\s+suomen|suomea sujuvasti|suomen kielen taitoa? (?:vaaditaan|edellytetään)|fluent finnish|finnish fluency|finnish (?:is )?(?:mandatory|required)|(?:good|excellent|native) (?:command of )?finnish"
BASIC_FINNISH = r"basic finnish|finnish (?:is )?(?:a plus|an advantage|optional|not required)|suomen alkeet|suomen kielen alkeet|suomen (?:kielen )?perustaidot|suomen kielen taito (?:on etu|katsotaan eduksi)"
REQUIREMENT = r"ajokortti|driv(?:er.s|ing) licen[cs]e|työturvallisuuskortti|occupational safety card|trukkikortti|forklift licen[cs]e|(?:\d+|one|two|three|kahden|kolmen)\s*\+?\s*(?:years?|vuoden)\s*(?:of |työ)?(?:experience|kokemu)"
PASSPORT = r"hygieniapass\w*|hygiene pass(?:port)?"
PORTAL_ONLY = r"do not (?:apply|send (?:your )?applications?) (?:by|via) (?:e-?mail)|(?:applications?|cvs?) (?:by|via) (?:e-?mail) (?:will not be|are not|are never) (?:accepted|considered|processed)|no (?:e-?mail applications|applications by e-?mail)|älä lähetä (?:hakemusta|hakemuksia) sähköpostitse|(?:emme hyväksy|ei oteta vastaan|ei käsitellä) sähköposti|only (?:accept|consider) applications (?:via|through)|only applications (?:submitted|received) (?:via|through)|emme (?:käsittele|vastaanota) sähköposti|vain (?:järjestelmän|lomakkeen|linkin) kautta"
PORTAL_ROUTE = r"apply (?:online|via (?:the |our )?(?:link|website|portal|form|system)|through (?:the |our )?(?:link|website|portal|form|system))|täytä (?:sähköinen )?hakemus|hae (?:alla olevan |oheisen )?(?:linkin|lomakkeen|järjestelmän|verkkosivujen) kautta|jätä hakemus (?:lomakkeella|järjestelmässä)"
EMAIL_LINE = r"(?:\bapply (?:by email|via email|at|to)|\bsend (?:your )?(?:application|cv)(?=\s*(?:to\b|by\b|via\b|:))|\blähetä (?:hakemuksesi|hakemus|cv)(?=\s*(?:suomeksi\b|osoitteeseen\b|sähköpostitse\b|:))|\bhae sähköpostitse)[^\n]{0,120}"
EMAIL_ADDRESS = r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+"
APPLICATION_FINNISH = r"(?:apply|application) in finnish|(?:hakemus|hakemukset) suomeksi"


@dataclass
class Listing:
    url: str
    title: str
    description: str
    municipalities: list[str]
    work_languages: list[str]
    application: str
    source: str = ""


def match(pattern, value):
    return re.search(pattern, value, re.IGNORECASE) is not None


def listing_deadline(job):
    value = re.search(r"(?:Hakuaika päättyy|Application deadline)\s*:?\s*(\d{1,2}\.\d{1,2}\.\d{4})",
                      job.description, re.I)
    if value:
        try:
            return datetime.strptime(value.group(1), "%d.%m.%Y").date()
        except ValueError:
            return None
    return None


def published_contacts(job):
    contacts = {}
    for line in (job.application + "\n" + job.description).splitlines():
        normalized = re.sub(r"\s*(?:\(at\)|\[at\]|\(ät\))\s*", "@", line, flags=re.I)
        for address in re.findall(EMAIL_ADDRESS, normalized):
            address = address.casefold()
            if not match(r"^(?:no-?reply|support|tuki)@|@(?:tyomarkkinatori\.fi|jobly\.fi|kuntarekry\.fi|duunitori\.fi)$", address):
                contacts.setdefault(address, line.strip()[:240])
    return contacts


def evaluate(job, profile):
    deadline = listing_deadline(job)
    if deadline and deadline < date.today():
        return "skip", "The application deadline has passed.", None
    cities = {name.strip().casefold() for name in job.municipalities if name.strip()}
    if not cities or (cities & CITIES and cities - CITIES):
        return "review", "worksite missing or mixed", None
    if not cities <= CITIES:
        return "skip", "worksite outside target cities", None

    if match(PORTAL_ONLY, job.description + "\n" + job.application):
        return "portal", "employer prohibits email applications", None
    if match(PORTAL_ROUTE, job.application):
        return "portal", "use the application portal listed by the employer", None

    title = job.title.casefold()
    if match(SUPERVISOR, title):
        return "skip", "supervisory or specialist role", None
    description = job.description
    if match(FLUENT_FINNISH, description) and not match(BASIC_FINNISH, description):
        return "skip", "Finnish requirement exceeds basic level", None
    if match(FLUENT_FINNISH, description):
        return "review", "conflicting Finnish requirements", None
    addresses = {
        email.casefold()
        for instruction in re.findall(EMAIL_LINE, job.application, re.IGNORECASE)
        if not match(r"\b(?:questions?|enquiries|inquiries|lisätiedot|tiedustelut)\b", instruction)
        for email in re.findall(EMAIL_ADDRESS, instruction)
        if not match(r"^(?:no-?reply|support|tuki)@|@(?:example\.com|tyomarkkinatori\.fi)$", email)
    }
    if len(addresses) != 1:
        return "review", "application email missing or ambiguous", None
    return "draft", "Email applications accepted", addresses.pop()


TEMPLATES = {
    "warehouse": (
        r"varasto|keräilij|pakkaaj|lajittelij|terminaali|warehouse|order pick|pack|sorter",
        "A busy warehouse needs people who can keep the pace without passing mistakes down the line. I’d learn your checks, keep my area in order, and make sure the next person has what they need to keep moving.",
        "Kiireisessä varastossa on tärkeää pitää työtahti tasaisena ja ehkäistä virheet ennen seuraavaa työvaihetta. Opettelisin tarkistuksenne, pitäisin oman työalueeni järjestyksessä ja huolehtisin, että seuraava työntekijä pääsee jatkamaan sujuvasti.",
    ),
    "cleaning": (
        r"siivoo|siivous|toimitilahuol|clean|housekeep|janitor",
        "What appeals to me is keeping your sites clean and ready for the people who use them. I’d follow the site’s cleaning plan, check the work before leaving, and give high-use areas the attention they need.",
        "Minua motivoi se, että tilat jäävät siisteiksi ja käyttövalmiiksi. Noudattaisin kohteen siivoussuunnitelmaa, tarkistaisin työn jäljen ennen lähtöä ja kiinnittäisin erityistä huomiota paljon käytettyihin tiloihin.",
    ),
    "food_service": (
        r"ravintola|keittiö|astia|tiskari|kokki|kahvila|blokkari|ruoka|food|kitchen|restaurant|dishwash|cafe",
        "In a busy restaurant, I’d look for what the team needs next: a clean station, equipment ready to use, or a colleague who could use another pair of hands. I’d learn how you run a shift and make myself useful from the start.",
        "Kiireisessä ravintolassa katson, mitä tiimi tarvitsee seuraavaksi: puhtaan työpisteen, käyttövalmiit välineet tai apua toiselle työntekijälle. Opettelisin vuoronne työtavat ja tarttuisin töihin alusta asti.",
    ),
    "production": (
        r"tuotanto|kokoaja|assembly|production|manufactur",
        "I understand how much the rest of the line depends on one person doing their part properly. I’d learn the checks for my station, work at a dependable pace, and raise problems early so the team can deal with them.",
        "Ymmärrän, miten paljon muu tuotantolinja riippuu siitä, että jokainen hoitaa oman työvaiheensa kunnolla. Opettelisin työpisteeni tarkistukset, pitäisin tasaisen työtahdin ja ilmoittaisin poikkeamista ajoissa.",
    ),
    "site_work": (
        r"rakennus|raksa|purku|apumies|aputyö|construction|labour|labor",
        "A crew works better when people notice what needs doing and communicate before moving on. I’d stay attentive to instructions, keep tools and materials where they’re needed, and leave the work area ready for the next task.",
        "Työryhmä toimii paremmin, kun työntekijät huomaavat, mitä pitää tehdä, ja kertovat toisilleen työn etenemisestä. Kuuntelisin ohjeet, pitäisin työkalut ja materiaalit saatavilla ja jättäisin työalueen valmiiksi seuraavaa tehtävää varten.",
    ),
    "retail_stock": (
        r"hyllyttäj|stock replen|shelf stack",
        "I’d keep products easy to find for customers and stock easy to locate for colleagues. In a busy shift I’d learn what needs replenishing first and finish each area properly before moving on.",
        "Huolehtisin, että asiakkaat löytävät tuotteet hyllystä ja kollegat varastosta. Kiireisessä vuorossa opettelisin, mitä kannattaa täydentää ensin, ja viimeistelisin oman alueeni ennen seuraavaan tehtävään siirtymistä.",
    ),
    "port": (
        r"satama|laivatyö|kansimies|deckhand|port worker|ferry worker|ship worker",
        "I would take your site and equipment procedures seriously from the first shift. My aim would be to do physical work steadily, communicate clearly around shared equipment, and be a person the crew can rely on.",
        "Ottaisin työpaikan ja laitteiden turvallisuusohjeet vakavasti ensimmäisestä vuorosta lähtien. Tekisin fyysistä työtä tasaisella tahdilla, pitäisin yhteyttä muihin yhteisten laitteiden äärellä ja hoitaisin oman osuuteni luotettavasti.",
    ),
    "moving": (
        r"muuttomies|mover",
        "People remember how their belongings were treated on moving day. I would work steadily, coordinate lifts with the crew, and give the last box the same care as the first.",
        "Asiakkaalle jää mieleen, miten hänen tavaroitaan käsiteltiin muuttopäivänä. Tekisin työtä tasaisesti, sopisin nostoista työryhmän kanssa ja käsittelisin viimeisenkin laatikon yhtä huolellisesti kuin ensimmäisen.",
    ),
    "events": (
        r"tapahtumatyöntekijä|event worker",
        "I’d pay attention to what makes an event run smoothly for both guests and colleagues. That means finishing setup properly, stepping in when something changes, and giving the next shift a clear handover.",
        "Kiinnittäisin huomiota siihen, mikä tekee tapahtumasta sujuvan vieraille ja kollegoille. Valmistelisin oman osuuteni huolellisesti, auttaisin tilanteen muuttuessa ja kertoisin seuraavalle vuorolle, mitä on vielä tehtävä.",
    ),
    "outdoor": (
        r"ulkoalue|lumityöntekijä|snow clear",
        "I’m comfortable with work where the conditions change but the job still needs doing. I’d come prepared, follow your priorities for the day, and leave the area in a condition the next crew can work with.",
        "Minulle sopii työ, jossa olosuhteet vaihtuvat mutta tehtävät on silti hoidettava. Tulisinkin töihin varautuneena, noudattaisin päivän tärkeysjärjestystä ja jättäisin alueen seuraavalle työryhmälle hyvään kuntoon.",
    ),
    "vehicle_care": (
        r"rengasasentaja|autonpesijä|car washer",
        "I’d take the time to learn your tools and quality checks, then work efficiently without rushing the finish. I want the person receiving the vehicle to see that someone took care with the work.",
        "Opettelisin työvälineenne ja laatutarkistuksenne, jotta voisin työskennellä tehokkaasti ja viimeistellä työn huolellisesti. Minulle on tärkeää, että työn jälki näkyy myös ajoneuvon vastaanottajalle.",
    ),
    "delivery": (
        r"jakelij|muuttomies|delivery|mover",
        "People plan their day around a delivery. I’d check that each handover is in order, keep the team informed, and speak up early if a delay or mix-up needs attention.",
        "Ihmiset suunnittelevat päivänsä toimitusten mukaan. Tarkistaisin, että jokainen luovutus on kunnossa, pitäisin tiimin ajan tasalla ja kertoisin ajoissa, jos viive tai epäselvyys vaatii huomiota.",
    ),
}


def role_for(job):
    return next((key for key, (pattern, _, _) in TEMPLATES.items() if match(pattern, job.title)), None)


AD_DUTIES = (
    (r"order picking|pick(?:ing)? orders|keräil", "order picking", "tilausten keräily",
     "check items against the order as I go", "tarkistaisin tuotteet tilauksesta keräilyn aikana"),
    (r"pack(?:ing|aging)|pakkaami|pakkaus", "packing", "pakkaaminen",
     "make sure each package is ready for the next person to handle", "varmistaisin, että pakkaukset ovat valmiina seuraavaan työvaiheeseen"),
    (r"loading and unloading|unloading|purkaminen|kuorman purku", "handling incoming goods", "saapuvan tavaran käsittely",
     "keep incoming goods organised and the handling area clear", "pitäisin saapuvan tavaran järjestyksessä ja kulkureitit vapaina"),
    (r"food prep|prepar(?:ing|ation of) food|ruoan (?:esi)?valmist", "food preparation", "ruoan valmistelu",
     "keep prep moving and have the next ingredients ready when the kitchen needs them", "huolehtisin, että valmistelu etenee ja raaka-aineet ovat valmiina, kun keittiö tarvitsee niitä"),
    (r"dishwash|washing dishes|astianpes|astiahuol", "dishwashing", "astiahuolto",
     "keep clean dishes and equipment coming through during the rush", "huolehtisin puhtaiden astioiden ja välineiden riittävyydestä myös ruuhkassa"),
    (r"customer service|serving guests|asiakaspalvel|tarjoilu", "customer service", "asiakaspalvelu",
     "give customers my attention and keep colleagues informed when things get busy", "kohtaisin asiakkaat ystävällisesti ja pitäisin työkaverit ajan tasalla myös kiireessä"),
    (r"cleaning (?:the |of )?(?:premises|offices|rooms)|siivous|puhtaanapito", "cleaning and upkeep", "siivous ja puhtaanapito",
     "follow the site’s routine and check the result before leaving the area", "noudattaisin kohteen työjärjestystä ja tarkistaisin työn jäljen ennen kuin siirryn eteenpäin"),
    (r"production line|tuotantolinj", "production-line work", "tuotantolinjalla työskentely",
     "keep a steady pace and flag interruptions early", "pitäisin tasaisen työtahdin ja ilmoittaisin häiriöistä ajoissa"),
    (r"quality (?:control|checks)|laadunvalvonta|laatutarkast", "quality checks", "laatutarkastukset",
     "do the agreed checks carefully even when the line is busy", "tekisin sovitut tarkistukset huolellisesti myös kiireessä"),
    (r"shelf replenishment|stocking shelves|hyllyttäminen|hyllytys", "replenishing stock", "hyllyjen täydentäminen",
     "keep the shelves easy to shop from and the stock area easy to work in", "pitäisin hyllyt asiakkaille selkeinä ja varaston työskentelykunnossa"),
    (r"event setup|setting up events|tapahtumien valmistelu", "event setup", "tapahtumien valmistelu",
     "get my part of the setup ready before guests arrive", "hoitaisin oman osuuteni valmisteluista ennen vieraiden saapumista"),
    (r"snow remov|snow clear|lumityö|lumenpoisto", "snow clearance", "lumityöt",
     "start with the routes people rely on most and leave them usable", "aloittaisin käytetyimmistä kulkureiteistä ja jättäisin ne kulkukelpoisiksi"),
)


def advertised_duties(job, finnish):
    matching = [duty for duty in AD_DUTIES if match(duty[0], job.description)][:2]
    names = (" ja " if finnish else " and ").join(duty[2 if finnish else 1] for duty in matching)
    return names, [duty[4 if finnish else 3] for duty in matching]



def draft(job, profile, template="auto", language="auto"):
    if template not in {"auto", "general"} and template not in TEMPLATES:
        raise ValueError("Choose a valid template.")
    if language not in {"auto", "en", "fi"}:
        raise ValueError("Choose a valid email language.")
    finnish_required = match(APPLICATION_FINNISH, job.application)
    english_required = match(r"(?:apply|application) in english|(?:hakemus|hakemukset) englanniksi", job.application)
    if (finnish_required and language == "en") or (english_required and language == "fi"):
        raise ValueError("Use the application language requested by the employer.")
    finnish = finnish_required or (language == "fi" and not english_required)
    name = (profile.get("name") or "").strip()
    role = role_for(job)
    chosen = role if template == "auto" else template
    if chosen in TEMPLATES:
        _, motivation_en, motivation_fi = TEMPLATES[chosen]
        motivation = motivation_fi if finnish else motivation_en
    else:
        motivation = (
            "Perehtyisin ensin siihen, mitä vuorossa pitää saada valmiiksi. Tarttuisin tarvittaviin tehtäviin, kysyisin ajoissa, jos jokin on epäselvää, ja hoitaisin oman osuuteni loppuun asti."
            if finnish else
            "I’d learn what needs to get done first, pitch in where the team needs help, and ask early if something is unclear. I want the people working alongside me to know they can count on me to finish my part."
        )
    relevant_passport = profile.get("hygiene_passport") and match(PASSPORT, job.description)
    if finnish:
        subject = f"Hakemus – {job.title}"
        opening = f"Haen ilmoittamaanne tehtävää ({job.title})."
        passport = "Minulla on suomalainen hygieniapassi."
        closing_text = "Ansioluetteloni on liitteenä. Keskustelisin mielelläni siitä, miten voisin auttaa tiimiänne."
        signoff = "Ystävällisin terveisin,"
        work_ethic = "Olen ahkera työntekijä, joka tulee ajoissa, tarttuu töihin ja pitää tasaisen työtahdin myös kiireessä."
    else:
        subject = f"Application – {job.title}"
        opening = f"I’d like to apply for the {job.title} position."
        passport = "I hold a Finnish Hygiene Passport."
        closing_text = "I’ve attached my CV and would be glad to talk about how I could help your team."
        signoff = "Kind regards,"
        work_ethic = "I’m hard-working and dependable. I show up ready, keep going when the shift gets busy, and take care with the work until it’s finished."
    duties, actions = advertised_duties(job, finnish) if template != "general" else ("", [])
    detail = (
        f"Ilmoituksessa huomioni kiinnittyi erityisesti tähän työnkuvaan: {duties}."
        if finnish else f"What caught my attention in your ad was the emphasis on {duties}."
    ) if duties else ""
    if actions:
        if finnish:
            motivation = ". ".join(action[0].upper() + action[1:] for action in actions) + "."
        else:
            motivation = "On your team, I’d " + " and ".join(actions) + "."
    first = " ".join(part for part in (opening, detail, work_ethic) if part)
    second = " ".join(part for part in (motivation, passport if relevant_passport else "", closing_text) if part)
    signature = f"{signoff}\n{name}" if name else signoff
    return subject, "\n\n".join(("Hei," if finnish else "Hello,", first, second, signature))



def vacancy_key(url):
    parts = urlsplit(url).path.casefold().rstrip("/").split("/")
    path = parts[-2] if len(parts) > 1 and parts[-1] in {"fi", "en", "sv"} else parts[-1]
    identifier = re.search(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$", path)
    return identifier.group() if identifier else path


def history_status(db, job, recipient):
    key = vacancy_key(job.url)
    row = db.execute("SELECT state FROM delivery_log WHERE vacancy = ?", (key,)).fetchone()
    if row:
        return row[0]
    legacy_rows = db.execute("SELECT url FROM processed_urls WHERE status = 'SENT'")
    if any(vacancy_key(url) == key for (url,) in legacy_rows):
        return "sent"
    rows = db.execute("SELECT job_url FROM contacted_recipients WHERE lower(email) = ?", (recipient,))
    contacts = list(rows)
    if any(url and vacancy_key(url) == key for (url,) in contacts):
        return "sent"
    if any(not url for (url,) in contacts):
        return "legacy contact – verify before applying"
    legacy_log = DIRECTORY / "sent_emails.txt"
    if not contacts and legacy_log.is_file():
        if recipient in {line.strip().casefold() for line in legacy_log.read_text(encoding="utf-8-sig").splitlines()}:
            return "legacy contact – verify before applying"
    return None


def open_history():
    db = sqlite3.connect(DIRECTORY / "applications.db")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS processed_urls (url TEXT PRIMARY KEY, status TEXT);
        CREATE TABLE IF NOT EXISTS contacted_recipients (email TEXT PRIMARY KEY, job_url TEXT);
        CREATE TABLE IF NOT EXISTS delivery_log (vacancy TEXT PRIMARY KEY, state TEXT NOT NULL);
    """)
    return db


def cv_path(profile, job=None):
    role_cv = profile.get("role_cvs", {}).get(role_for(job)) if job else None
    return DIRECTORY / (role_cv or profile.get("cv", "cv.pdf"))


def make_message(recipient, profile, subject, body, job=None):
    cv = cv_path(profile, job)
    if not profile.get("sender") or not profile.get("name") or not cv.is_file():
        raise ValueError("Set sender and name in profile.json and provide your local CV.")
    message = EmailMessage()
    message["From"] = profile["sender"]
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    message.add_attachment(cv.read_bytes(), maintype="application", subtype="pdf", filename=cv.name)
    return message


@contextmanager
def smtp_session(sender, password):
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(sender, password.replace(" ", ""))
        yield server


def send_reviewed(server, job, recipient, message):
    key = vacancy_key(job.url)
    with closing(open_history()) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            previous = history_status(db, job, recipient)
            if previous:
                return "already sent" if previous == "sent" else previous
            db.execute("INSERT INTO delivery_log VALUES (?, 'pending verification')", (key,))
        try:
            server.send_message(message)
        except (smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused, smtplib.SMTPDataError):
            with db:
                db.execute("DELETE FROM delivery_log WHERE vacancy = ?", (key,))
            raise
        with db:
            db.execute("UPDATE delivery_log SET state = 'sent' WHERE vacancy = ?", (key,))
    return "sent"


def canonical_url(href):
    url = urlsplit(urljoin(BASE, href))
    if url.scheme == "https" and url.netloc == urlsplit(BASE).netloc:
        path = url.path.rstrip("/")
        if re.fullmatch(rf"{LISTINGS}/[^/]+(?:/(?:fi|en|sv))?", path):
            return BASE + path
    return None


def field_lines(lines, labels, multiline=False):
    for index, line in enumerate(lines):
        label, colon, value = line.partition(":")
        if label.casefold() in labels:
            if not multiline:
                return value.strip() if colon and value.strip() else (lines[index + 1] if index + 1 < len(lines) else "")
            section = [value.strip()] if colon and value.strip() else []
            for following in lines[index + 1:]:
                if following.partition(":")[0].casefold() in SECTION_LABELS:
                    break
                section.append(following)
            return "\n".join(section)
    return ""


LOCATION_LABELS = {"työskentelyalue", "työskentelypaikkakunta", "sijainti", "työpaikan sijainti", "työskentelypaikan sijainti", "location", "job location"}
LANGUAGE_LABELS = {"työkieli", "työkielet", "working language", "working languages"}
APPLICATION_LABELS = {"hakuohjeet", "hakeminen", "how to apply", "application instructions"}
SECTION_LABELS = LOCATION_LABELS | LANGUAGE_LABELS | APPLICATION_LABELS | {
    "työpaikan kuvaus", "työn kuvaus", "job description", "lisätietoja", "yhteystiedot",
    "contact information", "additional information", "työnantaja", "employer",
    "työpaikan tiedot", "job details", "hakuaika", "application period",
}


def worksite(lines):
    # The vacancy header places its worksite immediately above the deadline.
    for index, line in enumerate(lines[:16]):
        if index and match(r"^(?:Hakuaika päättyy|Application deadline)", line):
            header = lines[index - 1]
            parts = [part.strip() for part in header.split(",")]
            if re.fullmatch(r"\d{3}(?:,\s*\d{3})*(?:,\s*\d{2})?(?:,\s*FI)?", header):
                return ", ".join(CITY_NAMES.get(code, f"Municipality {code}")
                                 for code in parts if len(code) == 3)
            if len(parts) > 1 and parts[-1].casefold() in {"suomi", "finland", "fi"}:
                return ", ".join(parts[:-1])
            if header.casefold() in CITIES:
                return header
            break
    return field_lines(lines, LOCATION_LABELS, multiline=True)


def parse_listing(url, title, content):
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    location = worksite(lines)
    languages = field_lines(lines, LANGUAGE_LABELS)
    application = field_lines(lines, APPLICATION_LABELS, multiline=True)
    if not application:
        application = "\n".join(line for line in lines if match(EMAIL_LINE, line) or match(PORTAL_ROUTE, line))
    split = r"\s*(?:[,;/\n]|\bja\b|\band\b)\s*"
    return Listing(url, " ".join(title.split()), content,
                   re.split(split, location), re.split(split, languages), application)


async def read_listing(page, link, report):
    try:
        response = await page.goto(link, wait_until="domcontentloaded", timeout=15000)
        if not response or not response.ok or canonical_url(page.url) != link:
            report(f"review | listing unavailable | {link}")
            return None
        main = page.locator("main").last
        title = await main.locator("h1").first.inner_text(timeout=8000)
        job = parse_listing(link, title, await main.inner_text(timeout=8000))
        apply_links = main.get_by_role("link", name=re.compile(r"^(?:Hae työpaikkaa|Apply(?: for (?:the|this) job)?)$", re.I))
        for apply_link in await apply_links.all():
            href = await apply_link.get_attribute("href") or ""
            if href.startswith("mailto:"):
                job.application += "\nApply by email: " + urlsplit(href).path
            elif href and not href.startswith("#"):
                job.application += "\nApply via the portal: " + urljoin(link, href)
        contacts = await main.locator('a[href^="mailto:"]').evaluate_all(
            "links => links.map(link => link.getAttribute('href'))")
        for href in contacts:
            address = urlsplit(href).path
            if address and address.casefold() not in job.description.casefold():
                job.description += "\nPublished contact: " + address
        return job
    except Exception as error:
        report(f"Could not read listing ({type(error).__name__}): {link}")
    return None


async def result_pages(page, query, max_pages, report, cancelled):
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    selector = f'a[href*="{LISTINGS}/"]'
    links = page.locator(selector)
    try:
        response = await page.goto(f"{BASE}{LISTINGS}?{urlencode({'q': query})}",
                                   wait_until="domcontentloaded", timeout=15000)
        if not response or not response.ok:
            report(f"Search unavailable: {query}")
            return
        await links.first.wait_for(timeout=20000, state="attached")
    except PlaywrightTimeoutError:
        report(f"No result links loaded: {query}")
        return

    for number in range(1, max_pages + 1):
        if cancelled():
            return
        report(f"Reading search results · {query} · page {number}")
        cards = await links.evaluate_all("""items => items.map(item => [
            item.href, (item.closest('article, li') || item.parentElement.parentElement).innerText
        ])""")
        ranked = sorted(cards, key=lambda card: not match(r"\bhelsinki\b|\bespoo\b|\bvantaa\b", card[1]))
        yield [link for href, _ in ranked if (link := canonical_url(href))]
        if number == max_pages or cancelled():
            return
        controls = page.get_by_role("button", name=re.compile(r"seuraava|next", re.I)).or_(
            page.get_by_role("link", name=re.compile(r"seuraava|next", re.I)))
        next_page = controls.first
        if not await next_page.count() or not await next_page.is_enabled():
            return
        try:
            await next_page.click(timeout=3000)
            await page.wait_for_function(
                "([selector, before]) => [...document.querySelectorAll(selector)].some(a => !before.includes(a.href))",
                arg=[selector, [href for href, _ in cards]], timeout=12000,
            )
        except PlaywrightTimeoutError:
            report(f"Could not load the next result page: {query}")
            return


async def scrape(queries, limit, report=print, listing_urls=None, max_pages=1, cancelled=lambda: False):
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context()
            search_page = await context.new_page()
            workers = [await context.new_page() for _ in range(4)]
            seen = set()
            collected = 0

            async def read_links(links):
                nonlocal collected
                pending = []
                for link in links:
                    key = vacancy_key(link)
                    if key not in seen:
                        seen.add(key)
                        pending.append(link)
                start = 0
                while start < len(pending):
                    if cancelled() or collected >= limit:
                        return
                    batch = pending[start:start + min(len(workers), limit - collected)]
                    start += len(batch)
                    report(f"Opening {len(batch)} listings · {collected} collected")
                    tasks = [asyncio.create_task(read_listing(page, link, report))
                             for page, link in zip(workers, batch)]
                    try:
                        for completed in asyncio.as_completed(tasks):
                            job = await completed
                            if job:
                                collected += 1
                                yield job
                    finally:
                        await asyncio.gather(*tasks, return_exceptions=True)

            if listing_urls is not None:
                async for job in read_links(listing_urls):
                    yield job
                return
            for index, query in enumerate(queries, 1):
                if cancelled() or collected >= limit:
                    break
                report(f"Searching {index}/{len(queries)} · {query}")
                async for links in result_pages(search_page, query, max_pages, report, cancelled):
                    async for job in read_links(links):
                        yield job
                    if cancelled() or collected >= limit:
                        break
        finally:
            await browser.close()


async def run(args, profile):
    if args.offline:
        listings = [Listing(**entry) for entry in json.loads(args.offline.read_text(encoding="utf-8-sig"))]
    else:
        listings = [job async for job in scrape(args.query or SEARCH_QUERIES, args.limit)]
    if not listings:
        print("No listings read. Check the search results and scraper before relying on this run.")
    for job in listings:
        decision, reason, recipient = evaluate(job, profile)
        print(f"{decision} | {job.title} | {reason} | {job.url}")
        if recipient:
            subject, body = draft(job, profile)
            print(f"To: {recipient}\nSubject: {subject}\n\n{body}\n")


def load_profile():
    path = DIRECTORY / "profile.json"
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}


def main():
    parser = argparse.ArgumentParser(description="Preview Job Market Finland applications.")
    parser.add_argument("--query", action="append", help="Search term. Repeat to use more terms.")
    parser.add_argument("--limit", type=int, default=30, help="Maximum live listings to inspect.")
    parser.add_argument("--offline", type=Path, help="Preview saved listings from a local JSON file.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")
    asyncio.run(run(args, load_profile()))


if __name__ == "__main__":
    main()
