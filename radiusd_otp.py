import base64
import grp
import hashlib
import hmac
import logging
import os
import pwd
import secrets
import socket
import struct
from flask import Flask, abort, jsonify, request
from functools import wraps
from time import time
from werkzeug.exceptions import HTTPException, Unauthorized

try:
    import valkey
except ImportError:
    import redis as valkey


class API(Flask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_error_handler(HTTPException, self.error_handler)

    def error_handler(self, e):
        return {"title": f"{e.code}: {e.name}"}, e.code


VALKEY_PREFIX = os.environ.get("VALKEY_PREFIX", "secret")
VALKEY_URL = os.environ.get("VALKEY_URL", f"{valkey.__name__}://localhost:6379")
VALKEY_TTL = int(os.environ.get("VALKEY_TTL", 30 * 24 * 60 * 60))


class UnixAuth:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        sock = environ.get("gunicorn.socket")
        if sock:
            try:
                creds = sock.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
                )
                pid, uid, gid = struct.unpack("3i", creds)
                user = pwd.getpwuid(uid)
                groups = [
                    grp.getgrgid(g).gr_name
                    for g in os.getgrouplist(user.pw_name, user.pw_gid)
                ]
                environ["REMOTE_USER"] = user.pw_name
                environ["REMOTE_GROUPS"] = groups
            except Exception:
                pass
        return self.app(environ, start_response)


def authorize(user=[], group=[]):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if len(user) > 0:
                if request.environ.get("REMOTE_USER") not in user:
                    raise Unauthorized
            if len(group) > 0:
                if request.environ.get("REMOTE_GROUPS") not in group:
                    raise Unauthorized
            return f(*args, **kwargs)

        return decorated_function

    return decorator


api = API(__name__)
api.wsgi_app = UnixAuth(api.wsgi_app)

gunicorn_logger = logging.getLogger("gunicorn.error")
api.logger.handlers = gunicorn_logger.handlers
api.logger.setLevel(gunicorn_logger.level)

db_conn = valkey.from_url(VALKEY_URL)


def generate_otp(secret, length=12, interval=60):
    counter = int(time() / interval).to_bytes(8, byteorder="big")
    hmac_hash = hmac.new(str(secret).encode(), counter, hashlib.sha256).digest()
    otp = base64.b32encode(hmac_hash).decode().replace("=", "")
    return otp[:length].lower()


def generate_secret():
    raw_bytes = secrets.token_bytes(20)
    secret = base64.b32encode(raw_bytes).decode("utf-8")
    return secret.replace("=", "")


def get_or_create_secret(username):
    try:
        secret = db_conn.get(f"secret:{username}")
    except valkey.exceptions.ConnectionError:
        api.logger.error("Connection failed to valkey server")
        abort(503)
    if not secret:
        api.logger.info(f"Creating new secret for user '{username}'")
        secret = generate_secret()
        db_conn.set(":".join([VALKEY_PREFIX, username]), secret, ex=VALKEY_TTL)
    return secret


def get_otp_for_user(username):
    try:
        pwd.getpwnam(username)
    except KeyError:
        api.logger.warning(f"Invalid username '{username}'")
        abort(400)
    secret = get_or_create_secret(username)
    otp = generate_otp(secret)
    return {
        "username": username,
        "secret": otp,
    }


@api.route("/otp")
def get_otp():
    username = request.environ.get("REMOTE_USER")
    otp = get_otp_for_user(username)
    if (
        request.accept_mimetypes.best_match(["application/json", "text/plain"])
        == "text/plain"
    ):
        return otp["secret"]
    return jsonify(otp)


@api.route("/otp/<username>")
@authorize(user="root")
def get_otp_user(username):
    return jsonify(get_otp_for_user(username))


@api.route("/whoami")
def whoami():
    username = request.environ.get("REMOTE_USER")
    return jsonify({"username": username})
