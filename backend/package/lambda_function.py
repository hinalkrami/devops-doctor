"""
lambda_function.py
------------------
Main entry point for the DevOps Doctor AWS Lambda backend.

Routes:
  GET  /         -> health check (unchanged)
  GET  /health   -> health check (alias)
  POST /diagnose -> invoke Bedrock Qwen3 32B via the Bedrock Mantle
                    OpenAI-compatible endpoint and return an AI diagnosis

Environment variables (set in Lambda Configuration → Environment variables,
or store BEDROCK_API_KEY in AWS Secrets Manager and inject it via a parameter
extension):

  BEDROCK_API_KEY   – required; Bedrock API key (never logged)
  BEDROCK_BASE_URL  – default: https://bedrock-mantle.eu-central-1.api.aws/v1
  MODEL_ID          – default: qwen.qwen3-32b
  MAX_TOKENS        – default: 500
  TEMPERATURE       – default: 0.5

To list available models (useful when verifying the exact model ID):
  GET {BEDROCK_BASE_URL}/models
  e.g. curl -H "Authorization: Bearer $BEDROCK_API_KEY" \
            https://bedrock-mantle.eu-central-1.api.aws/v1/models
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
import httpx
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

# ---------------------------------------------------------------------------
# Configuration – read once at cold start, reused across warm invocations
# ---------------------------------------------------------------------------

BEDROCK_BASE_URL: str = os.environ.get(
    "BEDROCK_BASE_URL",
    "https://bedrock-mantle.eu-central-1.api.aws/v1",
)
MODEL_ID: str = os.environ.get("MODEL_ID", "qwen.qwen3-32b")
MAX_TOKENS: int = int(os.environ.get("MAX_TOKENS", "1500"))
TEMPERATURE: float = float(os.environ.get("TEMPERATURE", "0.5"))
DYNAMODB_TABLE_NAME: str = os.environ.get("DYNAMODB_TABLE_NAME", "devops-doctor-diagnoses")
# TTL for stored diagnoses: default 90 days in seconds
DIAGNOSIS_TTL_SECONDS: int = int(os.environ.get("DIAGNOSIS_TTL_SECONDS", str(90 * 24 * 60 * 60)))

S3_BUCKET_NAME: str = os.environ.get("S3_BUCKET_NAME", "devops-doctor-logs-948588893633")
# Pre-signed URL expiry in seconds (default 5 minutes)
UPLOAD_URL_EXPIRY_SECONDS: int = int(os.environ.get("UPLOAD_URL_EXPIRY_SECONDS", "300"))
# Maximum log file size Lambda will read from S3 (10 MB)
S3_MAX_READ_BYTES: int = 10 * 1024 * 1024

# System prompt – instructs Qwen3 to return a strict JSON object with exactly
# seven fields and no surrounding prose or markdown fences.
SYSTEM_PROMPT = """\
You are DevOps Doctor, an expert in cloud infrastructure, CI/CD pipelines, \
Kubernetes, Linux systems, and application reliability.

When given a log snippet, error message, or problem description, respond with \
ONLY a valid JSON object — no markdown, no code fences, no explanation outside \
the JSON. The object must contain exactly these keys:

{
  "problem":          "<one-sentence description of the problem>",
  "root_cause":       "<technical root cause>",
  "evidence":         "<specific evidence from the input that points to the cause>",
  "explanation":      "<clear explanation of why this happens>",
  "recommended_fix":  "<concrete remediation steps>",
  "kubectl_commands": ["<command 1>", "<command 2>"],
  "prevention":       "<how to prevent this in future>"
}

kubectl_commands must be a JSON array of strings (empty array [] if not applicable). \
All other fields must be non-empty strings. Return nothing except the JSON object.\
"""

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# OpenAI client – created once outside the handler so it is reused across
# warm invocations (connection pool reuse, no re-authentication overhead).
# ---------------------------------------------------------------------------

# The API key must be present; fail loudly at cold-start rather than at
# first invocation so misconfigured deployments surface immediately.
_api_key = os.environ.get("BEDROCK_API_KEY")
if not _api_key:
    raise RuntimeError(
        "BEDROCK_API_KEY environment variable is not set. "
        "Configure it in Lambda → Configuration → Environment variables, "
        "or inject it from AWS Secrets Manager."
    )

openai_client = OpenAI(
    base_url=BEDROCK_BASE_URL,
    api_key=_api_key,
    # ~25-second timeout keeps us safely inside a 30-second Lambda timeout.
    timeout=httpx.Timeout(25.0, connect=5.0),
    max_retries=2,
)

logger.info(
    "OpenAI client initialised. base_url=%s model=%s max_tokens=%d temperature=%.2f",
    BEDROCK_BASE_URL,
    MODEL_ID,
    MAX_TOKENS,
    TEMPERATURE,
)

# ---------------------------------------------------------------------------
# DynamoDB resource – created once at cold start, reused across warm
# invocations. Uses the Lambda execution role credentials automatically.
# ---------------------------------------------------------------------------

_dynamodb = boto3.resource("dynamodb", region_name="eu-central-1")
_diagnoses_table = _dynamodb.Table(DYNAMODB_TABLE_NAME)

logger.info("DynamoDB resource initialised. table=%s", DYNAMODB_TABLE_NAME)

# ---------------------------------------------------------------------------
# S3 client – created once at cold start for pre-signed URL generation and
# log file reads.  Uses the Lambda execution role credentials automatically.
# ---------------------------------------------------------------------------

_s3_client = boto3.client(
    "s3",
    region_name="eu-central-1",
    endpoint_url="https://s3.eu-central-1.amazonaws.com"
)
logger.info("S3 client initialised. bucket=%s", S3_BUCKET_NAME)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _parse_diagnosis(raw: str) -> dict:
    """
    Parse the model's raw text into the expected 7-field dict.

    Qwen3 occasionally wraps output in ```json ... ``` fences despite the
    prompt instruction.  Strip those before attempting JSON parsing.
    If parsing still fails, return the raw text under a 'raw' key so the
    caller can surface a graceful fallback rather than a 502.
    """
    text = raw.strip()

    # Strip ```json ... ``` or ``` ... ``` fences if present.
    if text.startswith("```"):
        lines = text.splitlines()
        # Drop the opening fence line and any closing fence line.
        inner = [
            line for line in lines[1:]
            if line.strip() != "```"
        ]
        text = "\n".join(inner).strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Model response was not valid JSON: %s", exc)
        return {"raw": raw}

    # Ensure kubectl_commands is always a list (model sometimes returns a string).
    if "kubectl_commands" in parsed and isinstance(parsed["kubectl_commands"], str):
        parsed["kubectl_commands"] = [
            cmd.strip()
            for cmd in parsed["kubectl_commands"].splitlines()
            if cmd.strip()
        ]

    return parsed


def _save_to_dynamodb(diagnosis_id: str, log_input: str, diagnosis: dict, s3_key: str = None) -> None:
    """
    Persist a completed diagnosis to DynamoDB.

    Failures are fully isolated — a storage error will never cause the
    caller to return an error response to the user.  The diagnosis_id is
    logged so the item can be traced in CloudWatch even if the write fails.
    """
    now = datetime.now(timezone.utc)
    item = {
        "diagnosis_id": diagnosis_id,
        "timestamp":    now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "log_input":    log_input,
        "model":        MODEL_ID,
        "ttl":          int(now.timestamp()) + DIAGNOSIS_TTL_SECONDS,
    }

    # Store the S3 key if the log came from an uploaded file.
    if s3_key:
        item["s3_key"] = s3_key

    # Flatten the 7 diagnosis fields directly onto the item.
    # If the model returned a raw fallback, store it under raw_response instead.
    if "raw" in diagnosis and len(diagnosis) == 1:
        item["raw_response"] = diagnosis["raw"]
    else:
        for field in ("problem", "root_cause", "evidence", "explanation",
                      "recommended_fix", "kubectl_commands", "prevention"):
            if field in diagnosis:
                item[field] = diagnosis[field]

    try:
        _diagnoses_table.put_item(Item=item)
        logger.info("Saved diagnosis %s to DynamoDB.", diagnosis_id)
    except Exception as exc:
        logger.error(
            "DynamoDB write failed for diagnosis_id=%s: %s", diagnosis_id, exc
        )


def _sanitise_filename(name: str) -> str:
    """
    Strip path components and keep only safe characters.
    Returns a filename safe for use in an S3 key.
    """
    # Take only the final path component so callers can't inject prefixes.
    name = os.path.basename(name)
    # Allow alphanumerics, hyphens, underscores, dots only.
    safe = "".join(c for c in name if c.isalnum() or c in "-_.")
    return safe or "upload"


def _resolve_log_text(body: dict) -> tuple:
    """
    Return (log_text: str, s3_key: str | None).

    Accepts either:
      - body["log"]     – inline text (existing path, unchanged)
      - body["log_key"] – S3 object key; Lambda reads the file content

    Raises ValueError with a caller-safe message on invalid input.
    Raises ClientError for S3 access issues (caught by _handle_diagnose).
    """
    log_key = body.get("log_key", "").strip()

    if log_key:
        # Security: only allow reads from the logs/ prefix.
        if not log_key.startswith("logs/"):
            raise ValueError("log_key must reference an object under the logs/ prefix.")

        obj = _s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=log_key)
        content_length = obj.get("ContentLength", 0)
        if content_length > S3_MAX_READ_BYTES:
            raise ValueError(
                f"Log file exceeds the {S3_MAX_READ_BYTES // (1024*1024)} MB limit."
            )

        text = obj["Body"].read(S3_MAX_READ_BYTES).decode("utf-8", errors="replace").strip()
        if not text:
            raise ValueError("S3 object is empty.")
        return text, log_key

    text = body.get("log", "").strip()
    if not text:
        raise ValueError("Request body must include a non-empty 'log' or 'log_key' field.")
    return text, None


def _handle_upload_url(event: dict) -> dict:
    """
    GET /upload-url?filename=<name>

    Generates a pre-signed S3 PUT URL the client can use to upload a log
    file directly to S3, bypassing Lambda and API Gateway size limits.

    Query params:
        filename  (optional) – original filename, used as a suffix in the key
                               for human readability; defaults to "upload"

    Success response (200):
        {
            "status":     "success",
            "upload_url": "https://...",
            "log_key":    "logs/2026-10-02/uuid-filename.log",
            "expires_in": 300
        }

    Usage:
        1. GET /upload-url?filename=pod-crash.log  → receive upload_url + log_key
        2. PUT <upload_url> with log file body      → direct to S3 (no Lambda)
        3. POST /diagnose { "log_key": "..." }      → Lambda reads from S3
    """
    params = event.get("queryStringParameters") or {}
    raw_filename = params.get("filename", "upload")
    safe_filename = _sanitise_filename(raw_filename)

    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_key = f"logs/{date_prefix}/{uuid.uuid4()}-{safe_filename}"

    try:
        upload_url = _s3_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": log_key},
            ExpiresIn=UPLOAD_URL_EXPIRY_SECONDS,
        )
    except Exception as exc:
        logger.error("Failed to generate pre-signed URL: %s", exc)
        return _json_response(502, {
            "status":  "error",
            "message": "Failed to generate upload URL.",
        })

    logger.info("Generated pre-signed URL for key=%s", log_key)

    return _json_response(200, {
        "status":     "success",
        "upload_url": upload_url,
        "log_key":    log_key,
        "expires_in": UPLOAD_URL_EXPIRY_SECONDS,
    })


def _handle_diagnose(event: dict) -> dict:
    """
    POST /diagnose

    Expected request body:
        { "log": "<raw log text or error description>" }

    Success response (200):
        {
            "status": "success",
            "model": "<MODEL_ID>",
            "diagnosis": {
                "problem":          "...",
                "root_cause":       "...",
                "evidence":         "...",
                "explanation":      "...",
                "recommended_fix":  "...",
                "kubectl_commands": ["..."],
                "prevention":       "..."
            }
        }

    Error responses:
        400 – missing or empty "log" / "log_key" field, or invalid log_key
        401 – authentication error (bad/expired API key)
        429 – rate limit exceeded
        504 – upstream timeout
        502 – any other API error
        500 – unexpected internal error
    """
    body = _parse_body(event)

    # Resolve log text from inline body["log"] or S3 via body["log_key"].
    try:
        log_text, s3_key = _resolve_log_text(body)
    except ValueError as exc:
        return _json_response(400, {
            "status":  "error",
            "message": str(exc),
        })
    except Exception as exc:
        # S3 ClientError (NoSuchKey, access denied, etc.)
        logger.error("Failed to read log from S3: %s", exc)
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
        if error_code == "NoSuchKey":
            return _json_response(400, {
                "status":  "error",
                "message": "The specified log_key does not exist in S3.",
            })
        return _json_response(502, {
            "status":  "error",
            "message": "Failed to read log file from S3.",
        })

    logger.info("Invoking model %s for diagnosis request.", MODEL_ID)

    try:
        completion = openai_client.chat.completions.create(
            model=MODEL_ID,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": log_text},
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

    except APIStatusError as exc:
        status = exc.status_code
        logger.error(
            "Bedrock Mantle API error: status=%d type=%s message=%s",
            status,
            type(exc).__name__,
            exc.message,
        )
        if status == 401:
            return _json_response(401, {
                "status": "error",
                "message": "Authentication failed. Check BEDROCK_API_KEY.",
                "error_type": "AuthenticationError",
            })
        if status == 429:
            return _json_response(429, {
                "status": "error",
                "message": "Rate limit exceeded. Retry after a short delay.",
                "error_type": "RateLimitError",
            })
        return _json_response(502, {
            "status": "error",
            "message": "Bedrock Mantle returned an error.",
            "error_type": type(exc).__name__,
            "http_status": status,
        })

    except APITimeoutError as exc:
        logger.error("Bedrock Mantle request timed out: %s", type(exc).__name__)
        return _json_response(504, {
            "status": "error",
            "message": "Request to Bedrock Mantle timed out.",
            "error_type": "APITimeoutError",
        })

    except APIConnectionError as exc:
        logger.error(
            "Bedrock Mantle connection error: %s – %s",
            type(exc).__name__,
            str(exc),
        )
        return _json_response(502, {
            "status": "error",
            "message": "Could not connect to Bedrock Mantle endpoint.",
            "error_type": "APIConnectionError",
        })

    # ---------------------------------------------------------------------------
    # Extract and parse the structured response
    # ---------------------------------------------------------------------------

    try:
        raw_content = completion.choices[0].message.content.strip()
    except (IndexError, AttributeError) as exc:
        logger.error("Unexpected response shape from Bedrock Mantle: %s", exc)
        return _json_response(502, {
            "status": "error",
            "message": "Unexpected response format from Bedrock Mantle.",
            "error": str(exc),
        })

    diagnosis = _parse_diagnosis(raw_content)

    usage = completion.usage
    if usage:
        logger.info(
            "Diagnosis complete. prompt_tokens=%d completion_tokens=%d total_tokens=%d",
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.total_tokens,
        )
    else:
        logger.info("Diagnosis complete (no usage data returned).")

    # Generate a unique ID for this diagnosis, persist to DynamoDB, then
    # return it in the response so callers can reference the stored record.
    diagnosis_id = str(uuid.uuid4())
    _save_to_dynamodb(diagnosis_id, log_text, diagnosis, s3_key=s3_key)

    return _json_response(200, {
        "status":       "success",
        "model":        MODEL_ID,
        "diagnosis_id": diagnosis_id,
        "diagnosis":    diagnosis,
    })


# ---------------------------------------------------------------------------
# History handler
# ---------------------------------------------------------------------------

# Maximum number of records a caller can request in a single GET /history call.
_HISTORY_MAX_LIMIT = 50
_HISTORY_DEFAULT_LIMIT = 20

# Fields projected from DynamoDB — never fetch the verbose diagnosis fields
# (explanation, recommended_fix, prevention) in a list view.
_HISTORY_PROJECTION = "diagnosis_id, #ts, model, log_input, problem"
# 'timestamp' is a DynamoDB reserved word; use an expression alias.
_HISTORY_EXPR_NAMES = {"#ts": "timestamp"}


def _handle_history(event: dict) -> dict:
    """
    GET /history[?limit=N]

    Query params:
        limit  (optional) – number of records to return, 1–50, default 20

    Success response (200):
        {
            "status": "success",
            "count":  <int>,
            "limit":  <int>,
            "items":  [
                {
                    "diagnosis_id": "...",
                    "timestamp":    "2026-10-02T06:51:12Z",
                    "model":        "qwen.qwen3-32b",
                    "log_input":    "ImagePullBackOff: ...",   // truncated to 200 chars
                    "problem":      "..."
                },
                ...
            ]
        }

    Error responses:
        400 – invalid limit parameter
        502 – DynamoDB error
    """
    # Parse and validate the optional limit query parameter.
    params = event.get("queryStringParameters") or {}
    raw_limit = params.get("limit", str(_HISTORY_DEFAULT_LIMIT))
    try:
        limit = int(raw_limit)
        if not (1 <= limit <= _HISTORY_MAX_LIMIT):
            raise ValueError
    except ValueError:
        return _json_response(400, {
            "status":  "error",
            "message": f"limit must be an integer between 1 and {_HISTORY_MAX_LIMIT}.",
        })

    logger.info("GET /history limit=%d", limit)

    try:
        response = _diagnoses_table.scan(
            ProjectionExpression=_HISTORY_PROJECTION,
            ExpressionAttributeNames=_HISTORY_EXPR_NAMES,
        )
        items = response.get("Items", [])

        # Paginate if DynamoDB returned a continuation token (> 1 MB of data).
        while "LastEvaluatedKey" in response:
            response = _diagnoses_table.scan(
                ProjectionExpression=_HISTORY_PROJECTION,
                ExpressionAttributeNames=_HISTORY_EXPR_NAMES,
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))

    except Exception as exc:
        logger.error("DynamoDB Scan failed: %s", exc)
        return _json_response(502, {
            "status":  "error",
            "message": "Failed to retrieve diagnosis history.",
        })

    # Sort by timestamp descending (most recent first) and apply limit.
    items.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    items = items[:limit]

    # Truncate log_input to 200 chars to keep the response lean.
    for item in items:
        if "log_input" in item and len(item["log_input"]) > 200:
            item["log_input"] = item["log_input"][:200] + "..."

    return _json_response(200, {
        "status": "success",
        "count":  len(items),
        "limit":  limit,
        "items":  items,
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

        # POST /diagnose — AI-powered log diagnosis via Bedrock Mantle / Qwen3 32B
        if http_method == "POST" and path == "/diagnose":
            return _handle_diagnose(event)

        # GET /history — return recent diagnoses from DynamoDB
        if http_method == "GET" and path == "/history":
            return _handle_history(event)

        # GET /upload-url — generate a pre-signed S3 PUT URL for log uploads
        if http_method == "GET" and path == "/upload-url":
            return _handle_upload_url(event)

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
