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
    client_id: str
    ip: str
    lease_seconds: int
    server: Tuple[str, int]


class DHCPClient:
    """
    DHCP-like client (simplified).
    Protocol (suggested):
      Client -> Server: {"type":"DISCOVER","client_id":"..."}
      Server -> Client: {"type":"OFFER","client_id":"...","ip":"...","lease_seconds":3600}
      Client -> Server: {"type":"REQUEST","client_id":"...","ip":"..."}
      Server -> Client: {"type":"ACK","client_id":"...","ip":"...","lease_seconds":3600}
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
        data = encode(out_msg)
        sock.sendto(data, self.server)

        resp_bytes, addr = sock.recvfrom(4096)
        if addr != self.server:
            # בפרויקט שלכם יש רק שרת אחד, אז זה יכול להיות סימן לרעש/טעות
            raise RuntimeError(f"Unexpected responder: {addr}, expected {self.server}")

        return decode(resp_bytes)

    def acquire_lease(self, client_id: str) -> DHCPLease:
        """
        Full flow: DISCOVER -> OFFER -> REQUEST -> ACK
        Raises TimeoutError if server doesn't respond.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(self.timeout_sec)

            # 1) DISCOVER -> expect OFFER
            offer: Optional[Dict[str, Any]] = None
            discover = {"type": "DISCOVER", "client_id": client_id, "ts": time.time()}

            for attempt in range(1, self.retries + 1):
                try:
                    resp = self._send_and_wait(sock, discover)
                    if resp.get("type") == "OFFER" and resp.get("client_id") == client_id:
                        offer = resp
                        break
                except socket.timeout:
                    pass  # retry

            if offer is None:
                raise TimeoutError("No DHCP OFFER received (server may not be replying yet).")

            offered_ip = offer.get("ip")
            lease_seconds = int(offer.get("lease_seconds", 3600))
            if not isinstance(offered_ip, str) or not offered_ip:
                raise ValueError(f"Invalid OFFER: {offer}")

            # 2) REQUEST -> expect ACK
            ack: Optional[Dict[str, Any]] = None
            request = {
                "type": "REQUEST",
                "client_id": client_id,
                "ip": offered_ip,
                "ts": time.time(),
            }

            for attempt in range(1, self.retries + 1):
                try:
                    resp = self._send_and_wait(sock, request)
                    if resp.get("type") == "ACK" and resp.get("client_id") == client_id and resp.get("ip") == offered_ip:
                        ack = resp
                        break
                except socket.timeout:
                    pass  # retry

            if ack is None:
                raise TimeoutError("No DHCP ACK received.")

            lease_seconds = int(ack.get("lease_seconds", lease_seconds))
            return DHCPLease(
                client_id=client_id,
                ip=offered_ip,
                lease_seconds=lease_seconds,
                server=self.server,
            )


if __name__ == "__main__":
    client = DHCPClient(timeout_sec=1.0, retries=5)
    lease = client.acquire_lease(client_id="client-1")
    print("LEASE:", lease)
