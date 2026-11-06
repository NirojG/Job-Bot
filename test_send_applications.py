import unittest

from datetime import datetime, timezone

from send_applications import Listing, draft, evaluate, parse_listing, publication_timestamp, vacancy_key


class ApplicationTests(unittest.TestCase):
    def test_publication_timestamp_uses_helsinki_time(self):
        utc = datetime(2026, 11, 5, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(publication_timestamp("Hakuaika päättyy 15.11.2026 (julkaistu 5.11.2026 klo 15.30)"),
                         utc.timestamp())

    def test_publication_timestamp_uses_only_known_dates(self):
        midnight = datetime(2026, 11, 4, 22, tzinfo=timezone.utc)
        self.assertEqual(publication_timestamp("Warehouse worker\n05.11.2026, Employer", "Jobly"),
                         midnight.timestamp())
        self.assertIsNone(publication_timestamp("Deadline 5.11.2026"))
        self.assertIsNone(publication_timestamp("Published 31.02.2026"))

    def listing(self, **overrides):
        values = {
            "url": "https://tyomarkkinatori.fi/henkiloasiakkaat/avoimet-tyopaikat/example",
            "title": "Warehouse worker",
            "description": "Työkieli on englanti. Suomen kielen perustaidot.",
            "municipalities": ["Vantaa"],
            "work_languages": [],
            "application": "Send your application to jobs@employer.fi",
        }
        values.update(overrides)
        return Listing(**values)

    def test_worksite_overrides_company_location(self):
        job = self.listing(municipalities=["Tampere"], description="Our office is in Helsinki.")
        self.assertEqual(evaluate(job, {})[0], "skip")
        self.assertEqual(evaluate(self.listing(municipalities=["Espoo", "Tampere"]), {})[0], "review")

    def test_bilingual_ad_gets_an_english_draft_without_passport(self):
        job = self.listing()
        profile = {"hygiene_passport": True}
        self.assertEqual(evaluate(job, profile)[0], "draft")
        subject, body = draft(job, profile)
        self.assertTrue(subject.startswith("Application"))
        self.assertNotIn("Passport", body)

    def test_fluent_finnish_requirement(self):
        job = self.listing(description="Working language is English. Fluent Finnish required.")
        self.assertEqual(evaluate(job, {})[0], "skip")

    def test_contact_email_is_not_an_application_address(self):
        job = self.listing(application="Questions: recruiter@employer.fi")
        self.assertEqual(evaluate(job, {})[0], "review")

    def test_explicit_finnish_email_and_relevant_passport(self):
        job = self.listing(description="English is accepted. Hygieniapassi.",
                           application="Lähetä hakemus suomeksi: jobs@employer.fi")
        subject, body = draft(job, {"hygiene_passport": True})
        self.assertTrue(subject.startswith("Hakemus"))
        self.assertIn("hygieniapassi", body)

    def test_structured_fields(self):
        job = parse_listing(self.listing().url, "Warehouse worker", """
            Sijainti
            Vantaa
            Työkieli: englanti
            Hakuohjeet
            Send your application to jobs@employer.fi
            Yhteystiedot
            Send your application questions to other@employer.fi
        """)
        self.assertEqual(evaluate(job, {})[2], "jobs@employer.fi")

    def test_vacancy_id_is_stable_across_slugs(self):
        identifier = "abcdef12-1234-5678-1234-abcdef123456"
        self.assertEqual(vacancy_key(f"https://example.test/new-title-{identifier}?foo=bar"), identifier)


if __name__ == "__main__":
    unittest.main()
