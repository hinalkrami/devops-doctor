"""
lambda_function.py
------------------
This is the main entry point for the DevOps Doctor AWS Lambda backend.

AWS Lambda runs this file in response to an event (e.g. an HTTP request
coming through API Gateway). You don't manage any servers — AWS handles
all the infrastructure. You just write the handler function below.
"""

import json


def lambda_handler(event, context):
    """
    The Lambda handler is the function AWS calls when this Lambda is invoked.

    Parameters
    ----------
    event : dict
        Contains all the data about the incoming request.
        When triggered via API Gateway, this includes HTTP method, headers,
        query string parameters, and the request body.

    context : object
        Provides runtime information about the Lambda invocation (e.g. function
        name, memory limit, remaining execution time). We don't need it here
        but Lambda always passes it in.

    Returns
    -------
    dict
        A response object in the API Gateway proxy format:
          - statusCode : HTTP status code (200 = OK)
          - headers    : HTTP response headers
          - body       : JSON-encoded string with our response data
    """

    try:
        # Build the response payload — this is what the caller receives
        response_body = {
            "message": "DevOps Doctor backend is running",
            "service": "lambda",
            "status": "success",
        }

        # Return in API Gateway proxy integration format.
        # API Gateway expects this exact shape; anything else results in a
        # 502 Bad Gateway error on the caller's side.
        return {
            "statusCode": 200,
            "headers": {
                # Allow browsers and API clients to parse the response correctly
                "Content-Type": "application/json",
                # CORS header — required if a web frontend will call this API
                "Access-Control-Allow-Origin": "*",
            },
            # body must be a string, not a dict — json.dumps() handles that
            "body": json.dumps(response_body),
        }

    except Exception as e:
        # If anything unexpected goes wrong, return a 500 instead of crashing.
        # Lambda will still mark the invocation as successful (exit 0), but
        # the HTTP caller gets a proper error response with context.
        error_body = {
            "message": "An internal error occurred",
            "service": "lambda",
            "status": "error",
            "error": str(e),
        }

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(error_body),
        }
