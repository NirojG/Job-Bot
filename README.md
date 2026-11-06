# Niroj JobFlow

JobFlow is a local Windows dashboard for finding and reviewing practical jobs in Helsinki, Espoo, and Vantaa. It collects public listings, shows their application instructions and published contacts, and prepares English or Finnish email drafts. Email delivery starts after you review and approve the batch.

## Quick start

Install Python 3.10 or newer. From the repository folder, run these commands in PowerShell.

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m playwright install chromium
Copy-Item profile.example.json profile.json
```

1. Add your name and CV path to the local `profile.json`. If you use the default path, put your PDF in this folder as `cv.pdf`.
2. Double-click **Preview Niroj JobFlow.cmd** to try the workflow with sample vacancies and email delivery disabled.
3. Double-click **Open Niroj JobFlow.cmd** for the live dashboard. It opens the browser at `http://127.0.0.1:8765/`. Keep the terminal open.

## Collect and review jobs

- **Collect Jobs** runs one scan. **Scrape Jobs** starts continuous collection with up to five source workers. JobFlow pauses 15 minutes between scans. **Stop** ends the run after the current group finishes.
- The default sources are Työmarkkinatori, Jobly, Duunitori, Kuntarekry, and Work in Finland. StaffPoint is optional. Coverage varies by source, and the dashboard reports each worker's result.
- Filter by location, language, category, or published email. **Last 24 hours** shows jobs whose publication date places them in that window and switches to **Newest first**. Listings without a publication date stay in the full queue. **Saved Jobs** keeps bookmarks. A source may return no relevant ads even when the collector runs successfully.
- Open **Draft Message** to review a role-specific draft or **Email Templates** to browse examples in English and Finnish. The draft uses the vacancy's role and advertised duties.
- **Ready to apply** ranks suggested drafts by language fit, publication time, and deadline. It uses verified application emails and leaves uncertain qualifications for review. Check the reasons on individual listings and approve the batch yourself.
- **Email-ready batch** uses confirmed Helsinki, Espoo, and Vantaa worksites and picks one published recruiting address per job. Review the batch together, expand individual drafts if needed, and send from the top of the review.
- **Desperate Mode** gathers available jobs with published addresses into one review using the general template. Check recipients and uncheck jobs you want to skip before approving.
- For a portal application, follow the employer's instructions and use **Mark as applied** once you've submitted it. Completed vacancies leave the active queue, and SQLite keeps a completion record to help prevent duplicate applications.

## Profile and Gmail

Set these values in your private `profile.json` only if they apply.

| Field | Purpose |
|---|---|
| `name`, `phone`, `email`, `location` | Signature details. |
| `cv`, `role_cvs` | Default PDF and optional role-specific PDFs, such as `{"warehouse": "warehouse-cv.pdf"}`. |
| `hygiene_passport` | A valid Finnish Hygiene Passport. JobFlow includes it when the listing mentions it or a food-service ad clearly describes food preparation. |
| `language_statement` | Opt in to the statement about fluent English and learning Finnish. |
| `available_immediately` | Opt in to the statement about starting immediately in Helsinki, Espoo, or Vantaa. |
| `sender` | Optional Gmail sender address. You can also enter it at batch review. |

Use **Gmail Setup** to save your account once in Windows Credential Manager, or enter the Gmail address and app password for a single batch. Use **Forget saved Gmail** to remove the saved password. The app also supports the local `JOBBOT_SMTP_PASSWORD` environment variable. Keep the password, CVs, profile, database, and sent-email history outside Git. The repository includes a blank example profile.

## Project layout

| File | Responsibility |
|---|---|
| `dashboard.py` | Local web server, source scheduling, queue, and approval endpoints. |
| `dashboard.html`, `dashboard.css`, `dashboard.js` | Dashboard, templates, and batch review. |
| `send_applications.py` | Työmarkkinatori scraping, listing checks, draft generation, and Gmail SMTP. |
| `job_sources.py` | Adapters for the other job boards. |
| `review_app.py` | Batch delivery, listing rechecks, and the earlier desktop review interface. |
| `test_*.py` | Regression tests with simulated delivery. |

## Tests

```powershell
.\venv\Scripts\python.exe -m unittest discover -v
```

If a new control appears but the old launcher is still running, stop collection, close the terminal, and reopen the launcher. If collection fails for one source, check the worker status and terminal for its result.
