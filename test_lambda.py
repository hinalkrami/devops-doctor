"""
test_lambda.py
--------------
Local tests for the DevOps Doctor Lambda handler.

Runs without an AWS account or any network connection.  Bedrock calls are
intercepted by a lightweight unittest.mock patch so the handler logic can be
exercised end-to-end without real AWS credentials.

Usage:
    python test_lambda.py
"""

import json
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add the backend directory to the module search path so we can import
# lambda_function without installing it as a package.
sys.path.insert(0, "backend")

from lambda_function import lambda_handler  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_api_gateway_event(method="GET", path="/", body=None):
    """
    Build a minimal API Gateway Lambda Proxy Integration event.

    In production AWS passes a much richer object, but the handler only
    needs this shape to function correctly.
    """
    return {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": None,
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def make_bedrock_converse_response(text: str) -> dict:
    """
    Build a minimal boto3 bedrock-runtime converse() response that matches
    the shape the handler expects.
    """
    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "usage": {"inputTokens": 42, "outputTokens": 99},
        "stopReason": "end_turn",
    }


# ---------------------------------------------------------------------------
# Health-check tests (existing behaviour — must remain unchanged)
# ---------------------------------------------------------------------------

class TestHealthCheck(unittest.TestCase):

    def test_status_code_is_200(self):
        """GET / must return HTTP 200."""
        event = make_api_gateway_event()
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 200)

    def test_response_body_fields(self):
        """GET / body must contain the expected message, service, and status."""
        event = make_api_gateway_event()
        response = lambda_handler(event, context=None)
        body = json.loads(response["body"])
        self.assertEqual(body["message"], "DevOps Doctor backend is running")
        self.assertEqual(body["service"], "lambda")
        self.assertEqual(body["status"], "success")

    def test_content_type_header(self):
        """Response must declare Content-Type: application/json."""
        event = make_api_gateway_event()
        response = lambda_handler(event, context=None)
        self.assertEqual(
            response["headers"]["Content-Type"], "application/json"
        )

    def test_cors_header_present(self):
        """Response must include Access-Control-Allow-Origin: *."""
        event = make_api_gateway_event()
        response = lambda_handler(event, context=None)
        self.assertEqual(
            response["headers"]["Access-Control-Allow-Origin"], "*"
        )

    def test_health_alias_route(self):
        """GET /health must also return 200 with the health-check body."""
        event = make_api_gateway_event(method="GET", path="/health")
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "success")

    def test_unknown_route_falls_back_to_health(self):
        """Any unrecognised route must fall back to the health response."""
        event = make_api_gateway_event(method="GET", path="/unknown")
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "success")


# ---------------------------------------------------------------------------
# /diagnose route tests
# ---------------------------------------------------------------------------

class TestDiagnoseRoute(unittest.TestCase):

    # ------------------------------------------------------------------
    # Input-validation tests (no Bedrock call needed)
    # ------------------------------------------------------------------

    def test_diagnose_missing_body_returns_400(self):
        """POST /diagnose with no body must return 400."""
        event = make_api_gateway_event(method="POST", path="/diagnose")
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "error")

    def test_diagnose_empty_log_returns_400(self):
        """POST /diagnose with an empty 'log' field must return 400."""
        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"log": "   "}
        )
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 400)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "error")

    def test_diagnose_missing_log_key_returns_400(self):
        """POST /diagnose body without a 'log' key must return 400."""
        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"other_key": "value"}
        )
        response = lambda_handler(event, context=None)
        self.assertEqual(response["statusCode"], 400)

    # ------------------------------------------------------------------
    # Successful Bedrock invocation (mocked)
    # ------------------------------------------------------------------

    @patch("lambda_function._get_bedrock_client")
    def test_diagnose_success(self, mock_get_client):
        """POST /diagnose with a valid log must return 200 with a diagnosis."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_converse_response(
            "Root cause: OOMKilled. The container exceeded its memory limit."
        )
        mock_get_client.return_value = mock_client

        event = make_api_gateway_event(
            method="POST",
            path="/diagnose",
            body={"log": "OOMKilled: container memory limit exceeded"},
        )
        response = lambda_handler(event, context=None)

        self.assertEqual(response["statusCode"], 200)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "success")
        self.assertIn("diagnosis", body)
        self.assertTrue(len(body["diagnosis"]) > 0)
        self.assertEqual(body["model"], "qwen.qwen3-32b-v1:0")

    @patch("lambda_function._get_bedrock_client")
    def test_diagnose_passes_log_text_to_bedrock(self, mock_get_client):
        """The handler must forward the exact log text to the Converse API."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_converse_response("ok")
        mock_get_client.return_value = mock_client

        log_text = "ERROR: connection refused on port 5432"
        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"log": log_text}
        )
        lambda_handler(event, context=None)

        # Inspect what was sent to Bedrock
        call_kwargs = mock_client.converse.call_args[1]
        user_content = call_kwargs["messages"][0]["content"][0]["text"]
        self.assertEqual(user_content, log_text)

    @patch("lambda_function._get_bedrock_client")
    def test_diagnose_correct_model_id_used(self, mock_get_client):
        """The handler must invoke the configured Qwen3 model ID."""
        mock_client = MagicMock()
        mock_client.converse.return_value = make_bedrock_converse_response("ok")
        mock_get_client.return_value = mock_client

        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"log": "some error"}
        )
        lambda_handler(event, context=None)

        call_kwargs = mock_client.converse.call_args[1]
        self.assertEqual(call_kwargs["modelId"], "qwen.qwen3-32b-v1:0")

    # ------------------------------------------------------------------
    # Bedrock error handling (mocked)
    # ------------------------------------------------------------------

    @patch("lambda_function._get_bedrock_client")
    def test_diagnose_bedrock_client_error_returns_502(self, mock_get_client):
        """A Bedrock ClientError must result in a 502 response."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(
            error_response={
                "Error": {
                    "Code": "ThrottlingException",
                    "Message": "Rate exceeded",
                }
            },
            operation_name="Converse",
        )
        mock_get_client.return_value = mock_client

        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"log": "some error"}
        )
        response = lambda_handler(event, context=None)

        self.assertEqual(response["statusCode"], 502)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error_code"], "ThrottlingException")

    @patch("lambda_function._get_bedrock_client")
    def test_diagnose_malformed_bedrock_response_returns_502(self, mock_get_client):
        """A malformed Bedrock response shape must return 502, not crash."""
        mock_client = MagicMock()
        # Return a response missing the expected nested structure
        mock_client.converse.return_value = {"unexpected": "shape"}
        mock_get_client.return_value = mock_client

        event = make_api_gateway_event(
            method="POST", path="/diagnose", body={"log": "some error"}
        )
        response = lambda_handler(event, context=None)

        self.assertEqual(response["statusCode"], 502)
        body = json.loads(response["body"])
        self.assertEqual(body["status"], "error")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Use unittest's built-in runner for coloured output and proper exit codes
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestHealthCheck))
    suite.addTests(loader.loadTestsFromTestCase(TestDiagnoseRoute))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    sys.exit(0 if result.wasSuccessful() else 1)
