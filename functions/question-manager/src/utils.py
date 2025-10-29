"""Utility functions for question-manager"""
from typing import Dict, Any
import json


def success_response(data: Any, message: str = "Success") -> Dict[str, Any]:
    """Standard success response"""
    return {
        "success": True,
        "message": message,
        "data": data
    }


def error_response(message: str, code: int = 400, details: Any = None) -> Dict[str, Any]:
    """Standard error response"""
    response = {
        "success": False,
        "message": message,
        "code": code
    }
    if details:
        response["details"] = details
    return response


def parse_request_body(req) -> Dict[str, Any]:
    """Parse request body from Appwrite request"""
    try:
        if hasattr(req, 'body'):
            return json.loads(req.body) if isinstance(req.body, str) else req.body
        return {}
    except Exception as e:
        raise ValueError(f"Invalid request body: {str(e)}")

