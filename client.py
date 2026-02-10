import json
import socket
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767


def encode(msg: Dict[str, Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")


def decode(data: bytes) -> Dict[str, Any]:
    return json.loads(data.decode("utf-8"))


@dataclass
class DHCPLease:
    client_name: str           # זה ה-token שלכם
    ip: str
    lease_seconds: int
    server: Tuple[str, int]


class DHCPClient:
    """
    Protocol (matching our server):
      Client -> Server: {"type":"DHCP_DISCOVER","client_name":"<token>"}
      Server -> Client: {"type":"DHCP_OFFER","client_name":"<token>","offered_ip":"...","lease_seconds":600}

      Client -> Server: {"type":"DHCP_REQUEST","client_name":"<token>","ip":"..."}
      Server -> Client: {"type":"ACK","client_id":"<token>","ip":"...","lease_seconds":600}

      (Optional NAK)
      Server -> Client: {"type":"DHCP_NAK","reason":"..."}
    """

    def __init__(
        self,
        server_ip: str = DHCP_IP,
        server_port: int = DHCP_PORT,
        timeout_sec: float = 1.0,
        retries: int = 5,
    ):
        self.server = (server_ip, server_port)
        self.timeout_sec = timeout_sec
        self.retries = retries

    def _send_and_wait(self, sock: socket.socket, out_msg: Dict[str, Any]) -> Dict[str, Any]:
        sock.sendto(encode(out_msg), self.server)

        resp_bytes, addr = sock.recvfrom(4096)
        if addr != self.server:
            raise RuntimeError(f"Unexpected responder: {addr}, expected {self.server}")

        return decode(resp_bytes)

    def acquire_lease(self, client_name: str) -> DHCPLease:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout_sec)

            # 1) DISCOVER -> expect OFFER
            offer: Optional[Dict[str, Any]] = None
            discover = {"type": "DHCP_DISCOVER", "client_name": client_name}

            for _ in range(self.retries):
                try:
                    resp = self._send_and_wait(sock, discover)

                    # אם השרת שולח NAK — נחזיר שגיאה מיידית
                    if resp.get("type") == "DHCP_NAK":
                        raise RuntimeError(f"DHCP_NAK during DISCOVER: {resp}")

                    if resp.get("type") == "DHCP_OFFER" and resp.get("client_name") == client_name:
                        offer = resp
                        break
                except socket.timeout:
                    pass

            if offer is None:
                raise TimeoutError("No DHCP OFFER received.")

            offered_ip = offer.get("offered_ip")
            lease_seconds = int(offer.get("lease_seconds", 600))

            if not isinstance(offered_ip, str) or not offered_ip:
                raise ValueError(f"Invalid OFFER: {offer}")

            # 2) REQUEST -> expect ACK
            ack: Optional[Dict[str, Any]] = None
            request = {
                "type": "DHCP_REQUEST",
                "client_name": client_name,
                "ip": offered_ip,
                "ts": time.time(),  # השרת מתעלם מזה, זה רק ללוגים
            }

            for _ in range(self.retries):
                try:
                    resp = self._send_and_wait(sock, request)

                    if resp.get("type") == "DHCP_NAK":
                        raise RuntimeError(f"DHCP_NAK during REQUEST: {resp}")

                    # תואם לשרת: type="ACK", client_id הוא הטוקן, ip הוא ה-IP המאושר
                    if (
                        resp.get("type") == "ACK"
                        and resp.get("client_id") == client_name
                        and resp.get("ip") == offered_ip
                    ):
                        ack = resp
                        break
                except socket.timeout:
                    pass

            if ack is None:
                raise TimeoutError("No DHCP ACK received.")

            lease_seconds = int(ack.get("lease_seconds", lease_seconds))

            return DHCPLease(
                client_name=client_name,
                ip=offered_ip,
                lease_seconds=lease_seconds,
                server=self.server,
            )


if __name__ == "__main__":
    client = DHCPClient(timeout_sec=1.0, retries=5)
    lease = client.acquire_lease(client_name="client-1")  # client_name הוא הטוקן
    print("LEASE:", lease)
