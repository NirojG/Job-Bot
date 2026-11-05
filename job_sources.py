"""Public search indexes. External results use the source site's application route."""

import re
from urllib.parse import urlencode, urlsplit

from send_applications import CITIES, Listing, SEARCH_QUERIES, parse_listing

SOURCES = {
    "duunitori": ("Duunitori", "https://duunitori.fi/tyopaikat", 'a[href*="/tyopaikat/tyo/"]'),
    "jobly": ("Jobly", "https://www.jobly.fi/tyopaikat/helsinki-metropolitan-area", 'h2 a[href*="/tyopaikka/"], h2 a[href*="/job/"]'),
    "kuntarekry": ("Kuntarekry", "https://kuntarekry.fi/fi/tyopaikat/", 'main a[href*="/fi/tyopaikat/"]'),
    "workinfinland": ("Work in Finland", "https://www.workinfinland.com/en/open-jobs/", ""),
    "barona": ("Barona Careers", "https://www.baronacareers.com/fi/fi/job", 'a[href*="/jobs/"]'),
    "staffpoint": ("StaffPoint", "https://www.staffpoint.fi/tyopaikat", 'a[href*="/tyopaikat/"]'),
}
ROLES = re.compile(
    "|".join(re.escape(term) for term in SEARCH_QUERIES)
    + r"|varast|siivou|keräili|tarjoilij|kokki|logistiikka|trukki|kuljettaj|kiinteistöhuol|teollisu|ruokapalvelu|puhtaus|laitoshuol|warehouse|cleaning|production|cook|waiter|forklift|maintenance",
    re.I,
)


async def discover(source, terms, max_pages, limit, report, cancelled):
    from playwright.async_api import TimeoutError, async_playwright

    label, base, selector = SOURCES[source]
    seen = set()
    previous_links = set()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            detail = await browser.new_page() if source in {"jobly", "kuntarekry", "staffpoint"} else None
            def result_links():
                if source == "workinfinland":
                    return page.get_by_role("link", name="Go to job site", exact=True)
                return page.locator(selector)
            cities_to_search = sorted(CITIES)
            rounds = max_pages * (len(cities_to_search) if source == "duunitori" else 2 if source == "jobly" else 1)
            if source == "kuntarekry":
                rounds = min(max_pages + 2, 5)
            for number in range(1, rounds + 1):
                if cancelled() or len(seen) >= limit:
                    return
                city = cities_to_search[(number - 1) % len(cities_to_search)] if source == "duunitori" else None
                page_number = (number - 1) // len(cities_to_search) + 1 if city else number
                if source == "kuntarekry" and number <= len(cities_to_search):
                    city = cities_to_search[number - 1]
                    page_number = 1
                report(f"{label} · reading {city or 'results'} page {page_number}")
                if source in {"duunitori", "jobly", "kuntarekry"} or number == 1:
                    params = {"sivu": page_number, "alue": city}
                    if terms:
                        params["haku"] = ";".join(terms)
                    url = f"{base}?{urlencode(params)}" if source == "duunitori" else base
                    if source == "jobly":
                        index = (number - 1) // 2
                        seed = base if number % 2 == 0 else base.replace("/tyopaikat/", "/tyopaikat/kuljetus-ja-logistiikka/")
                        url = f"{seed}?{urlencode({'page': index})}"
                    if source == "kuntarekry":
                        if city:
                            url = f"https://kuntarekry.fi/fi/tyopaikat-sijainnin-mukaan/uusimaa/{city}/"
                        else:
                            category = ("ruokapalvelut", "siivous-ja-laitoshuolto")[number - 4]
                            url = f"https://kuntarekry.fi/fi/tyopaikat-tehtavan-mukaan/tekninen-ala/{category}/"
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    if not response or not response.ok:
                        report(f"{label} · search returned HTTP {response.status if response else 'unavailable'}")
                        return
                else:
                    next_page = page.get_by_role("button", name=re.compile(r"seuraava|next|näytä lisää|load more", re.I)).or_(
                        page.get_by_role("link", name=re.compile(r"seuraava|next", re.I))).first
                    if not await next_page.count() or not await next_page.is_enabled():
                        break
                    await next_page.click(timeout=4000)
                try:
                    await result_links().first.wait_for(state="attached", timeout=12000)
                except TimeoutError:
                    report(f"{label} · no new result links loaded")
                    if source in {"duunitori", "jobly", "kuntarekry"}:
                        continue
                    break
                records = await result_links().evaluate_all("""links => links.map(a => {
                    const card = a.querySelector("h2,h3,h4") ? a : (
                        a.closest("article, li, .job-box, .job-list-item, .views-row") || a.parentElement?.parentElement || a.parentElement || a
                    );
                    const heading = a.querySelector("h2,h3,h4") || a.closest("h2,h3,h4,h5") || card.querySelector("h2,h3,h4,h5");
                    return [a.href, (heading?.innerText || a.innerText || "").trim(), card.innerText || ""];
                })""")
                found_links = {href for href, _, _ in records}
                if found_links and found_links <= previous_links:
                    if source in {"duunitori", "jobly", "kuntarekry"}:
                        continue
                    break
                previous_links.update(found_links)
                for href, title, card in records:
                    if cancelled() or len(seen) >= limit:
                        return
                    parts = urlsplit(href)
                    if source == "kuntarekry":
                        slug = parts.path.rstrip("/").rsplit("/", 1)[-1]
                        title = slug.replace("-", " ")
                    if parts.scheme != "https" or not parts.netloc or not title or not ROLES.search(title):
                        continue
                    if source != "workinfinland" and parts.netloc.removeprefix("www.") != urlsplit(base).netloc.removeprefix("www."):
                        continue
                    if source == "kuntarekry" and not re.search(r"/fi/tyopaikat/[^/]+-[a-z0-9]+/?$", parts.path, re.I):
                        continue
                    if source == "staffpoint" and not re.search(r"-[A-Za-z0-9]{6}$", parts.path):
                        continue
                    if terms and not any(term.casefold() in (title + " " + card).casefold() for term in terms):
                        continue
                    cities = sorted(city.title() for city in CITIES if re.search(rf"\b{city}\b", card, re.I))
                    if not cities and city:
                        cities = [city.title()]
                    if not cities:
                        continue
                    clean = parts._replace(query="", fragment="").geturl()
                    if clean in seen:
                        continue
                    if detail:
                        try:
                            response = await detail.goto(clean, wait_until="domcontentloaded", timeout=10000)
                            if response and response.ok:
                                main = detail.locator("main").first
                                content = await main.inner_text(timeout=3500)
                                parsed = parse_listing(clean, title, content)
                                if source == "kuntarekry":
                                    heading = main.locator("h1").first
                                    if await heading.count():
                                        title = await heading.inner_text(timeout=2500)
                                hrefs = await main.locator('a[href^="mailto:"]').evaluate_all(
                                    "links => links.map(link => link.getAttribute('href'))")
                                card = content + "".join("\nPublished contact: " + urlsplit(href).path for href in hrefs)
                                application = parsed.application
                            else:
                                application = ""
                        except TimeoutError:
                            application = ""
                    else:
                        application = ""
                    if not cities:
                        continue
                    seen.add(clean)
                    yield Listing(clean, title.splitlines()[0], card, cities, [], application or
                                  f"Apply through the source listing on {label}. Confirm the worksite on the original posting.", label)
            report(f"{label} · {len(seen)} local blue-collar matches")
        finally:
            await browser.close()
