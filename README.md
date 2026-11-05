# Niroj JobFlow

A Windows job-search workspace for Helsinki, Espoo, and Vantaa. The dashboard runs locally and uses Python, SQLite, and Playwright.

## Open the dashboard

- Double-click **Open Niroj JobFlow.cmd** for the live workspace. Keep the launcher window open.
- Double-click **Preview Niroj JobFlow.cmd** for the sample workspace. The preview server disables email delivery.
- On a new computer, create a Python virtual environment named `venv`, install `requirements.txt`, and run `python -m playwright install chromium` from that environment.

## Collect and review

Use **Collect Jobs** to start a search, or choose automatic collection in **Settings**. When enabled, the running launcher checks every six hours. Bookmarks, the collected queue, and sent history live in SQLite.

The dashboard prioritizes vacancies with confirmed English. It keeps Finnish and unconfirmed-language listings available for review. Job Market Finland uses the existing detailed scraper. Duunitori, Jobly, Kuntarekry, Work in Finland, and optional StaffPoint use public search pages where accessible and route applicants to the original listing. Availability varies by source.

## Profile, drafts, and email

Use **My Profile** to open and reload the private profile. Keep the default CV in `cv`, and optionally add a `role_cvs` map such as `{"warehouse": "warehouse-cv.pdf"}`. A matching role CV takes precedence; otherwise the default CV is used. Use role experience fields only for verified experience. The profile and all CVs remain local.

Open **Draft Message** to choose a template and language, then review the selected emails and attachments before approving delivery. Gmail SMTP uses the existing environment setting if available, or the app password entered for that batch. JobFlow rechecks eligible listings and records each outcome. Portal-only listings open in the browser.

Run automated checks using `python -m unittest` from the virtual environment. Development checks use sample data or simulated delivery.


## Continuous collection

Click **Start Infinity** to scan the checked sources in parallel. JobFlow runs up to five source workers and starts another scan after a 15-minute pause. Click **Stop** to end continuous collection. In the launcher terminal, type **infinity** or **stop** and press Enter. Keep the launcher open while collecting.

For a listing without a verified application address, **Email this job** shows any addresses found in the published ad. Choose one or enter an address, then review and approve the message. You can review drafts while collection continues.
