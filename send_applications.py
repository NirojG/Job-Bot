import asyncio
import os
import smtplib
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from playwright.async_api import async_playwright
from groq import Groq

# --- APPLICANT CONFIGURATION ---
SENDER_EMAIL = "Place your email here"
APPLICANT_NAME = "Your name"
APPLICANT_PHONE = "+358 41 444 444"
APPLICANT_EMAIL = "place email"
PDF_CV_PATH = "cv.pdf"
SENT_EMAILS_FILE = "sent_emails.txt"


def load_sent_emails():
    """Loads previously contacted emails to prevent duplicate sending."""
    if not os.path.exists(SENT_EMAILS_FILE):
        return set()
    with open(SENT_EMAILS_FILE, "r") as f:
        return set(line.strip().lower() for line in f if line.strip())

def mark_email_as_sent(email):
    """Saves the contacted email to the tracking file."""
    with open(SENT_EMAILS_FILE, "a") as f:
        f.write(f"{email.lower()}\n")

def generate_tailored_cover_letter(groq_client, job_title, page_text):
    """Uses Groq to write a highly natural, human-sounding email for blue-collar roles."""
    prompt = f"""
You are {APPLICANT_NAME}, applying for the position of {job_title}. 
Job Listing Details: {page_text[:2000]}

Your Profile:
- You hold a valid Finnish Hygiene Passport (Hygieniapassi).
- You have practical, hands-on experience working as a cleaner, kitchen hand, factory worker, and farm assistant.
- You are a hard worker, fast learner, and ready for physical or entry-level tasks requiring minimal training.
- You live in Helsinki and are ready to start immediately in Helsinki, Vantaa, or Espoo.

Task:
Write a short, natural, human-sounding email (3-4 sentences max) to apply for this job.
- If the job is in Finnish, write in simple, polite Finnish. If English, write in natural English.
- Do NOT sound like an AI or a corporate executive. Sound like a reliable, eager worker applying for a practical job.
- ONLY mention the specific experience from your profile that matches this job (e.g., mention the hygiene pass and kitchen work if it's a restaurant job; mention factory work if it's a warehouse job).
- Do NOT include subject lines, "Dear Hiring Manager", or sign-offs like "Best regards". Just provide the body of the email.
"""
    try:
        response = groq_client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"⚠️ Groq API error: {e}. Falling back to default letter.")
        return (
            f"I am writing to express my strong interest in the {job_title} role. "
            f"I am a hardworking, reliable person with practical hands-on experience, "
            f"and I am ready to start working immediately in the Helsinki, Vantaa, or Espoo area."
        )


def send_job_email_with_pdf(recipient_email, job_title, cover_letter_text, app_pass):
    try:
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = recipient_email
        msg['Cc'] = SENDER_EMAIL
        msg['Subject'] = f"Työhakemus: {job_title} - {APPLICANT_NAME}"

        body = f"""Hei / Hello,

{cover_letter_text}

I have attached my CV to this email for more details. 

---
Yhteystiedot / Contact Details:
Name: {APPLICANT_NAME}
Email: {APPLICANT_EMAIL}
Phone: {APPLICANT_PHONE}
Location: Helsinki
"""
        msg.attach(MIMEText(body, 'plain'))

        if os.path.exists(PDF_CV_PATH):
            with open(PDF_CV_PATH, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
            encoders.encode_base64(part)

            clean_filename = f"{APPLICANT_NAME.replace(' ', '_')}_CV.pdf"
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={clean_filename}",
            )
            msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, app_pass)

        recipients = [recipient_email, SENDER_EMAIL]
        server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
        server.quit()
        print(f"✅ Successfully sent: '{job_title}' to {recipient_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False


async def main():
    app_pass = input("Enter your 16-character Google App Password: ").strip().replace(" ", "")
    if not app_pass:
        print("Error: App password cannot be empty.")
        return

    groq_api_key = input("Enter your Groq API Key (gsk_...): ").strip()
    if not groq_api_key:
        print("Error: Groq API key cannot be empty.")
        return

    groq_client = Groq(api_key=groq_api_key)
    sent_emails_history = load_sent_emails()

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=False, slow_mo=50)
        page = await browser.new_page()

        search_queries = [
            "varastotyöntekijä", "siivooja", "astianpesijä", "ravintolatyöntekijä", 
            "hyllyttäjä", "tuotantotyöntekijä", "apumies", "lajittelija", 
            "aputyöntekijä", "pakkaaja", "jakelija", "blokkari"
        ]
        
        sent_count = 0
        target_limit = 50

        for query in search_queries:
            if sent_count >= target_limit:
                break

            search_url = f"https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat?q={query}&municipality=091&municipality=092&municipality=049"
            print(f"\n🔍 Searching category: '{query}' in Helsinki, Vantaa, Espoo...")

            try:
                await page.goto(search_url)
                await page.wait_for_timeout(4000)
            except Exception:
                continue

            job_cards = await page.locator("a[href*='/avoimet-tyopaikat/']").all()
            print(f"Found {len(job_cards)} listings for '{query}'. Processing...")

            for i in range(len(job_cards)):
                if sent_count >= target_limit:
                    break

                try:
                    cards = await page.locator("a[href*='/avoimet-tyopaikat/']").all()
                    if i >= len(cards):
                        break

                    await cards[i].click()
                    await page.wait_for_timeout(2500)

                    try:
                        job_title_elem = page.locator("h1").first
                        job_title = await job_title_elem.inner_text()
                    except Exception:
                        job_title = f"{query.capitalize()} Role"

                    page_text = await page.inner_text("body")

                    # Location filter
                    has_location = any(city in page_text for city in ["Helsinki", "Vantaa", "Espoo"])
                    if not has_location:
                        print(f"⏭️ [{sent_count}/{target_limit}] Skipping: Outside target region.")
                        await page.go_back()
                        await page.wait_for_timeout(1500)
                        continue

                    # Strict filtering against supervisory or specialized roles
                    is_blue_collar = not any(word in page_text.lower() for word in ["päällikkö", "johtaja", "asiantuntija", "manager", "esimies"])
                    if not is_blue_collar:
                        print(f"⏭️ [{sent_count}/{target_limit}] Skipping: Role requires advanced/specialized experience.")
                        await page.go_back()
                        await page.wait_for_timeout(1500)
                        continue

                    # Email scraper
                    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", page_text)
                    valid_emails = [
                        e for e in emails 
                        if "tyomarkkinatori" not in e.lower() 
                        and "example" not in e.lower() 
                        and "support" not in e.lower()
                    ]

                    if valid_emails:
                        target_email = valid_emails[0].lower()
                        
                        # PREVENT DUPLICATES
                        if target_email in sent_emails_history:
                            print(f"⏭️ [{sent_count}/{target_limit}] Skipping: Already sent an application to {target_email}")
                            await page.go_back()
                            await page.wait_for_timeout(1500)
                            continue

                        print(f"🎯 [{sent_count+1}/{target_limit}] Email found: {target_email} | Job: {job_title}")
                        
                        print("🤖 Generating human-like AI cover letter with Groq...")
                        cover_letter = generate_tailored_cover_letter(groq_client, job_title, page_text)

                        success = send_job_email_with_pdf(target_email, job_title, cover_letter, app_pass)
                        if success:
                            sent_count += 1
                            sent_emails_history.add(target_email)
                            mark_email_as_sent(target_email)
                            print(f"🔥 Milestone: {sent_count}/{target_limit} applications sent!")
                    else:
                        print(f"⏭️ [{sent_count}/{target_limit}] No direct email found, skipping.")

                    await page.go_back()
                    await page.wait_for_timeout(1500)

                except Exception as e:
                    print(f"⚠️ Error on card {i}: {e}")
                    try:
                        await page.goto(search_url)
                        await page.wait_for_timeout(2000)
                    except Exception:
                        pass

        print(f"\n🎉 Finished! Successfully sent {sent_count} direct applications.")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())