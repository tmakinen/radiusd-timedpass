import radiusd
import json
import socket
import http.client


class UnixSocketConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("localhost")
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


def authorize(p):
    request_data = dict(p)
    username = request_data.get("User-Name")

    if not username:
        return (radiusd.RLM_MODULE_REJECT, (), ())

    conn = None
    try:
        conn = UnixSocketConnection("/run/radiusd-timedpass/sock")
        headers = {"Content-Type": "application/json"}
        conn.request("GET", f"/otp/{username}", headers=headers)

        response = conn.getresponse()
        if response.status != 200:
            radiusd.radlog(radiusd.L_ERR, f"OTP API Server Error: {response.status}")
            return (radiusd.RLM_MODULE_FAIL, (), ())

        data = json.loads(response.read().decode())
        cleartext_password = data["secret"]
    except Exception as e:
        radiusd.radlog(radiusd.L_ERR, f"OTP API Connection Exception: {str(e)}")
        return (radiusd.RLM_MODULE_FAIL, (), ())
    finally:
        if conn:
            conn.close()

    if "MS-CHAP2-Response" in request_data:
        nt_hash_bytes = hashlib.new(
            "md4", cleartext_password.encode("utf-16le")
        ).digest()
        nt_hash = binascii.hexlify(nt_hash_bytes).decode("utf-8").upper()
        config = (
            ("NT-Password", nt_hash),
            ("Auth-Type", "MS-CHAP"),
        )
        return (radiusd.RLM_MODULE_OK, (), config)
    elif "User-Password" in request_data:
        config = (
            ("Cleartext-Password", cleartext_password),
            ("Auth-Type", "PAP"),
        )
        return (radiusd.RLM_MODULE_OK, (), config)
