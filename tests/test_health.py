import unittest
from fastapi.testclient import TestClient
from app.main import app


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("status", data)
        self.assertEqual(data["service"], "documentador-ai-service")
        self.assertIn("model", data)
        self.assertIn("geminiConfigured", data)


if __name__ == "__main__":
    unittest.main()
