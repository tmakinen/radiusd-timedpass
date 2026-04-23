import base64
import grp
import gunicorn.app.base
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


class StandaloneApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        config = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


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


def get_uid_range():
    with open("/etc/login.defs", "r") as fp:
        for line in fp.readlines():
            line = line.split()
            try:
                if line[0] == "UID_MIN":
                    uid_min = int(line[1])
                elif line[0] == "UID_MAX":
                    uid_max = int(line[1])
            except IndexError:
                pass
    return (uid_min, uid_max)


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
    except valkey.exceptions.ConnectionError as e:
        api.logger.error(f"Connection failed to valkey server: {e}")
        abort(503)
    if not secret:
        api.logger.info(f"Creating new secret for user '{username}'")
        secret = generate_secret()
        db_conn.set(":".join([VALKEY_PREFIX, username]), secret, ex=VALKEY_TTL)
    return secret


def get_otp_for_user(username):
    try:
        user = pwd.getpwnam(username)
    except KeyError:
        api.logger.warning(f"Invalid username '{username}'")
        abort(400)
    (uid_min, uid_max) = get_uid_range()
    if uid_min > user.pw_uid < uid_max:
        api.logger.warning(f"User '{username}' not allowed, UID not in range")
        abort(400)
    secret = get_or_create_secret(username)
    otp = generate_otp(secret)
    return {
        "username": username,
        "secret": otp,
    }


@api.route("/auth", methods=["POST"])
def authenticate():
    data = request.get_json()
    if not data:
        api.logger.warning("No data provided in request")
        abort(400)
    try:
        username = data["User-Name"]
        password = data["User-Password"]
    except KeyError:
        api.logger.warning("Missing username or password")
        abort(400)

    secret = get_or_create_secret(username)
    otp = generate_otp(secret)
    if otp == password:
        return "", 204
    else:
        api.logger.warning(f"Authentication failed for user {username}")
        abort(401)


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
@authorize(user="radiusd")
def get_otp_user(username):
    return jsonify(get_otp_for_user(username))


@api.route("/whoami")
def whoami():
    username = request.environ.get("REMOTE_USER")
    return jsonify({"username": username})


if __name__ == "__main__":
    socket_path = os.environ.get("SOCKET_PATH", "/run/radiusd-timedpass/sock")
    options = {
        "accesslog": "-",
        "bind": f"unix:{socket_path}",
        "workers": int(os.environ.get("GUNICORN_WORKERS", 4)),
    }
    StandaloneApplication(api, options).run()
