import os
import secrets

import click
from flask import Flask, jsonify, render_template, request
from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError
from werkzeug.exceptions import HTTPException


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        MONGO_URI=os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017"),
        MONGO_DB=os.environ.get("MONGO_DB", "triad_dms"),
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,
        MAX_FORM_MEMORY_SIZE=256 * 1024,
        MAX_FORM_PARTS=32,
        TOKEN_AGE=8 * 60 * 60,
    )
    if test_config:
        app.config.update(test_config)

    client = MongoClient(app.config["MONGO_URI"], serverSelectionTimeoutMS=5000)
    db = client[app.config["MONGO_DB"]]
    app.extensions["db"] = db

    from .auth import auth_api, promote_user, seed_admin
    from .documents import documents_api
    from .fields import fields_api, seed_fields
    from .requests import access_api

    for blueprint in (auth_api, documents_api, fields_api, access_api):
        app.register_blueprint(blueprint, url_prefix="/api")

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        db.command("ping")
        return jsonify(status="ok")

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(PyMongoError)
    def database_error(error):
        app.logger.error("MongoDB operation failed (%s)", type(error).__name__)
        return jsonify(error="Database operation failed. Try again shortly."), 503

    @app.after_request
    def response_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.cli.command("make-admin")
    @click.argument("account")
    def make_admin(account):
        if not promote_user(db, account):
            raise click.ClickException("Account not found. Register it first.")
        click.echo("Admin role granted.")

    db.users.create_index("identity_keys", unique=True)
    db.documents.create_index([("division_key", ASCENDING), ("created_at", ASCENDING)])
    db.access_requests.create_index([("doc_id", ASCENDING), ("requester_id", ASCENDING)], unique=True)
    db.access_requests.create_index([("division_key", ASCENDING), ("status", ASCENDING)])
    db.access_requests.create_index([("requester_id", ASCENDING), ("status", ASCENDING)])
    db.fields.create_index("aliases", unique=True)
    seed_fields(db)
    seed_admin(db)
    return app
