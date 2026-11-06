"""Private, loopback-only Job Bot dashboard."""

import asyncio
import hashlib
import json
import os
import re
import sys
import secrets
import socket
import threading
import time
import webbrowser
from collections import Counter
from contextlib import closing
from dataclasses import asdict, replace
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from job_sources import SOURCES, discover
from job_decisions import assess, batch_recipient
import gmail_credentials
from review_app import CACHE, send_batch
from send_applications import (
    published_contacts, publication_timestamp,
    DIRECTORY, ENGLISH, SEARCH_QUERIES, TEMPLATES, Listing, match, canonical_url, draft, evaluate, history_status,
    cv_path, listing_deadline, load_profile, make_message, open_history, parse_listing, role_for, scrape, vacancy_key,
)


class JobFlowServer(ThreadingHTTPServer):
    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


DEFAULT_SOURCES = ("jmf", "jobly", "duunitori", "kuntarekry", "workinfinland")
INFINITY_INTERVAL = 15 * 60


class Dashboard:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.infinity_stop = threading.Event()
        self.infinity = False
        self.delivery_active = False
        self.mode = "idle"
        self.message = "Ready to collect"
        self.activity = []
        self.source_runs = {}
        self.source_retry = {}
        self.added = 0
        self.revision = 0
        self.jobs = {}
        self.rows = {}
        self.holds = {}
        self.saved = set()
        self.profile = load_profile()
        with closing(open_history()) as db:
            db.execute("CREATE TABLE IF NOT EXISTS collected_jobs (id TEXT PRIMARY KEY, listing TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS saved_jobs (id TEXT PRIMARY KEY)")
            db.execute("CREATE TABLE IF NOT EXISTS jobflow_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            preferences = dict(db.execute("SELECT key, value FROM jobflow_settings"))
            self.automatic = preferences.get("automatic", "0") == "1"
            self.gmail_sender = preferences.get("gmail_sender", "")
            self.gmail_saved = bool(gmail_credentials.get_password(self.gmail_sender))
            self.last_collection = float(preferences.get("last_collection", "0"))
            self.saved = {key for (key,) in db.execute("SELECT id FROM saved_jobs")}
            self.completed = {key for (key,) in db.execute(
                "SELECT vacancy FROM delivery_log WHERE state IN ('sent', 'applied online')")}
            self.completed.update(vacancy_key(url) for (url,) in db.execute(
                "SELECT url FROM processed_urls WHERE status = 'SENT'") if url)
            self.completed.update(vacancy_key(url) for (url,) in db.execute(
                "SELECT job_url FROM contacted_recipients WHERE job_url IS NOT NULL") if url)
            with db:
                for key in self.completed:
                    self.remove_from_queue(key, db)
            saved = list(db.execute("SELECT listing FROM collected_jobs"))
            for (entry,) in saved:
                self.add(Listing(**json.loads(entry)), db)
            if not saved and CACHE.is_file():
                for entry in json.loads(CACHE.read_text(encoding="utf-8")):
                    self.record(Listing(**entry), db)

    def set_preference(self, key, value):
        with closing(open_history()) as db, db:
            db.execute("INSERT OR REPLACE INTO jobflow_settings VALUES (?, ?)", (key, str(value)))

    def stop_collection(self):
        self.infinity_stop.set()
        self.stop.set()
        self.report("Stopping after the current page or listing group…")

    def terminal_commands(self):
        for line in sys.stdin:
            command = line.strip().casefold()
            if command not in {"", "collect", "scrape", "infinity", "stop"}:
                continue
            with self.lock:
                try:
                    if command == "stop":
                        self.stop_collection()
                    elif command in {"scrape", "infinity"}:
                        self.start_infinity({})
                    else:
                        self.collect({})
                except (ValueError, OSError) as error:
                    print(f"Collection could not start: {error}", flush=True)


    def schedule(self):
        while True:
            with self.lock:
                if self.automatic and not self.infinity and self.mode == "idle" and time.time() - self.last_collection >= 6 * 3600:
                    self.collect({})
            time.sleep(30)

    def bookmark(self, ids, saved):
        if not isinstance(ids, list) or not isinstance(saved, bool) or any(key not in self.jobs for key in ids):
            raise ValueError("Select jobs from the current queue.")
        with closing(open_history()) as db, db:
            statement = "INSERT OR IGNORE INTO saved_jobs VALUES (?)" if saved else "DELETE FROM saved_jobs WHERE id = ?"
            db.executemany(statement, ((key,) for key in ids))
        if saved:
            self.saved.update(ids)
        else:
            self.saved.difference_update(ids)
        self.revision += 1

    def remove_from_queue(self, key, db):
        db.execute("DELETE FROM collected_jobs WHERE id = ?", (key,))
        db.execute("DELETE FROM saved_jobs WHERE id = ?", (key,))
        self.jobs.pop(key, None)
        self.rows.pop(key, None)
        self.holds.pop(key, None)
        self.saved.discard(key)
        self.revision += 1

    def mark_applied(self, key):
        if self.mode != "idle" or key not in self.rows or self.rows[key]["status"] not in {"portal", "review"}:
            raise ValueError("This job cannot be marked as applied right now.")
        with closing(open_history()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM delivery_log WHERE vacancy = ?", (key,)).fetchone()
            if row:
                raise ValueError("This vacancy already has an application record.")
            db.execute("INSERT INTO delivery_log VALUES (?, 'applied online')", (key,))
            self.remove_from_queue(key, db)
        self.completed.add(key)

    def record(self, job, db):
        if vacancy_key(job.url) in self.completed:
            return False
        with db:
            db.execute("INSERT OR REPLACE INTO collected_jobs VALUES (?, ?)",
                       (vacancy_key(job.url), json.dumps(asdict(job), ensure_ascii=False)))
        self.add(job, db)
        return True

    def add(self, job, db):
        if canonical_url(job.url):
            parsed = parse_listing(job.url, job.title, job.description)
            if any(parsed.municipalities):
                job = replace(job, municipalities=parsed.municipalities)
        key = vacancy_key(job.url)
        self.jobs[key] = job
        external = job.source or next((label for label, base, _ in SOURCES.values()
                         if urlsplit(base).netloc == urlsplit(job.url).netloc), None)
        decision, reason, recipient = evaluate(job, self.profile)
        if external and reason != "The application deadline has passed.":
            decision, reason, recipient = "portal", "Check the worksite and apply on the source site", None
        english = any(value.casefold() in {"english", "englanti", "en"} for value in job.work_languages)
        english = english or match(ENGLISH, job.description)
        if recipient:
            previous = history_status(db, job, recipient)
            if previous or key in self.holds:
                decision = "sent" if previous == "sent" else "held"
                reason, recipient = previous or self.holds[key], None
        contract = "Part-time" if match(r"osa-aikatyö|part-time", job.description) else (
            "Full-time" if match(r"kokoaikatyö|full-time", job.description) else "")
        deadline = listing_deadline(job)
        row = {"category": role_for(job), "contract": contract, "deadline": deadline.strftime("%d.%m.%Y") if deadline else "",
               "id": key, "title": job.title, "url": job.url, "cities": job.municipalities,
               "languages": job.work_languages, "status": decision, "reason": reason, "english": english,
               "source": external or "Job Market Finland", "contact_count": len(published_contacts(job)),
               "published_at": job.published_at or publication_timestamp(job.description, job.source or external or "")}
        payload = json.dumps([asdict(job), self.profile], sort_keys=True, ensure_ascii=False)
        row["version"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        row["assessment"] = assess(job, self.profile, decision, reason, english)
        row["batch_recipient"] = batch_recipient(job, decision, recipient)
        row["deadline_days"] = (deadline - date.today()).days if deadline else None
        if decision == "portal":
            for line in job.application.splitlines():
                if line.startswith("Apply via the portal: "):
                    url = line.removeprefix("Apply via the portal: ").strip()
                    if urlsplit(url).scheme == "https" and urlsplit(url).netloc:
                        row["application_url"] = url
                        break
        if recipient:
            subject, body = draft(job, self.profile)
            row.update(recipient=recipient, subject=subject, body=body)
        self.rows[key] = row
        self.revision += 1

    def report(self, message):
        with self.lock:
            self.message = message
            self.activity = [message, *self.activity[:7]]
            if self.mode == "collection" or (self.infinity and self.mode == "idle"):
                print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

    def start(self, mode, target):
        if self.mode != "idle":
            raise ValueError("Another operation is in progress.")
        self.stop.clear()
        self.mode = mode
        self.report("Starting " + mode + "…")

        def work():
            try:
                target()
            except Exception as error:
                self.report(f"Operation stopped: {error}")
            finally:
                with self.lock:
                    self.mode = "idle"

        threading.Thread(target=work, daemon=True).start()

    def start_infinity(self, data):
        if self.infinity or self.mode != "idle":
            raise ValueError("Stop the current operation before starting Infinity mode.")
        self.infinity_stop.clear()
        self.infinity = True
        data = {**data}
        try:
            self.collect(data)
        except Exception:
            self.infinity = False
            raise

        def repeat():
            cycle = 0
            try:
                while not self.infinity_stop.wait(1):
                    with self.lock:
                        idle = self.mode == "idle"
                    if not idle:
                        continue
                    with self.lock:
                        self.report("Continuous scraping is waiting 15 minutes before the next scan.")
                    if self.infinity_stop.wait(INFINITY_INTERVAL):
                        break
                    cycle += 1
                    while not self.infinity_stop.is_set():
                        with self.lock:
                            if self.mode == "idle":
                                self.collect({**data, "_offset": cycle * 7})
                                break
                        self.infinity_stop.wait(1)
            except Exception as error:
                self.report(f"Infinity mode stopped: {error}")
            finally:
                with self.lock:
                    self.infinity = False

        threading.Thread(target=repeat, daemon=True).start()

    def collect(self, data):
        if self.mode != "idle":
            raise ValueError("A collection or delivery is already running.")
        terms = [item.strip() for item in data.get("query", "").split(",") if item.strip()]
        direct = [url for item in terms if (url := canonical_url(item))]
        queries = [item for item in terms if not canonical_url(item)]
        limit, pages = int(data.get("limit", 350)), int(data.get("pages", 3))
        if not 1 <= limit <= 1000 or not 1 <= pages <= 10:
            raise ValueError("Choose 1–1,000 listings and 1–10 pages per search.")
        self.added = 0

        selected_sources = data.get("sources", DEFAULT_SOURCES)
        if not selected_sources or any(source not in {"jmf", *SOURCES} for source in selected_sources):
            raise ValueError("Select at least one supported source.")

        labels = {"jmf": "Job Market Finland", **{key: value[0] for key, value in SOURCES.items()}}
        self.source_runs = {source: {"label": labels[source], "state": "Waiting", "saved": 0, "message": ""}
                            for source in selected_sources} if queries or not direct else {}

        async def gather():
            with closing(open_history()) as db:
                async def consume(stream, source=None):
                    async for job in stream:
                        with self.lock:
                            self.holds.pop(vacancy_key(job.url), None)
                            if self.record(job, db):
                                self.added += 1
                                if source:
                                    self.source_runs[source]["saved"] += 1
                                self.report(f"Saved {self.added} listings this run · {job.title}")

                if direct:
                    await consume(scrape([], limit, report=self.report, listing_urls=direct,
                                         cancelled=self.stop.is_set))
                if not queries and terms:
                    return self.report(f"Saved {self.added} listings to the database.")
                offset = data.get("_offset", 0) % len(SEARCH_QUERIES)
                ordered = SEARCH_QUERIES[offset:] + SEARCH_QUERIES[:offset]
                async def scan(source, allowance):
                    run = self.source_runs[source]
                    def progress(message):
                        with self.lock:
                            run["message"] = message
                            if "HTTP " in message:
                                run["state"] = "Unavailable"
                                if re.search(r"HTTP (?:403|429)\b", message):
                                    self.source_retry[source] = time.monotonic() + 3600
                            self.report(message)
                    with self.lock:
                        if self.infinity and time.monotonic() < self.source_retry.get(source, 0):
                            run["state"] = "Waiting to retry"
                            run["message"] = "The source refused or limited requests on the last scan."
                            return
                        run["state"] = "Collecting"
                    try:
                        if source == "jmf":
                            await consume(scrape(queries or ordered, allowance, report=progress,
                                                 max_pages=pages, cancelled=self.stop.is_set), source)
                        else:
                            await consume(discover(source, queries, pages, allowance, progress, self.stop.is_set), source)
                    except Exception as error:
                        progress(f"{labels[source]} · source interrupted: {type(error).__name__}")
                        with self.lock:
                            run["state"] = "Unavailable"
                    finally:
                        with self.lock:
                            if run["state"] != "Unavailable":
                                run["state"] = "Stopped" if self.stop.is_set() else "Finished"
                remaining = limit - self.added
                if remaining > 0 and not self.stop.is_set():
                    share, extra = divmod(remaining, len(selected_sources))
                    slots = asyncio.Semaphore(5)
                    async def run_source(source, allowance):
                        async with slots:
                            if not self.stop.is_set():
                                await scan(source, allowance)
                    await asyncio.gather(*(run_source(source, share + (index < extra))
                                           for index, source in enumerate(selected_sources)
                                           if share or index < extra))
            action = "Stopped after" if self.stop.is_set() else "Collection finished with"
            self.report(f"{action} {self.added} listings saved to SQLite.")

        self.start("collection", lambda: asyncio.run(gather()))
        self.last_collection = time.time()
        self.set_preference("last_collection", self.last_collection)

    def reload(self):
        if self.mode != "idle":
            raise ValueError("Wait for the current operation to finish.")
        self.profile = load_profile()
        with closing(open_history()) as db:
            for job in list(self.jobs.values()):
                self.add(job, db)
        self.report("Profile reloaded. Review your drafts again.")

    def save_gmail(self, data):
        sender = str(data.get("sender") or "").strip().casefold()
        password = "".join(str(data.get("password") or "").split())
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", sender) or not password:
            raise ValueError("Enter your Gmail address and Google app password.")
        old_sender = self.gmail_sender
        gmail_credentials.save_password(sender, password)
        self.set_preference("gmail_sender", sender)
        self.gmail_sender, self.gmail_saved = sender, True
        if old_sender and old_sender != sender:
            gmail_credentials.remove_password(old_sender)

    def forget_gmail(self):
        if self.gmail_sender:
            gmail_credentials.remove_password(self.gmail_sender)
        self.set_preference("gmail_sender", "")
        self.gmail_sender, self.gmail_saved = "", False

    def send(self, data):
        ids = data.get("ids")
        versions = data.get("versions")
        if versions is None and data.get("revision") != self.revision:
            raise ValueError("The queue changed. Review and select the drafts again.")
        if versions is not None and not isinstance(versions, dict):
            raise ValueError("Review the selected drafts again.")
        if self.delivery_active or self.mode == "delivery":
            raise ValueError("An email batch is already being sent.")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ValueError("Select one or more unique drafts.")
        sender = str(data.get("sender") or self.gmail_sender or self.profile.get("sender") or "").strip()
        saved_password = gmail_credentials.get_password(self.gmail_sender) if sender.casefold() == self.gmail_sender else None
        password = data.get("password") or saved_password or os.environ.get("JOBBOT_SMTP_PASSWORD")
        if not password:
            raise ValueError("Set up Gmail or enter your Gmail app password for this batch.")
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", sender):
            raise ValueError("Enter the Gmail address that owns the app password.")
        profile = {**self.profile, "sender": sender}
        selected = []
        choices = {}
        manual = data.get("manual", {})
        if not isinstance(manual, dict) or set(manual) - set(ids):
            raise ValueError("Invalid manually entered recipients.")
        manual_urls = set()
        local_batch = data.get("local_batch") is True
        for key in ids:
            row = self.rows.get(key, {})
            if versions is not None and versions.get(key) != row.get("version"):
                raise ValueError("A selected listing or your profile changed. Review it again.")
            if not row or (not local_batch and key not in manual and row.get("status") != "draft"):
                raise ValueError("One of the selected jobs is no longer available for this email.")
            job = self.jobs[key]
            recipient = row.get("recipient")
            if local_batch:
                recipient = batch_recipient(job, row["status"], recipient)
                if not recipient:
                    raise ValueError("A selected job has no confirmed local worksite and usable email. Reopen Email-ready batch.")
                if recipient != row.get("recipient"):
                    manual_urls.add(job.url)
            elif key in manual:
                recipient = str(manual[key]).strip().casefold()
                if recipient not in published_contacts(job):
                    raise ValueError("Choose a published address from this listing.")
                manual_urls.add(job.url)
            choice = data.get("choices", {}).get(key, {})
            choices[job.url] = (choice.get("template", "auto"), choice.get("language", "auto"))
            subject, body = draft(job, self.profile, *choices[job.url])
            selected.append((job, recipient, subject, body))
        for job, recipient, subject, body in selected:
            make_message(recipient, profile, subject, body, job)

        def deliver():
            results = send_batch(selected, profile, password, self.report, choices, manual_urls)
            with self.lock, closing(open_history()) as db:
                for job, *_ in selected:
                    key = vacancy_key(job.url)
                    outcome = results.get(job.url)
                    if outcome in {"sent", "already sent"}:
                        with db:
                            self.remove_from_queue(key, db)
                        self.completed.add(key)
                    else:
                        if outcome:
                            self.holds[key] = outcome
                        self.add(job, db)
                count = sum(value == "sent" for value in results.values())
                self.report(f"Sent {count} of {len(selected)}. Check the remaining row statuses.")

        if self.mode != "collection":
            self.start("delivery", deliver)
        else:
            self.delivery_active = True
            def deliver_while_collecting():
                try:
                    deliver()
                except Exception as error:
                    self.report(f"Delivery stopped: {error}")
                finally:
                    with self.lock:
                        self.delivery_active = False
            threading.Thread(target=deliver_while_collecting, daemon=True).start()


def serve(sample=False):
    dashboard = Dashboard()
    token = secrets.token_urlsafe(32)
    assets = {"/": ("dashboard.html", "text/html"), "/dashboard.js": ("dashboard.js", "text/javascript"),
              "/dashboard.css": ("dashboard.css", "text/css")}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, content, mime="application/json"):
            if mime == "application/json":
                content = json.dumps(content, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", f"{mime}; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def authorized(self):
            return self.headers.get("Host") == host and secrets.compare_digest(self.headers.get("X-JobBot-Token", ""), token)

        def do_GET(self):
            path = urlsplit(self.path).path
            if self.headers.get("Host") != host:
                return self.reply(403, {"error": "Open the local Job Bot address."})
            if path in assets:
                name, mime = assets[path]
                data = (DIRECTORY / name).read_bytes()
                if path == "/":
                    data = data.replace(b"__SESSION_TOKEN__", token.encode("ascii"))
                return self.reply(200, data, mime)
            if not self.authorized():
                return self.reply(403, {"error": "Reload the dashboard."})
            with dashboard.lock:
                if path == "/api/state":
                    revision = str(dashboard.revision)
                    return self.reply(200, {
                        "revision": dashboard.revision, "mode": dashboard.mode, "message": dashboard.message,
                        "infinity": dashboard.infinity, "delivery_active": dashboard.delivery_active,
                        "swarm_supported": not sample, "general_template": True,
                        "activity": dashboard.activity, "sources": list(dashboard.source_runs.values()), "added": dashboard.added, "completed": len(dashboard.completed),
                        "counts": Counter(row["status"] for row in dashboard.rows.values()),
                        "rows": list(dashboard.rows.values()) if self.path != f"/api/state?revision={revision}" else None,
                        "templates": list(TEMPLATES), "saved": sorted(dashboard.saved), "sender": dashboard.gmail_sender or dashboard.profile.get("sender", ""), "gmail_saved": dashboard.gmail_saved, "automatic": dashboard.automatic,
                    })
                if path == "/api/cvs":
                    paths = {"default": cv_path(dashboard.profile)}
                    paths.update({role: DIRECTORY / value for role, value in dashboard.profile.get("role_cvs", {}).items()})
                    return self.reply(200, [{"role": role, "name": path.name,
                                             "available": path.suffix.lower() == ".pdf" and path.is_file()}
                                            for role, path in paths.items()])
                if path == "/api/cv":
                    query = parse_qs(urlsplit(self.path).query)
                    job = dashboard.jobs.get(query.get("job", [""])[0])
                    role = query.get("role", ["default"])[0]
                    configured = dashboard.profile.get("role_cvs", {}).get(role)
                    cv = cv_path(dashboard.profile, job) if job or not configured else DIRECTORY / configured
                    if cv.suffix.lower() == ".pdf" and cv.is_file():
                        return self.reply(200, cv.read_bytes(), "application/pdf")
                    return self.reply(404, {"error": "The configured CV PDF could not be found."})
                if path == "/api/templates":
                    example = Listing("", "Example position", "", [], [], "")
                    return self.reply(200, {key: {lang: draft(example, dashboard.profile, key, lang) for lang in ("en", "fi")}
                                            for key in (*TEMPLATES, "general")})
                if path.startswith("/api/listing/"):
                    job = dashboard.jobs.get(unquote(path.removeprefix("/api/listing/")))
                    if job:
                        result = {"application": job.application, "description": job.description,
                                  "contacts": published_contacts(job)}
                        if job:
                            options = parse_qs(urlsplit(self.path).query)
                            template = options.get("template", ["auto"])[0]
                            language = options.get("language", ["auto"])[0]
                            try:
                                result["subject"], result["body"] = draft(job, dashboard.profile, template, language)
                                result["attachment"] = cv_path(dashboard.profile, job).name
                            except ValueError as error:
                                result["draft_error"] = str(error)
                        return self.reply(200, result)
            return self.reply(404, {"error": "Listing not found."})

        def do_POST(self):
            if not self.authorized() or self.headers.get("Origin") != f"http://{host}":
                return self.reply(403, {"error": "Open this action from the local dashboard."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= (1_000_000 if self.path == "/api/send" else 100_000):
                    raise ValueError("Invalid request size.")
                data = json.loads(self.rfile.read(length))
                with dashboard.lock:
                    if self.path in {"/api/collect", "/api/jobs/start"}:
                        dashboard.collect(data)
                    elif self.path in {"/api/infinity", "/api/jobs/swarm"} and not sample:
                        dashboard.start_infinity(data)
                    elif self.path == "/api/stop" and (dashboard.mode == "collection" or dashboard.infinity):
                        dashboard.stop_collection()
                    elif self.path == "/api/send" and not sample:
                        dashboard.send(data)
                    elif self.path == "/api/automatic" and not sample:
                        enabled = data.get("enabled")
                        if not isinstance(enabled, bool):
                            raise ValueError("Choose whether automatic collection is enabled.")
                        dashboard.set_preference("automatic", int(enabled))
                        dashboard.automatic = enabled
                    elif self.path == "/api/mark-applied" and not sample:
                        dashboard.mark_applied(data.get("id"))
                    elif self.path == "/api/bookmark":
                        dashboard.bookmark(data.get("ids"), data.get("saved"))
                    elif self.path == "/api/reload":
                        dashboard.reload()
                    elif self.path == "/api/gmail/save" and not sample:
                        dashboard.save_gmail(data)
                    elif self.path == "/api/gmail/forget" and not sample:
                        dashboard.forget_gmail()
                    elif self.path == "/api/profile":
                        path = DIRECTORY / "profile.json"
                        if not path.exists():
                            path.write_bytes((DIRECTORY / "profile.example.json").read_bytes())
                        os.startfile(path, "open")
                    else:
                        raise ValueError("This action is unavailable.")
                self.reply(200, {"ok": True, "revision": dashboard.revision})
            except (ValueError, TypeError, OSError) as error:
                self.reply(400, {"error": str(error)})

    port = 0 if sample else 8765
    try:
        server = JobFlowServer(("127.0.0.1", port), Handler)
    except OSError as error:
        if not sample and error.errno in {48, 98, 10013, 10048}:
            webbrowser.open(f"http://127.0.0.1:{port}")
            return
        raise
    with server:
        host = f"127.0.0.1:{server.server_port}"
        print(f"Niroj JobFlow is running at http://{host}.", flush=True)
        print("Keep this terminal open. Click Collect Jobs in the browser, or press Enter here. Type scrape to start continuous collection or stop to end it.", flush=True)
        if not sample:
            threading.Thread(target=dashboard.schedule, daemon=True).start()
            if sys.stdin.isatty():
                threading.Thread(target=dashboard.terminal_commands, daemon=True).start()
        webbrowser.open(f"http://{host}" + ("/?sample=1" if sample else ""))
        server.serve_forever()


if __name__ == "__main__":
    try:
        serve(sample="--sample" in sys.argv)
    except KeyboardInterrupt:
        pass
