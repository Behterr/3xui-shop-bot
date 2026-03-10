import json
import os
from urllib.parse import quote

import httpx


def _normalize_base_path(path):
    if not path:
        return ""
    return path if path.startswith("/") else f"/{path}"


def _extract_cookie(set_cookie):
    if not set_cookie:
        return ""
    pairs = [item.split(";")[0] for item in set_cookie if item]
    return "; ".join(pairs)


class ThreeXuiClient:
    def __init__(self, base_url, web_base_path, username, password, insecure):
        self.base_url = base_url.rstrip("/")
        self.web_base_path = _normalize_base_path(web_base_path)
        self.username = username
        self.password = password
        self.cookie = ""
        self.verify = not insecure

    def api_url(self, path):
        return f"{self.base_url}{self.web_base_path}/panel/api{path}"

    def login(self):
        url = f"{self.base_url}{self.web_base_path}/login"
        response = httpx.post(
            url,
            json={"username": self.username, "password": self.password},
            verify=self.verify,
        )
        response.raise_for_status()

        cookie = _extract_cookie(response.headers.get_list("set-cookie"))
        if not cookie:
            raise RuntimeError("Login failed: no session cookie returned")
        self.cookie = cookie

    def request(self, method, path, data=None):
        if not self.cookie:
            self.login()

        url = self.api_url(path)
        response = httpx.request(
            method,
            url,
            json=data,
            headers={
                "Cookie": self.cookie,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            verify=self.verify,
        )

        if response.status_code == 401:
            self.cookie = ""
            self.login()
            return self.request(method, path, data)

        return response

    def add_client(self, inbound_id, client):
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client]})}
        return self.request("POST", "/inbounds/addClient", payload)

    def get_inbound(self, inbound_id):
        return self.request("GET", f"/inbounds/get/{inbound_id}")

    def update_client(self, client_id, inbound_id, client):
        payload = {"id": inbound_id, "settings": json.dumps({"clients": [client]})}
        return self.request("POST", f"/inbounds/updateClient/{client_id}", payload)

    def delete_client(self, inbound_id, client_id):
        return self.request("POST", f"/inbounds/{inbound_id}/delClient/{client_id}")


def build_subscription_url(template, email, uuid):
    if not template:
        return None
    return (
        template.replace("{email}", quote(email))
        .replace("{uuid}", quote(uuid))
    )
