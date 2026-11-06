"""Local application review window. Collection never opens an email connection."""

import asyncio
import json
import os
import queue
import random
import shutil
import smtplib
import threading
import time
import tkinter as tk
import webbrowser
from contextlib import closing
from dataclasses import asdict
from tkinter import messagebox, simpledialog, ttk

from send_applications import (
    DIRECTORY, SEARCH_QUERIES, Listing, canonical_url, draft, evaluate, history_status,
    load_profile, make_message, open_history, scrape, send_reviewed, smtp_session, vacancy_key,
)

CACHE = DIRECTORY / "review_queue.local.json"
MIN_SEND_DELAY = 30
MAX_SEND_DELAY = 90


async def collect(queries, limit, report):
    urls = [canonical_url(query) for query in queries]
    direct = [url for url in urls if url]
    terms = [query for query, url in zip(queries, urls) if not url]
    jobs = [job async for job in scrape([], limit, report=report, listing_urls=direct)] if direct else []
    if terms and len(jobs) < limit:
        jobs.extend([job async for job in scrape(terms, limit - len(jobs), report=report)])
    return jobs


async def recheck(selected, report):
    urls = [job.url for job, _, _, _ in selected]
    return {job.url: job async for job in scrape([], len(urls), report=report, listing_urls=urls)}


def send_batch(selected, profile, password, report, choices=None, manual_urls=(), progress=None):
    choices = choices or {}
    verified = [item for item in selected if item[0].url not in manual_urls]
    current = asyncio.run(recheck(verified, report)) if verified else {}
    outcomes = {}
    ready = []
    for job, recipient, subject, body in selected:
        refreshed = current.get(job.url)
        if job.url not in manual_urls and (
            refreshed is None
            or refreshed.title != job.title
            or refreshed.application.split() != job.application.split()
            or refreshed.municipalities != job.municipalities
            or refreshed.work_languages != job.work_languages
            or evaluate(refreshed, profile)[2] != recipient
            or draft(refreshed, profile, *choices.get(job.url, ())) != (subject, body)
        ):
            outcomes[job.url] = "Listing changed or unavailable. Scrape again before sending."
            continue
        ready.append((job, recipient, make_message(recipient, profile, subject, body, job)))

    if not ready:
        return outcomes
    sent = 0
    total = len(ready)

    def update(state, processed, next_at=None):
        if progress:
            progress(state=state, total=total, processed=processed, sent=sent, next_at=next_at)

    update("connecting", 0)
    try:
        with smtp_session(profile["sender"], password) as server:
            for index, (job, recipient, message) in enumerate(ready, 1):
                update("sending", index - 1)
                report(f"Sending {index} of {total}")
                try:
                    outcomes[job.url] = send_reviewed(server, job, recipient, message)
                except Exception:
                    outcomes[job.url] = "Delivery interrupted. Check Gmail Sent and the queue status."
                    break
                if outcomes[job.url] == "sent":
                    sent += 1
                    if index < total:
                        delay = random.randint(MIN_SEND_DELAY, MAX_SEND_DELAY)
                        update("waiting", index, time.time() + delay)
                        report(f"Sent {sent} of {total}. Next application in {delay} seconds.")
                        time.sleep(delay)
                update("sending", index)
    except smtplib.SMTPAuthenticationError:
        connection_error = "Gmail rejected sign-in. Check the Gmail address and app password."
    except (OSError, smtplib.SMTPException):
        connection_error = "Could not complete the Gmail connection. Check your network and try again."
    else:
        connection_error = "Batch stopped before this email was attempted."
    for job, _, _ in ready:
        outcomes.setdefault(job.url, connection_error)
    return outcomes


class ReviewWindow:
    def __init__(self, root):
        self.root = root
        self.root.title("Job Bot – Application Review")
        self.root.geometry("1180x760")
        self.root.minsize(820, 530)
        self.events = queue.Queue()
        self.profile = {}
        self.jobs = {}
        self.checked = set()
        self.outcomes = {}
        self.rows = {}
        self.busy = False
        self.build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.profile = load_profile()
            if CACHE.is_file():
                self.jobs = {item["url"]: Listing(**item) for item in json.loads(CACHE.read_text(encoding="utf-8"))}
            self.refresh()
        except (ValueError, TypeError, KeyError, OSError) as error:
            messagebox.showerror("Could not load local files", str(error), parent=self.root)
        self.root.after(100, self.poll)

    def build(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="Search terms").pack(side="left")
        self.query = ttk.Entry(top, width=32)
        self.query.pack(side="left", padx=(6, 12), fill="x", expand=True)
        ttk.Label(top, text="Max listings").pack(side="left")
        self.limit = ttk.Spinbox(top, from_=1, to=500, width=5)
        self.limit.set("100")
        self.limit.pack(side="left", padx=6)
        self.collect_button = ttk.Button(top, text="Collect listings", command=self.start_collection)
        self.collect_button.pack(side="left", padx=4)
        ttk.Button(top, text="Open profile", command=self.open_profile).pack(side="left", padx=4)
        ttk.Button(top, text="Reload profile", command=self.reload_profile).pack(side="left", padx=4)

        split = ttk.Panedwindow(self.root, orient="vertical")
        split.pack(fill="both", expand=True, padx=10)
        list_frame = ttk.Frame(split)
        split.add(list_frame, weight=2)
        columns = ("checked", "status", "title", "city", "reason")
        self.table = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        for name, label, width in zip(columns, ("Send", "Status", "Job", "Worksite", "Reason"), (55, 105, 295, 135, 365)):
            self.table.heading(name, text=label)
            self.table.column(name, width=width, stretch=name in {"title", "reason"})
        self.table.tag_configure("Draft", foreground="#176134")
        self.table.tag_configure("Portal", foreground="#80510e")
        self.table.tag_configure("Sent", foreground="#315a8e")
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<ButtonRelease-1>", self.on_click)
        self.table.bind("<space>", self.on_space)
        self.table.bind("<<TreeviewSelect>>", self.show_details)

        details = ttk.Frame(split, padding=(0, 8, 0, 0))
        split.add(details, weight=1)
        ttk.Label(details, text="Application instructions and email preview").pack(anchor="w")
        self.preview = tk.Text(details, height=12, wrap="word", state="disabled", padx=8, pady=8)
        details_scroll = ttk.Scrollbar(details, orient="vertical", command=self.preview.yview)
        self.preview.configure(yscrollcommand=details_scroll.set)
        details_scroll.pack(side="right", fill="y")
        self.preview.pack(fill="both", expand=True)

        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Open original listing", command=self.open_listing).pack(side="left")
        ttk.Button(bottom, text="Clear checks", command=self.clear_checks).pack(side="left", padx=6)
        self.send_button = ttk.Button(bottom, text="Send checked (0)", command=self.start_send, state="disabled")
        self.send_button.pack(side="right")
        self.status = tk.StringVar(value="Enter search terms or listing URLs, separated by commas.")
        ttk.Label(bottom, textvariable=self.status).pack(side="left", padx=8)

    def refresh(self):
        selected = self.table.selection()
        self.table.delete(*self.table.get_children())
        self.rows.clear()
        with closing(open_history()) as db:
            for job in self.jobs.values():
                status, reason, recipient = evaluate(job, self.profile)
                label = status.title()
                if recipient:
                    previous = history_status(db, job, recipient)
                    if previous:
                        label = "Sent" if previous == "sent" else "Held"
                        reason, recipient = previous, None
                    elif job.url in self.outcomes:
                        reason = self.outcomes[job.url]
                        label, recipient = "Held", None
                self.rows[job.url] = recipient
                checked = "☑" if job.url in self.checked and recipient else "☐" if recipient else ""
                self.table.insert("", "end", iid=job.url, tags=(label,), values=(
                    checked, label, job.title, ", ".join(filter(None, job.municipalities)) or "Unknown", reason,
                ))
        self.checked.intersection_update(url for url, recipient in self.rows.items() if recipient)
        if selected and selected[0] in self.rows:
            self.table.selection_set(selected[0])
        self.show_details()
        self.update_buttons()

    def show_details(self, _event=None):
        selected = self.table.selection()
        text = "Select a listing to see its instructions and draft."
        if selected:
            job = self.jobs[selected[0]]
            text = f"{job.title}\n{job.url}\nWorksite: {', '.join(filter(None, job.municipalities)) or 'Unknown'}\n"
            text += f"Working languages: {', '.join(filter(None, job.work_languages)) or 'See listing'}\n"
            text += f"\nApplication instructions\n{job.application or 'No application instructions could be extracted.'}"
            recipient = self.rows.get(job.url)
            if recipient:
                subject, body = draft(job, self.profile)
                text += f"\n\nTo: {recipient}\nSubject: {subject}\n\n{body}"
            text += f"\n\nListing text\n{job.description}"
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def toggle(self, url):
        if self.busy or not self.rows.get(url):
            return
        if url in self.checked:
            self.checked.remove(url)
        else:
            self.checked.add(url)
        self.table.set(url, "checked", "☑" if url in self.checked else "☐")
        self.update_buttons()

    def on_click(self, event):
        if self.table.identify_column(event.x) == "#1":
            self.toggle(self.table.identify_row(event.y))

    def on_space(self, _event):
        if self.table.selection():
            self.toggle(self.table.selection()[0])
        return "break"

    def clear_checks(self):
        if not self.busy:
            for url in tuple(self.checked):
                self.toggle(url)

    def update_buttons(self):
        self.collect_button.configure(state="disabled" if self.busy else "normal")
        self.send_button.configure(text=f"Send checked ({len(self.checked)})",
                                   state="normal" if self.checked and not self.busy else "disabled")

    def open_listing(self):
        selected = self.table.selection()
        if selected and canonical_url(selected[0]):
            webbrowser.open(selected[0])

    def open_profile(self):
        path = DIRECTORY / "profile.json"
        try:
            if not path.exists():
                shutil.copyfile(DIRECTORY / "profile.example.json", path)
            os.startfile(path, "open")
        except OSError as error:
            messagebox.showerror("Could not open profile", str(error), parent=self.root)

    def reload_profile(self):
        if self.busy:
            return
        try:
            self.profile = load_profile()
            self.clear_checks()
            self.refresh()
            self.status.set("Profile reloaded. Review the updated drafts.")
        except (ValueError, OSError) as error:
            messagebox.showerror("Could not reload profile", str(error), parent=self.root)

    def start_collection(self):
        try:
            limit = int(self.limit.get())
            if not 1 <= limit <= 500:
                raise ValueError
        except ValueError:
            messagebox.showerror("Max listings", "Enter a number between 1 and 500.", parent=self.root)
            return
        queries = [query.strip() for query in self.query.get().split(",") if query.strip()]
        self.clear_checks()
        self.start_worker("collected", lambda report: asyncio.run(collect(queries or SEARCH_QUERIES, limit, report)))

    def start_send(self):
        selected = []
        try:
            for url in self.table.get_children():
                if url in self.checked:
                    job, recipient = self.jobs[url], self.rows[url]
                    subject, body = draft(job, self.profile)
                    make_message(recipient, self.profile, subject, body)
                    selected.append((job, recipient, subject, body))
        except (ValueError, OSError) as error:
            messagebox.showerror("Application setup", str(error), parent=self.root)
            return
        if not selected or not messagebox.askyesno(
            "Confirm applications",
            f"Recheck and send these {len(selected)} applications with your CV attached?",
            parent=self.root,
        ):
            return
        password = os.environ.get("JOBBOT_SMTP_PASSWORD") or simpledialog.askstring(
            "Gmail app password", "Enter your Gmail app password", show="*", parent=self.root,
        )
        if not password:
            return
        profile = self.profile
        self.start_worker("sent", lambda report: send_batch(selected, profile, password, report))

    def start_worker(self, event, work):
        self.busy = True
        self.update_buttons()
        self.status.set("Working…")

        def run():
            try:
                result = work(lambda message: self.events.put(("progress", message)))
            except Exception as error:
                self.events.put(("error", str(error)))
            else:
                self.events.put((event, result))

        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                event, result = self.events.get_nowait()
                if event == "progress":
                    self.status.set(result)
                    continue
                self.busy = False
                if event == "collected":
                    self.outcomes.clear()
                    for job in result:
                        for old_url in tuple(self.jobs):
                            if old_url != job.url and vacancy_key(old_url) == vacancy_key(job.url):
                                del self.jobs[old_url]
                        self.jobs[job.url] = job
                    try:
                        temporary = CACHE.with_suffix(".tmp")
                        temporary.write_text(json.dumps([asdict(job) for job in self.jobs.values()], ensure_ascii=False), encoding="utf-8")
                        temporary.replace(CACHE)
                    except OSError as error:
                        messagebox.showerror("Could not save the queue", str(error), parent=self.root)
                    self.status.set(f"Collected {len(result)} listings. {len(self.jobs)} in queue.")
                    self.refresh()
                elif event == "sent":
                    self.checked.clear()
                    self.outcomes.update(result)
                    sent = sum(status == "sent" for status in result.values())
                    self.status.set(f"Sent {sent} of {len(result)}. See row reasons for the rest.")
                    self.refresh()
                else:
                    self.status.set("Operation stopped. See the error.")
                    messagebox.showerror("Job Bot", result, parent=self.root)
                self.update_buttons()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Job Bot is working", "Wait for the current operation to finish.", parent=self.root)
        else:
            self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    ReviewWindow(window)
    window.mainloop()
