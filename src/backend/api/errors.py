from fastapi.responses import JSONResponse

STATUS = {'VALIDATION_ERROR': 422, 'UNAUTHENTICATED': 401, 'FORBIDDEN': 403,
          'NOT_FOUND': 404, 'CONFLICT': 409, 'UNAVAILABLE': 503}


def error_response(code, message, correlation_id, status=None):
    status = status or STATUS.get(code, 500)
    return JSONResponse(status_code=status, content=dict(code=code, message=message,
                        correlation_id=correlation_id, http_status=status))
