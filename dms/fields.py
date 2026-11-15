from flask import Blueprint, abort, g, jsonify
from pymongo.errors import DuplicateKeyError

from .auth import require_user
from .common import clean_text, database, json_body

fields_api = Blueprint("fields", __name__)


def field_key(label):
    # Hex encodes arbitrary labels as safe MongoDB keys, including dots and dollars.
    return label.casefold().encode().hex()


def seed_fields(db):
    label = "Report Type"
    key = field_key(label)
    try:
        db.fields.update_one(
            {"_id": key},
            {"$setOnInsert": {"label": label, "aliases": [key], "options": ["Financial", "Operational", "Research"]}},
            upsert=True,
        )
    except DuplicateKeyError:
        if db.fields.find_one({"_id": key}) is None:
            raise


def field_maps():
    definitions = list(database().fields.find())
    labels = {field["_id"]: field["label"] for field in definitions}
    aliases = {alias: field["_id"] for field in definitions for alias in field["aliases"]}
    return labels, aliases


def metadata_key(label, aliases):
    key = field_key(label)
    return aliases.get(key, key)


def field_response(field):
    return {"id": field["_id"], "label": field["label"], "options": field["options"]}


def field_input():
    if g.user["role"] != "admin":
        abort(403, "Only admins can change custom fields.")
    data = json_body()
    label = clean_text(data.get("label"), "Field name", 60)
    if label.casefold() in {"division", "q"}:
        abort(400, "That field name is reserved.")
    options = data.get("options", [])
    if not isinstance(options, list) or len(options) > 30:
        abort(400, "Provide up to 30 options as a list.")
    options = list(dict.fromkeys(clean_text(option, "Option", 100) for option in options))
    return label, options


@fields_api.get("/fields")
@require_user
def list_fields():
    return jsonify(fields=[field_response(field) for field in database().fields.find().sort("label")])


@fields_api.post("/fields")
@require_user
def create_field():
    label, options = field_input()
    key = field_key(label)
    field = {"_id": key, "label": label, "options": options, "aliases": [key]}
    try:
        database().fields.insert_one(field)
    except DuplicateKeyError:
        abort(409, "That field name is already in use.")
    return jsonify(field=field_response(field)), 201


@fields_api.patch("/fields/<field_id>")
@require_user
def edit_field(field_id):
    label, options = field_input()
    try:
        result = database().fields.update_one(
            {"_id": field_id},
            {"$set": {"label": label, "options": options}, "$addToSet": {"aliases": field_key(label)}},
        )
    except DuplicateKeyError:
        abort(409, "That field name is already in use.")
    if not result.matched_count:
        abort(404, "Field not found.")
    return jsonify(field=field_response({"_id": field_id, "label": label, "options": options}))
