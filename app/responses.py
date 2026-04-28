from fastapi.responses import Response


def forbidden_response() -> Response:
    return Response("Forbidden", status_code=403)


def not_found_response() -> Response:
    return Response("Not found", status_code=404)
