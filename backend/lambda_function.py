"""
lambda_function.py
------------------
Main entry point for the DevOps Doctor AWS Lambda backend.

Routes:
  GET  /         -> health check (unchanged)
  GET  /health   -> health check (alias)
  POST /diagnose -> invoke Bedrock Qwen3 32B and return an AI diagnosis

All responses use API Gateway Lambda Proxy Integration format.
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "eu-central-1")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "qwen.qwen3-32b-v1:0")

# Maximum tokens Qwen3 32B is allowed to produce in a single response.
# The model supports up to 8K output tokens; 2048 is generous for a diagnosis.
MAX_TOKENS = int(os.environ.get("BEDROCK_MAX_TOKENS", "2048"))

# System prompt that frames every diagnosis request.
SYSTEM_PROMPT = (
    "You are DevOps Doctor, an expert in cloud infrastructure, CI/CD pipelines, "
    "Kubernetes, Linux systems, and application reliability. "
    "When given a log snippet, error message, or description of a problem, "
    "you diagnose the root cause, explain it clearly, and suggest concrete remediation steps. "
    "Be concise, technical, and actionable."
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_bedrock_client = None  # module-level cache — reused across warm invocations


def _get_bedrock_client():
    """Return a cached boto3 bedrock-runtime client."""
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
    return _bedrock_client


def _json_response(status_code: int, body: dict) -> dict:
    """Wrap a dict in the API Gateway proxy integration envelope."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _parse_body(event: dict) -> dict:
    """
    Safely parse the JSON request body from an API Gateway proxy event.
    Returns an empty dict if body is absent or not valid JSON.
    """
    raw = event.get("body") or "{}"
    if isinstance(raw, dict):
        return raw  # already parsed (e.g. direct Lambda test invocations)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_health() -> dict:
    """Return a static health-check response. Unchanged from Phase 1."""
    return _json_response(200, {
        "message": "DevOps Doctor backend is running",
        "service": "lambda",
        "status": "success",
    })


def _handle_diagnose(event: dict) -> dict:
    """
    POST /diagnose

    Expected request body:
        { "log": "<raw log text or error description>" }

    Success response (200):
        {
            "status": "success",
            "diagnosis": "<Qwen3 response text>",
            "model": "qwen.qwen3-32b-v1:0"
        }

    Error responses:
        400 – missing or empty "log" field
        500 – unexpected internal error
        502 – Bedrock returned an error
    """
    body = _parse_body(event)

    log_text = body.get("log", "").strip()
    if not log_text:
        return _json_response(400, {
            "status": "error",
            "message": "Request body must include a non-empty 'log' field.",
        })

    logger.info("Invoking Bedrock model %s for diagnosis request.", BEDROCK_MODEL_ID)

    client = _get_bedrock_client()

    try:
        response = client.converse(
            modelId=BEDROCK_MODEL_ID,
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": log_text}],
                }
            ],
            inferenceConfig={
                "maxTokens": MAX_TOKENS,
                "temperature": 0.2,   # low temperature for factual, deterministic output
                "topP": 0.9,
            },
        )
    except ClientError as exc:
        error_code = exc.response["Error"]["Code"]
        error_msg = exc.response["Error"]["Message"]
        logger.error("Bedrock ClientError: %s – %s", error_code, error_msg)
        return _json_response(502, {
            "status": "error",
            "message": "Bedrock invocation failed.",
            "error_code": error_code,
            "error": error_msg,
        })

    # Extract the assistant's text from the Converse response envelope:
    # response["output"]["message"]["content"] is a list of content blocks.
    try:
        content_blocks = response["output"]["message"]["content"]
        diagnosis_text = "\n".join(
            block["text"]
            for block in content_blocks
            if "text" in block
        ).strip()
    except (KeyError, TypeError) as exc:
        logger.error("Unexpected Bedrock response shape: %s", exc)
        return _json_response(502, {
            "status": "error",
            "message": "Unexpected response format from Bedrock.",
            "error": str(exc),
        })

    logger.info(
        "Diagnosis complete. Input tokens: %s, output tokens: %s.",
        response.get("usage", {}).get("inputTokens", "n/a"),
        response.get("usage", {}).get("outputTokens", "n/a"),
    )

    return _json_response(200, {
        "status": "success",
        "diagnosis": diagnosis_text,
        "model": BEDROCK_MODEL_ID,
    })


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    """
    AWS Lambda handler — called for every invocation.

    Dispatches to the appropriate route handler based on the HTTP method and
    path from the API Gateway proxy event. Supports both:
      - API Gateway REST API / v1 proxy: event["httpMethod"] + event["path"]
      - API Gateway HTTP API / v2 payload: event["requestContext"]["http"]["method"]
        + event["rawPath"]

    Falls back to the health response for any unrecognised route so existing
    integrations are never broken.
    """
    try:
        # HTTP API v2 payload format
        request_context = event.get("requestContext", {})
        if "http" in request_context:
            http_method = request_context["http"].get("method", "GET").upper()
            path = event.get("rawPath", "/")
        else:
            # REST API v1 proxy format
            http_method = event.get("httpMethod", "GET").upper()
            path = event.get("path", "/")

        path = path.rstrip("/") or "/"

        logger.info("Received %s %s", http_method, path)

        # POST /diagnose — AI-powered log diagnosis via Bedrock Qwen3 32B
        if http_method == "POST" and path == "/diagnose":
            return _handle_diagnose(event)

        # GET / or GET /health — health check (all other routes fall here too)
        return _handle_health()

    except Exception as exc:
        logger.exception("Unhandled exception in lambda_handler: %s", exc)
        return _json_response(500, {
            "message": "An internal error occurred",
            "service": "lambda",
            "status": "error",
            "error": str(exc),
        })
