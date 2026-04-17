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


def authenticate(p):
    request_data = dict(p)
    username = request_data.get("User-Name")
    password = request_data.get("User-Password")

    if not username or not password:
        return radiusd.RLM_MODULE_REJECT

    payload = json.dumps({"User-Name": username, "User-Password": password}).encode(
        "utf-8"
    )

    conn = None
    try:
        conn = UnixSocketConnection("/run/radiusd-timedpass/sock")
        headers = {"Content-Type": "application/json"}
        conn.request("POST", "/auth", body=payload, headers=headers)

        response = conn.getresponse()
        status = response.status

        if status == 204 or status == 200:
            return radiusd.RLM_MODULE_OK

        if status == 401 or status == 403:
            return radiusd.RLM_MODULE_REJECT

        if 500 <= status <= 599:
            radiusd.radlog(radiusd.L_ERR, f"OTP API Server Error: {status}")
            return radiusd.RLM_MODULE_FAIL

        radiusd.radlog(radiusd.L_ERR, f"OTP API Unexpected Status: {status}")
        return radiusd.RLM_MODULE_FAIL

    except Exception as e:
        radiusd.radlog(radiusd.L_ERR, f"OTP API Connection Exception: {str(e)}")
        return radiusd.RLM_MODULE_FAIL
    finally:
        if conn:
            conn.close()


def authorize(p):
    return (radiusd.RLM_MODULE_UPDATED, (), (("Auth-Type", "timedpass"),))
