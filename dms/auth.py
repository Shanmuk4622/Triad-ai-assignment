import os
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, abort, current_app, g, jsonify, request
from itsdangerous import BadData, URLSafeTimedSerializer
from pymongo.errors import DuplicateKeyError
from werkzeug.security import check_password_hash, generate_password_hash

from .common import clean_text, database, json_body, object_id

auth_api = Blueprint("auth", __name__)


def signer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="triad-dms-auth")


def require_user(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            abort(401, "Sign in to continue.")
        try:
            user_id = signer().loads(token, max_age=current_app.config["TOKEN_AGE"])
        except BadData:
            abort(401, "Your session is invalid or expired. Sign in again.")
        g.user = database().users.find_one({"_id": object_id(user_id, "user ID")})
        if g.user is None:
            abort(401, "Your account is unavailable.")
        return view(*args, **kwargs)

    return wrapped


def public_user(user):
    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "division": user["division"],
        "role": user["role"],
    }


def promote_user(db, account):
    return db.users.update_one(
        {"identity_keys": account.strip().casefold()}, {"$set": {"role": "admin"}}
    ).matched_count


def seed_admin(db):
    username = os.environ.get("DMS_ADMIN_USERNAME", "").strip()
    password = os.environ.get("DMS_ADMIN_PASSWORD", "")
    if not username and not password:
        return
    division = os.environ.get("DMS_ADMIN_DIVISION", "Division A").strip()
    if not (1 <= len(username) <= 100 and 12 <= len(password) <= 128 and 1 <= len(division) <= 80
            and username.isprintable() and division.isprintable()):
        raise RuntimeError("Set a valid DMS admin username, division, and password of at least 12 characters.")
    key = username.casefold()
    user = db.users.find_one({"identity_keys": key})
    if not user:
        try:
            db.users.insert_one(make_user(username, None, division, password, role="admin"))
            return
        except DuplicateKeyError:
            user = db.users.find_one({"identity_keys": key})
    if user["role"] != "admin" or user["username"].casefold() != key:
        raise RuntimeError("The configured admin username is already in use.")


def make_user(username, email, division, password, role="member"):
    return {
        "username": username,
        "email": email,
        "identity_keys": list(dict.fromkeys([username.casefold(), (email or username).casefold()])),
        "division": division,
        "division_key": division.casefold(),
        "password_hash": generate_password_hash(password),
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }


@auth_api.post("/auth/register")
def register():
    data = json_body()
    username = clean_text(data.get("username") or data.get("name") or data.get("email"), "Username")
    email = data.get("email")
    if email is not None:
        email = clean_text(email, "Email", 254)
        local, separator, domain = email.partition("@")
        if not separator or not local or not domain or "@" in domain or any(c.isspace() for c in email):
            abort(400, "Enter a valid email address.")
    division = clean_text(data.get("division"), "Division", 80)
    password = data.get("password")
    if not isinstance(password, str) or not 6 <= len(password) <= 128:
        abort(400, "Password must contain 6 to 128 characters.")

    user = make_user(username, email, division, password)
    try:
        database().users.insert_one(user)
    except DuplicateKeyError:
        abort(409, "That username or email is already registered.")
    return jsonify(message="Account created.", user=public_user(user)), 201


@auth_api.post("/auth/login")
def login():
    data = json_body()
    identity = clean_text(data.get("username") or data.get("email"), "Username or email", 254)
    password = data.get("password")
    if not isinstance(password, str) or len(password) > 128:
        abort(401, "Incorrect username, email, or password.")
    user = database().users.find_one({"identity_keys": identity.casefold()})
    if not user or not check_password_hash(user["password_hash"], password):
        abort(401, "Incorrect username, email, or password.")
    token = signer().dumps(str(user["_id"]))
    return jsonify(token=token, user=public_user(user))


@auth_api.get("/auth/me")
@require_user
def me():
    return jsonify(user=public_user(g.user))
