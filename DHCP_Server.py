
import json, socket
from typing import Dict, Any

DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767


# פונקציה שמקבלת דיקשנרי הופכת אותו לגיסון וממירה אותו לבתים
def encode(msg: Dict[str,Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")

# פונקציה שמקבלת בתים הופת אותם לגיסון וממירה אותם לדיקשנרי
def decode(data: bytes) -> dict[str,Any]:
    return json.loads(data.decode("utf-8"))

# יצירת הסוקט שיאזין לבקשות המבקשות לקבל IP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind(DHCP_IP, DHCP_PORT)
    print(f"DHCP server listening on {DHCP_IP}:{DHCP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        msg = decode(data)
        print(f"DHCP Server recive from {addr}:{msg}")
