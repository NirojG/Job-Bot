# AI-Powered Job Application Assistant 

A Python project I built to automate some of the repetitive work involved in my own job search.

When I was applying for jobs around Helsinki, Espoo, and Vantaa, I noticed that a lot of the application process was repetitive. I was searching for similar jobs, opening listings one by one, checking if they were suitable, looking for a contact email, writing a short application, and sending my CV.

I wanted to see how much of this process I could automate with Python.

The result is a small job application assistant that searches **Työmarkkinatori**, filters the listings, finds contact emails, uses an LLM to write a short application message, and sends the application with my CV attached.

This is mainly a personal learning project where I experimented with browser automation, web scraping, APIs, email automation, and using an LLM as part of a normal Python workflow.

## How it works

The process is fairly simple:

```text
Työmarkkinatori
       │
       ▼
Search job listings
       │
       ▼
Open each listing
       │
       ▼
Python checks the job
       │
       ├── Outside Helsinki / Vantaa / Espoo → Skip
       │
       ├── Management / specialised role → Skip
       │
       ├── No direct email found → Skip
       │
       └── Already contacted → Skip
       │
       ▼
Groq + LLaMA 3
       │
       ▼
Generate a short application
       │
       ▼
Attach CV
       │
       ▼
Send through Gmail SMTP
       │
       ▼
Save email to sent_emails.txt
```

The filtering itself is mainly handled by Python. The LLM is used for the part where it makes sense: writing a short application based on the job listing and my background.

## Features

### 🔎 Job search and scraping

The project uses **Playwright** with Microsoft Edge to open Työmarkkinatori and search for specific types of jobs.

Some of the current search terms include:

* `varastotyöntekijä`
* `siivooja`
* `astianpesijä`
* `ravintolatyöntekijä`
* `hyllyttäjä`
* `tuotantotyöntekijä`
* `apumies`
* `lajittelija`
* `aputyöntekijä`
* `pakkaaja`
* `jakelija`
* `blokkari`

The searches are targeted at Helsinki, Vantaa, and Espoo.

### 🧹 Basic job filtering

Before an application is sent, the Python script checks the listing.

It skips jobs when:

* the location is outside the target area
* the role appears to be a management or specialised position
* no direct contact email can be found
* an application has already been sent to that email address

For example, roles containing terms such as `päällikkö`, `johtaja`, `asiantuntija`, `manager`, or `esimies` are filtered out.

This keeps the automation focused on the type of entry-level and practical jobs I was actually looking for.

### 🤖 LLM-generated applications

Once a suitable listing and contact email are found, the job title and part of the job description are sent to the **Groq API** using LLaMA 3.

The prompt also contains my relevant background, such as my Hygiene Passport and previous practical work experience.

The model then generates a short application message based on the particular job.

It can write the message in:

* 🇫🇮 Finnish when the listing is in Finnish
* 🇬🇧 English when the listing is in English

I intentionally keep the generated message short, usually around 3–4 sentences, because these are simple job applications rather than long cover letters.

### 📧 Automatic email sending

The application is sent through Gmail SMTP.

The email includes:

* The generated application message
* My contact details
* My PDF CV
* The job title in the subject
* A copy sent to myself for record keeping

The CV is attached automatically if the PDF file is available.

### 🛑 Duplicate prevention

The project keeps a local list of email addresses that have already been contacted:

```text
sent_emails.txt
```

After an application is successfully sent, the recipient's email is added to this file.

When the script finds another listing with the same email address, it skips it instead of sending another application.

## Tech Stack

| Technology         | Used for                             |
| ------------------ | ------------------------------------ |
| **Python**         | Main application                     |
| **Playwright**     | Browser automation and scraping      |
| **Groq API**       | Sending job information to the LLM   |
| **LLaMA 3**        | Generating application messages      |
| **smtplib**        | Gmail SMTP connection                |
| **email.mime**     | Creating emails and attaching the CV |
| **re**             | Extracting email addresses           |
| **Microsoft Edge** | Browser used by Playwright           |

## Project Structure

The main script handles the complete workflow:

```text
Job-Bot/
│
├── send_applications.py
├── cv.pdf
├── sent_emails.txt
├── requirements.txt
└── README.md
```

`send_applications.py` contains the search, filtering, LLM, email, and duplicate-prevention logic.

## Running it locally

### 1. Clone the repository

```bash
git clone https://github.com/NirojG/Job-Bot.git
cd Job-Bot
```

### 2. Install the Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright

```bash
playwright install
```

### 4. Add your CV

Place your CV in the project folder:

```text
cv.pdf
```

### 5. Run the script

```bash
python send_applications.py
```

The script will ask for:

* Your Google App Password
* Your Groq API key

The browser then opens and starts processing the job searches.

> **Important:** Do not put your API keys, Google App Password, or other private credentials directly into the repository.

## A little more about the project

I didn't start this project because I wanted to build a big recruitment platform.

I built it because I was doing the same things again and again while applying for jobs and thought there had to be a better way.

It also gave me a good opportunity to learn how different parts of an application can work together. Playwright handles the browser, Python handles the logic and filtering, Groq handles the text generation, and SMTP handles the actual email sending.

For me, the interesting part was not just using an LLM. It was putting it into a workflow where it actually solved a small problem.

## ⚠️ Note

This is a personal project and was built for experimentation and learning.

Automated job applications can contain mistakes, so generated messages and selected listings should be checked before relying on them. Website structures and policies can also change, which may require updates to the scraper.
