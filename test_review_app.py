import tempfile
import unittest
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from dashboard import Dashboard
from job_decisions import assess, batch_recipient
from review_app import send_batch
from send_applications import Listing, canonical_url, draft, evaluate, open_history, parse_listing, vacancy_key


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.job = Listing(
            "https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/warehouse",
            "Warehouse worker", "English is accepted.", ["Vantaa"], ["English"],
            "Send your application to jobs@employer.fi",
        )

    def test_current_listing_links_use_language_suffixes(self):
        link = self.job.url + "/fi"
        self.assertEqual(canonical_url(link + "?source=search"), link)
        self.assertEqual(vacancy_key(link), vacancy_key(self.job.url + "/en"))

    def test_portal_instruction_overrides_email_address(self):
        job = replace(self.job, application=self.job.application + "\nApply via our portal.")
        self.assertEqual(evaluate(job, {}), ("portal", "use the application portal listed by the employer", None))
        job = replace(self.job, description="Applications by email will not be accepted.")
        self.assertEqual(evaluate(job, {})[0], "portal")

    def test_mixed_multiline_worksite_is_held(self):
        job = parse_listing(self.job.url, self.job.title, """
            Sijainti: Helsinki
            Rovaniemi
            Työkieli: englanti
            Hakuohjeet: Lähetä hakemus osoitteeseen jobs@employer.fi
        """)
        self.assertEqual(evaluate(job, {})[0], "review")

    def test_bulk_email_uses_confirmed_local_worksite_and_ranks_contacts(self):
        job = replace(self.job, description=(
            "Location: Vantaa\nJob description\nRecruiter: hiring@example.org\n"
            "Send your application to applications@example.org\nPrivacy: privacy@example.org"
        ))
        self.assertEqual(batch_recipient(job, "portal"), "applications@example.org")
        for city in ("Rovaniemi", "Rauma", "Helsinki, Rauma"):
            outside = replace(job, description=job.description.replace("Vantaa", city))
            self.assertIsNone(batch_recipient(outside, "portal", "applications@example.org"))
        unconfirmed = replace(job, description="Recruiter: hiring@example.org")
        self.assertIsNone(batch_recipient(unconfirmed, "portal"))
        no_email = replace(job, description="Location: Espoo\nJob description\nPacking orders.",
                           application="Apply online")
        self.assertIsNone(batch_recipient(no_email, "portal"))

    def test_external_email_ready_excludes_uncertain_delivery_history(self):
        job = replace(self.job, source="Jobly", url="https://www.jobly.fi/job/warehouse",
                      description="Location: Vantaa\nJob description\nSend your application to jobs@employer.fi")
        key = vacancy_key(job.url)
        with tempfile.TemporaryDirectory() as directory, patch("send_applications.DIRECTORY", Path(directory)):
            dashboard = Dashboard()
            with closing(open_history()) as db, db:
                dashboard.add(job, db)
                self.assertEqual(dashboard.rows[key]["batch_recipient"], "jobs@employer.fi")
                db.execute("INSERT INTO contacted_recipients VALUES (?, NULL)", ("jobs@employer.fi",))
                dashboard.add(job, db)
                self.assertIsNone(dashboard.rows[key]["batch_recipient"])
                self.assertIn("legacy contact", dashboard.rows[key]["reason"])
                db.execute("INSERT INTO delivery_log VALUES (?, 'pending verification')", (key,))
                dashboard.add(job, db)
                self.assertIsNone(dashboard.rows[key]["batch_recipient"])
                self.assertEqual(dashboard.rows[key]["reason"], "pending verification")

    def test_recommends_clear_local_email_match(self):
        self.assertEqual(assess(self.job, {}, "draft", "", True)["fit"], "ready")
        self.assertEqual(assess(self.job, {}, "portal", "", True)["fit"], "online")
        self.assertEqual(assess(self.job, {}, "draft", "", False)["fit"], "check")

    def test_excludes_regulated_qualification_from_suggested_batch(self):
        job = replace(self.job, title="Personal assistant",
                      description="English is accepted. A nursing qualification recognised by Valvira is required.")
        assessment = assess(job, {}, "draft", "", True)
        self.assertEqual(assessment["fit"], "check")
        self.assertIn("Valvira", assessment["evidence"])

    def test_draft_adapts_to_advert_and_general_mode_stays_broad(self):
        job = replace(self.job, description="The shift includes order picking and packing.")
        _, tailored = draft(job, {})
        _, general = draft(job, {}, "general")
        _, finnish = draft(job, {}, "auto", "fi")
        self.assertIn("order picking and packing", tailored)
        self.assertIn("tilausten keräily ja pakkaaminen", finnish)
        self.assertIn("hardworking, reliable", tailored)
        self.assertIn("from the first shift", general)
        self.assertNotIn("worked", general)
        self.assertIn("switch between picking, packing", tailored)
        self.assertNotIn("order picking and packing", general)
    def test_changed_listing_never_opens_smtp(self):
        subject, body = draft(self.job, {})
        changed = replace(self.job, application="Apply via our portal.")
        with patch("review_app.recheck", new=AsyncMock(return_value={self.job.url: changed})):
            with patch("review_app.smtp_session") as smtp:
                result = send_batch([(self.job, "jobs@employer.fi", subject, body)], {}, "", lambda _: None)
        self.assertIn("changed", result[self.job.url])
        smtp.assert_not_called()

    def test_batch_sends_only_selected_and_records_vacancy(self):
        recipient = "jobs@employer.fi"
        subject, body = draft(self.job, {})
        other = replace(self.job, url=self.job.url + "-other")
        delivered = []

        class FakeSMTP:
            def send_message(self, message):
                delivered.append(message)

        @contextmanager
        def smtp(_sender, _password):
            yield FakeSMTP()

        with tempfile.TemporaryDirectory() as directory:
            profile = {"name": "Test Applicant", "sender": "person@example.org"}
            (Path(directory) / "cv.pdf").write_bytes(b"%PDF-test")
            subject, body = draft(self.job, profile)
            selection = [(self.job, recipient, subject, body)]
            with (
                patch("send_applications.DIRECTORY", Path(directory)),
                patch("review_app.recheck", new=AsyncMock(return_value={self.job.url: self.job, other.url: other})),
                patch("review_app.smtp_session", side_effect=smtp),
            ):
                result = send_batch(selection, profile, "test password", lambda _: None)
                second = send_batch(selection, profile, "test password", lambda _: None)
        self.assertEqual(result, {self.job.url: "sent"})
        self.assertEqual(second, {self.job.url: "already sent"})
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0]["To"], recipient)
        self.assertEqual(next(delivered[0].iter_attachments()).get_filename(), "cv.pdf")


if __name__ == "__main__":
    unittest.main()
