"""
test_lambda.py
--------------
Local test for the DevOps Doctor Lambda handler.

Runs without an AWS account or any network connection — it simply imports
lambda_handler and calls it the same way AWS Lambda would, then checks the
response looks correct.

Usage:
    python test_lambda.py
"""

import json
import sys

# Add the backend directory to the module search path so we can import
# lambda_function without installing it as a package.
sys.path.insert(0, "backend")

from lambda_function import lambda_handler  # noqa: E402


def make_api_gateway_event(method="GET", path="/"):
    """
    Build a minimal API Gateway proxy event.

    In production AWS passes a much richer object, but the handler only
    needs this shape to function correctly right now.
    """
    return {
        "httpMethod": method,
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "queryStringParameters": None,
        "body": None,
        "isBase64Encoded": False,
    }


def test_status_code_is_200():
    """The handler must return HTTP 200 for a normal GET request."""
    event = make_api_gateway_event()
    response = lambda_handler(event, context=None)

    assert response["statusCode"] == 200, (
        f"Expected statusCode 200, got {response['statusCode']}"
    )
    print("✅  test_status_code_is_200 passed")


def test_response_body_fields():
    """The JSON body must contain the expected message, service, and status."""
    event = make_api_gateway_event()
    response = lambda_handler(event, context=None)

    body = json.loads(response["body"])

    assert body["message"] == "DevOps Doctor backend is running", (
        f"Unexpected message: {body['message']}"
    )
    assert body["service"] == "lambda", (
        f"Unexpected service: {body['service']}"
    )
    assert body["status"] == "success", (
        f"Unexpected status: {body['status']}"
    )
    print("✅  test_response_body_fields passed")


def test_content_type_header():
    """Response must declare Content-Type: application/json."""
    event = make_api_gateway_event()
    response = lambda_handler(event, context=None)

    content_type = response.get("headers", {}).get("Content-Type", "")
    assert content_type == "application/json", (
        f"Unexpected Content-Type: {content_type}"
    )
    print("✅  test_content_type_header passed")


if __name__ == "__main__":
    print("Running DevOps Doctor Lambda local tests...\n")

    tests = [
        test_status_code_is_200,
        test_response_body_fields,
        test_content_type_header,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌  {test.__name__} FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌  {test.__name__} ERROR: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")

    # Exit with a non-zero code if any test failed — useful in CI pipelines
    if failed:
        sys.exit(1)
