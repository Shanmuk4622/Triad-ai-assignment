import json
import unittest
from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

from dms import create_app


def scanned_document(kind="PDF"):
    image = Image.new("RGB", (1050, 175), "white")
    ImageDraw.Draw(image).text((35, 40), "Orchid Voucher 2026", font=ImageFont.load_default(size=66), fill="black")
    buffer = BytesIO()
    image.save(buffer, format=kind)
    return buffer.getvalue()


class DocumentSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Always use a disposable database, including when run inside Docker Compose.
        cls.app = create_app({"TESTING": True, "MONGO_DB": f"triad_test_{uuid4().hex}"})
        cls.db = cls.app.extensions["db"]
        cls.addClassCleanup(cls.db.client.close)
        cls.addClassCleanup(cls.db.client.drop_database, cls.db.name)
        cls.client = cls.app.test_client()
        cls.a = cls.account("alice", "Division A")
        cls.a_member = cls.account("amy", "Division A")
        cls.b = cls.account("ben", "Division B")
        cls.b_member = cls.account("bob", "Division B")
        cls.c = cls.account("cara", "Division C")
        result = cls.app.test_cli_runner().invoke(args=["make-admin", "alice"])
        if result.exit_code != 0:
            raise RuntimeError(result.output)

    @classmethod
    def account(cls, name, division):
        payload = {"username": name, "email": f"{name}@example.test", "password": "secure1234", "division": division, "role": "admin"}
        response = cls.client.post("/api/auth/register", json=payload)
        if response.status_code != 201 or response.json["user"]["role"] != "member":
            raise RuntimeError(response.json)
        response = cls.client.post("/api/auth/login", json={"email": payload["email"], "password": payload["password"]})
        return {"Authorization": f"Bearer {response.json['token']}"}

    def upload(self, headers, title="Finance record", fields=None, payload=None, suffix="pdf", **form_fields):
        fields = fields if fields is not None else {"Report Type": "Financial", "Period": ["Q3", "2026"]}
        payload = payload if payload is not None else scanned_document()
        return self.client.post("/api/documents/upload", headers=headers, data={
            "title": title, "file": (BytesIO(payload), f"scan.{suffix}"),
            "metadata": json.dumps(fields), **form_fields,
        })

    def new_document(self, **kwargs):
        response = self.upload(self.a, **kwargs)
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["doc_id"]

    def ask(self, document_id, headers=None):
        return self.client.post("/api/access/request", headers=headers or self.b, json={"doc_id": document_id})

    def test_auth_and_page(self):
        self.assertIn(b"Upload document", self.client.get("/").data)
        self.assertEqual(self.client.get("/api/health").json, {"status": "ok"})
        self.assertEqual(self.client.get("/api/documents").status_code, 401)
        self.assertEqual(self.client.get("/api/documents", headers={"Authorization": "Bearer invalid"}).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.a).json["user"]["role"], "admin")
        self.assertEqual(self.client.get("/api/auth/me", headers=self.b).json["user"]["role"], "member")
        wrong = self.client.post("/api/auth/login", json={"username": "alice", "password": "incorrect"})
        self.assertEqual(wrong.status_code, 401)

    def test_gridfs_metadata_filter_and_same_division_download(self):
        payload = scanned_document()
        doc_id = self.new_document(payload=payload)
        self.assertGreater(self.db.fs.chunks.count_documents({}), 0)
        listing = self.client.get("/api/documents", headers=self.a_member, query_string={"Report Type": "financial", "Period": "Q3", "Division": "division a"})
        match = next(doc for doc in listing.json["documents"] if doc["id"] == doc_id)
        self.assertEqual(match["metadata"], {"Report Type": "Financial", "Period": ["Q3", "2026"]})
        file = self.client.get(f"/api/documents/{doc_id}/download", headers=self.a_member)
        self.assertEqual(file.status_code, 200)
        self.assertEqual(file.data, payload)
        self.assertIn("attachment", file.headers["Content-Disposition"])

    def test_cross_division_upload_is_blocked(self):
        self.assertEqual(self.upload(self.a, Division="Division B").status_code, 403)
        self.assertEqual(self.upload(self.b, fields={"Division": "Division A"}).status_code, 403)
        response = self.upload(self.a, fields={"Division": "division a"})
        self.assertEqual(response.json["document"]["metadata"]["Division"], "Division A")

    def test_scanned_pdf_and_image_are_searchable(self):
        pdf_id = self.new_document(title="First attachment", fields={})
        image_id = self.new_document(title="Second attachment", fields={}, payload=scanned_document("PNG"), suffix="png")
        response = self.client.get("/api/search", query_string={"q": "Orchid Voucher"}, headers=self.a)
        self.assertEqual(response.status_code, 200)
        self.assertTrue({pdf_id, image_id}.issubset(doc["id"] for doc in response.json["results"]))
        self.assertTrue(all("ocr_text" not in doc for doc in response.json["results"]))

    def test_search_title_and_metadata(self):
        doc_id = self.new_document(title="Operations alpha", fields={"Units": "Violet"})
        for term in ["operations alpha", "Violet", "Units"]:
            with self.subTest(term=term):
                response = self.client.get("/api/search", query_string={"q": term}, headers=self.a)
                self.assertIn(doc_id, [doc["id"] for doc in response.json["results"]])

    def test_cross_division_approval_is_per_person_and_document(self):
        doc_id = self.new_document(title="Restricted report")
        other_id = self.new_document(title="Another report")
        detail = f"/api/documents/{doc_id}"
        listing = self.client.get("/api/documents", headers=self.b)
        self.assertNotIn(doc_id, [doc["id"] for doc in listing.json["documents"]])
        catalog = self.client.get("/api/documents/catalog", headers=self.b).json["documents"]
        item = next(doc for doc in catalog if doc["id"] == doc_id)
        self.assertEqual(set(item), {"id", "title", "division", "access_status"})
        self.assertNotIn("metadata", self.client.get(detail, headers=self.b).json["document"])
        self.assertEqual(self.client.get(f"{detail}/download", headers=self.b).status_code, 403)
        self.assertFalse(self.client.get("/api/search?q=Orchid", headers=self.b).json["results"])

        request = self.ask(doc_id)
        self.assertEqual(request.status_code, 201)
        req_id = request.json["request_id"]
        self.assertEqual(self.ask(doc_id).json["request_id"], req_id)
        self.assertFalse(self.client.get("/api/access/requests", headers=self.b).json["requests"])
        inbox = self.client.get("/api/access/requests", headers=self.a_member).json["requests"]
        self.assertIn(req_id, [item["id"] for item in inbox])
        approval = {"request_id": req_id}
        self.assertEqual(self.client.post("/api/access/approve", headers=self.c, json=approval).status_code, 403)
        self.assertEqual(self.client.post("/api/access/approve", headers=self.a_member, json=approval).json["status"], "approved")
        self.assertEqual(self.client.get(f"{detail}/download", headers=self.b).status_code, 200)
        self.assertEqual(self.client.get(f"{detail}/download", headers=self.b_member).status_code, 403)
        self.assertEqual(self.client.get(f"/api/documents/{other_id}/download", headers=self.b).status_code, 403)
        search = self.client.get("/api/search?q=Orchid", headers=self.b).json["results"]
        self.assertEqual([doc["id"] for doc in search], [doc_id])

    def test_rejected_request_does_not_grant_access(self):
        doc_id = self.new_document(title="Private report")
        req_id = self.ask(doc_id, self.c).json["request_id"]
        response = self.client.post("/api/access/reject", headers=self.a, json={"request_id": req_id})
        self.assertEqual(response.json["status"], "rejected")
        self.assertEqual(self.client.get(f"/api/documents/{doc_id}/download", headers=self.c).status_code, 403)
        self.assertEqual(self.client.post("/api/access/approve", headers=self.a, json={"request_id": req_id}).status_code, 409)

    def test_admin_can_rename_a_field_without_losing_existing_values(self):
        form = {"label": "Office.Code", "options": ["HQ", "Remote"]}
        self.assertEqual(self.client.post("/api/fields", headers=self.b, json=form).status_code, 403)
        response = self.client.post("/api/fields", headers=self.a, json=form)
        field = response.json["field"]
        doc_id = self.new_document(fields={"Office.Code": "HQ"})
        response = self.client.patch(f"/api/fields/{field['id']}", headers=self.a, json={"label": "Office", "options": ["HQ", "Branch"]})
        self.assertEqual(response.status_code, 200)
        detail = self.client.get(f"/api/documents/{doc_id}", headers=self.a).json["document"]
        self.assertEqual(detail["metadata"], {"Office": "HQ"})
        for name in ["Office", "Office.Code"]:
            listing = self.client.get("/api/documents", headers=self.a, query_string={name: "HQ"})
            self.assertIn(doc_id, [doc["id"] for doc in listing.json["documents"]])

    def test_invalid_document_and_metadata(self):
        self.assertEqual(self.upload(self.a, payload=b"not an image").status_code, 400)
        self.assertEqual(self.upload(self.a, fields=["wrong format"]).status_code, 400)
        self.assertEqual(self.client.get("/api/documents/invalid", headers=self.a).status_code, 400)


if __name__ == "__main__":
    unittest.main()
