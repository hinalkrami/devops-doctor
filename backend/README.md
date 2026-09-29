# DevOps Doctor — Lambda Backend

## What is AWS Lambda?

AWS Lambda is a **serverless compute** service. You upload your code and Lambda runs it on demand — you never provision, patch, or manage servers. You pay only for the compute time your code actually uses (billed per millisecond).

A Lambda function is triggered by an **event source**: an HTTP request through API Gateway, a message on an SQS queue, a file uploaded to S3, a scheduled CloudWatch rule, and many others. Lambda receives the event, runs your handler, and returns a response.

Key facts:
- **Runtime**: Each function targets a specific runtime (Python 3.12 here).
- **Handler**: The entry-point you register with Lambda — `lambda_function.lambda_handler` in this project.
- **Stateless**: Each invocation is independent. Do not rely on in-memory state between calls.
- **Timeout**: Default 3 seconds, configurable up to 15 minutes.

---

## What does `lambda_handler` do?

`lambda_handler(event, context)` in `lambda_function.py` is the function Lambda calls for every invocation.

**Right now it:**
1. Receives the incoming `event` (HTTP request data when triggered via API Gateway).
2. Builds a JSON response body:
   ```json
   {
     "message": "DevOps Doctor backend is running",
     "service": "lambda",
     "status": "success"
   }
   ```
3. Wraps it in the **API Gateway proxy integration format** (a dict with `statusCode`, `headers`, and a string `body`) and returns HTTP `200 OK`.
4. Catches any unexpected exception and returns HTTP `500` with error details instead of crashing silently.

---

## How we will connect it to API Gateway later

AWS API Gateway acts as the front door for HTTP traffic. The plan for Phase 2:

1. **Create a REST API** (or HTTP API) in API Gateway in the `eu-central-1` region.
2. **Add a route** — e.g. `GET /health` — and configure it to use **Lambda Proxy Integration**.
   - With proxy integration, API Gateway forwards the raw HTTP request as the Lambda `event` and maps the Lambda return value directly back to the HTTP response. This is why our handler already returns `statusCode`, `headers`, and `body`.
3. **Deploy the API** to a stage (e.g. `dev`).
4. API Gateway provides a public **invoke URL** such as:
   ```
   https://<api-id>.execute-api.eu-central-1.amazonaws.com/dev/health
   ```
5. A `GET` request to that URL will invoke `lambda_handler` and return the JSON health response.

No code changes to the handler are needed for this — it is already formatted correctly for API Gateway proxy integration.

---

## Local development

### Running the local test

```bash
python test_lambda.py
```

The test imports `lambda_handler` directly (no AWS account needed) and asserts the response status is `200`.

### Installing dependencies

```bash
pip install -r backend/requirements.txt
```

No packages are required in Phase 1, so this is a no-op for now.
