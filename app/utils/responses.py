"""Standardized API response utilities."""

from typing import Any, Dict, Optional

from flask import jsonify


def success_response(data: Any = None, message: Optional[str] = None, code: int = 200):
    """
    Create a standardized success response.

    Args:
        data: The response data
        message: Optional success message
        code: HTTP status code (default 200)

    Returns:
        Flask JSON response tuple
    """
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if message:
        response["message"] = message
    return jsonify(response), code


def error_response(
    message: str, code: int = 400, details: Optional[Any] = None
):
    """
    Create a standardized error response.

    Args:
        message: Error message
        code: HTTP status code (default 400)
        details: Optional additional error details

    Returns:
        Flask JSON response tuple
    """
    response = {"success": False, "error": message}
    if details is not None:
        response["details"] = details
    return jsonify(response), code


def validation_error_response(errors: Dict[str, str], code: int = 400):
    """
    Create a standardized validation error response.

    Args:
        errors: Dictionary of field names to error messages
        code: HTTP status code (default 400)

    Returns:
        Flask JSON response tuple
    """
    return jsonify({
        "success": False,
        "error": "Validation failed",
        "validation_errors": errors
    }), code
