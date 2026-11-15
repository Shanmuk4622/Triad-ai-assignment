from bson import ObjectId
from flask import abort, current_app, request


def database():
    return current_app.extensions["db"]


def json_body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Send a JSON object.")
    return data


def clean_text(value, label, limit=100):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        abort(400, f"{label} must contain 1 to {limit} characters.")
    value = value.strip()
    if not value.isprintable():
        abort(400, f"{label} must use printable characters.")
    return value


def object_id(value, label):
    if not isinstance(value, str) or not ObjectId.is_valid(value):
        abort(400, f"Invalid {label}.")
    return ObjectId(value)


def timestamp(value):
    return value.isoformat(timespec="seconds").removesuffix("+00:00") + "Z"
