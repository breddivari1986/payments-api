import unittest
import app


class PaymentsTests(unittest.TestCase):


    def test_creates_and_reads_a_payment(self):
        code, p = app.create_payment({"idempotency_key": "order-1001-a", "customer_id": "c_1", "amount_minor": 1999, "currency": "usd"})
        assert code == 201 and p["status"] == "authorized" and p["currency"] == "USD"
        assert app.get_payment(p["id"]) == (200, p)


    def test_the_same_key_returns_the_same_payment(self):
        body = {"idempotency_key": "order-2002-b", "customer_id": "c_2", "amount_minor": 500, "currency": "EUR"}
        first = app.create_payment(body)
        again = app.create_payment(body)
        assert first[0] == 201 and again[0] == 200 and again[1]["id"] == first[1]["id"]


    def test_validation_rejects_bad_input(self):
        assert app.create_payment({"idempotency_key": "x", "customer_id": "c", "amount_minor": 1, "currency": "USD"})[0] == 400
        assert app.create_payment({"idempotency_key": "order-3003-c", "customer_id": "", "amount_minor": 1, "currency": "USD"})[0] == 400
        assert app.create_payment({"idempotency_key": "order-3004-d", "customer_id": "c", "amount_minor": 0, "currency": "USD"})[0] == 400
        assert app.create_payment({"idempotency_key": "order-3005-e", "customer_id": "c", "amount_minor": 5, "currency": "XYZ"})[0] == 400
        assert app.get_payment("pay_0000000000000000")[0] == 404


    def test_metrics_render(self):
        text = app.metrics()
        assert "payments_created_total" in text and "payments_uptime_seconds" in text
