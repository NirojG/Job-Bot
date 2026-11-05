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
        "I’m comfortable with physical work and a busy pace. I learn new routines quickly and can adapt when the team needs me to switch between picking, packing, and keeping the work area organised.",
        "Olen tottunut fyysiseen työhön ja reippaaseen työtahtiin. Opin uudet rutiinit nopeasti ja siirryn joustavasti keräilyn, pakkaamisen ja työalueen järjestämisen välillä.",
    ),
    "cleaning": (
        r"siivoo|siivous|toimitilahuol|clean|housekeep|janitor",
        "I work carefully and can adapt to different cleaning sites and schedules. I’d learn your routines, keep track of what has been done, and check the result before moving on.",
        "Teen työni huolellisesti ja sopeudun erilaisiin siivouskohteisiin ja työaikoihin. Opettelisin kohteen rutiinit, seuraisin tehtävien etenemistä ja tarkistaisin työn jäljen ennen siirtymistä seuraavaan kohteeseen.",
    ),
    "food_service": (
        r"ravintola|keittiö|astia|tiskari|kokki|kahvila|blokkari|ruoka|food|kitchen|restaurant|dishwash|cafe",
        "I’m comfortable working at a busy pace and switching between tasks as needed. In a restaurant, I’d help keep prep moving, make sure clean dishes and equipment are ready, and support the team during a rush.",
        "Olen tottunut reippaaseen työtahtiin ja vaihdan tehtävästä toiseen tarpeen mukaan. Ravintolassa auttaisin esivalmisteluissa, huolehtisin puhtaiden astioiden ja välineiden saatavuudesta ja tukisin tiimiä ruuhkassa.",
    ),
    "production": (
        r"tuotanto|kokoaja|assembly|production|manufactur",
        "I’m comfortable with practical work that calls for a steady pace and attention to detail. I’d learn the routine at my station, follow the checks, and flag any issue that could hold up the next stage.",
        "Minulle sopii käytännön työ, jossa tarvitaan tasaista työtahtia ja tarkkuutta. Opettelisin työpisteeni rutiinit, tekisin sovitut tarkistukset ja kertoisin ajoissa ongelmista, jotka voivat hidastaa seuraavaa työvaihetta.",
    ),
    "site_work": (
        r"rakennus|raksa|purku|apumies|aputyö|construction|labour|labor",
        "I’m comfortable with physical work and adapting to the tasks a crew needs done that day. I follow instructions carefully and would keep tools, materials, and the work area ready for the next task.",
        "Olen tottunut fyysiseen työhön ja sopeudun työryhmän päivän tehtäviin. Noudatan ohjeita huolellisesti ja pitäisin työvälineet, materiaalit ja työalueen valmiina seuraavaa tehtävää varten.",
    ),
    "retail_stock": (
        r"hyllyttäj|stock replen|shelf stack",
        "I can adapt when priorities change on a busy shop floor. I’d keep stock organised, refill what’s needed first, and leave the shelves easy for customers to shop from.",
        "Sopeudun muuttuviin tehtäviin myös kiireisessä myymälässä. Pitäisin varaston järjestyksessä, täydentäisin tarvittavat tuotteet ensin ja huolehtisin hyllyjen selkeydestä.",
    ),
    "port": (
        r"satama|laivatyö|kansimies|deckhand|port worker|ferry worker|ship worker",
        "I’m comfortable with physical work and working alongside others around shared equipment. I’d learn your safety routines and communicate clearly so the crew can work together smoothly.",
        "Olen tottunut fyysiseen työhön ja yhteistyöhön yhteisten työvälineiden äärellä. Opettelisin turvallisuuskäytäntönne ja pitäisin yhteyttä muihin, jotta työ sujuu turvallisesti.",
    ),
    "moving": (
        r"muuttomies|mover",
        "I’m comfortable with physical work and working at a steady pace. I’d coordinate lifting with the team, adapt to each site, and handle customers’ belongings carefully throughout the move.",
        "Olen tottunut fyysiseen työhön ja tasaiseen työtahtiin. Sopisin nostoista tiimin kanssa, sopeutuisin eri kohteisiin ja käsittelisin asiakkaiden tavaroita huolellisesti koko muuton ajan.",
    ),
    "events": (
        r"tapahtumatyöntekijä|event worker",
        "I enjoy practical work where things can change quickly. I can switch between setup, helping guests, and supporting colleagues, while making sure the tasks I take on are finished.",
        "Pidän käytännön työstä, jossa tilanteet voivat muuttua nopeasti. Siirryn joustavasti valmisteluista vieraiden auttamiseen ja kollegoiden tukemiseen ja huolehdin, että ottamani tehtävät tulevat valmiiksi.",
    ),
    "outdoor": (
        r"ulkoalue|lumityöntekijä|snow clear",
        "I’m comfortable doing physical work outdoors and adapting when the weather or the day’s priorities change. I’d keep a steady pace and finish the areas assigned to me properly.",
        "Minulle sopii fyysinen ulkotyö, ja sopeudun sään sekä päivän tehtävien vaihteluun. Pitäisin tasaisen työtahdin ja hoitaisin minulle osoitetut alueet huolellisesti loppuun.",
    ),
    "vehicle_care": (
        r"rengasasentaja|autonpesijä|car washer",
        "I’m comfortable with hands-on work and learning the tools and products your team uses. I’d work at a steady pace, keep the work area in order, and check the finish before handing over a vehicle.",
        "Minulle sopii käytännön työ, ja opin mielelläni tiiminne käyttämät välineet ja tuotteet. Työskentelisin tasaisella tahdilla, pitäisin työpisteen järjestyksessä ja tarkistaisin työn jäljen ennen ajoneuvon luovutusta.",
    ),
    "delivery": (
        r"jakelij|muuttomies|delivery|mover",
        "I can adapt when the order or pace of deliveries changes. I’d check what is ready, handle the handover carefully, and keep the team informed if a delay needs attention.",
        "Sopeudun toimitusten järjestyksen ja työtahdin vaihteluun. Tarkistaisin toimitusten valmiuden, huolehtisin luovutuksesta ja ilmoittaisin tiimille ajoissa mahdollisista viiveistä.",
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
    role = role_for(job) if template == "auto" else template
    duties, actions = advertised_duties(job, finnish)
    ready = profile.get("available_immediately")
    if finnish:
        subject = f"Hakemus – {job.title}"
        greeting, signoff = "Hei,", "Ystävällisin terveisin,"
        opening = f"Haen ilmoittamaanne tehtävää ({job.title}). Olen ahkera ja luotettava työntekijä, joka pitää käytännön työstä ja tekee tehtävänsä huolellisesti."
        fit = (TEMPLATES[role][2] if role in TEMPLATES else
               "Tulen ajoissa, opin uudet työtavat nopeasti ja autan siellä, missä tiimi tarvitsee apua. Olen tottunut fyysiseen työhön ja kiireisiin vuoroihin ja hoidan aloittamani tehtävät huolellisesti loppuun.")
        if template == "general":
            opening = f"Haen ilmoittamaanne tehtävää ({job.title}). Etsin työtä, jonka voisin aloittaa pian, ja haluaisin ansaita tiiminne luottamuksen tekemällä työni hyvin ensimmäisestä vuorosta lähtien."
        elif actions and role not in {"warehouse", "food_service"}:
            fit += " " + actions[0][0].upper() + actions[0][1:] + "."
        passport = "Minulla on voimassa oleva suomalainen hygieniapassi."
        closing = ("Ansioluetteloni on liitteenä. Keskustelisin mielelläni siitä, miten voisin auttaa tiimiänne."
                   if template != "general" else
                   "Ansioluetteloni on liitteenä. Arvostaisin mahdollisuutta keskustella siitä, missä voisin olla tiimillenne avuksi.")
    else:
        subject = f"Application for {job.title}"
        greeting, signoff = "Hello,", "Best regards,"
        opening = f"I’m writing to apply for the {job.title} position. I’m a hardworking, reliable person who enjoys practical work and takes pride in doing it properly."
        fit = (TEMPLATES[role][1] if role in TEMPLATES else
               "I’m a reliable, hardworking person who shows up on time, learns new routines quickly, and helps where the team needs me. I’m comfortable with physical work and busy shifts, and I stick with a task until it’s done properly.")
        if template == "general":
            opening = f"I’m writing to apply for the {job.title} position. I’m looking for an opportunity to get started soon and would welcome the chance to earn your team’s trust by doing a good job from the first shift."
        elif actions and role not in {"warehouse", "food_service"}:
            fit += " I’d " + actions[0] + "."
        passport = "I hold a valid Finnish Hygiene Passport."
        closing = ("I’ve attached my CV and would be happy to discuss how I could help your team."
                   if template != "general" else
                   "I’ve attached my CV. I’d appreciate the chance to speak with you about where I could be useful to your team.")
    if name:
        subject += f" – {name}"
    if template != "general" and duties and role in {"warehouse", "food_service"}:
        fit += (f" Ilmoituksen mainitsemista tehtävistä minua kiinnostaa erityisesti {duties}." if finnish
                else f"I’d be glad to help with {duties}, as mentioned in your ad.")
    personal = [fit]
    if profile.get("hygiene_passport") and (
        match(PASSPORT, job.description) or
        (role_for(job) == "food_service" and match(AD_DUTIES[3][0], job.description))
    ):
        personal.append(passport)
    if profile.get("language_statement"):
        personal.append("Puhun sujuvasti englantia ja opiskelen suomea."
                        if finnish else "I speak fluent English and am actively learning Finnish.")
    if ready:
        personal.append("Asun Helsingissä ja voin aloittaa heti Helsingissä, Espoossa tai Vantaalla."
                        if finnish else "I’m based in Helsinki and available to start immediately in Helsinki, Espoo, or Vantaa.")
    signature = "\n".join(str(value).strip() for value in (
        signoff, name, profile.get("phone"), profile.get("email"), profile.get("location")
    ) if value and str(value).strip())
    return subject, "\n\n".join((greeting, opening, " ".join(personal), closing, signature))



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
