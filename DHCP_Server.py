
import json, socket
from typing import Dict, Any

DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767

# מאגר כתובות IP
POOL = [f"192.168.1.{i}" for i in range(50,150)]
SUBNET_MASK = "255.255.255.0"

# מבנה הנתונים שיחזיק את המידע, איזו כתובת תפוסה ועל ידי מי
ip_to_client: Dict[str,str] = {}

# מבנה נתונים ה
token_to_id: Dict[str, int] = {}
next_client_id = 1

def pick_free_ip():
    for ip in POOL:
        if ip not in ip_to_client:
            return ip
        return None
# פונקציה שמקבלת דיקשנרי הופכת אותו לגיסון וממירה אותו לבתים
def encode(msg: Dict[str,Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")

# פונקציה שמקבלת בתים הופת אותם לגיסון וממירה אותם לדיקשנרי
def decode(data: bytes) -> dict[str,Any]:
    return json.loads(data.decode("utf-8"))

# יצירת הסוקט שיאזין לבקשות המבקשות לקבל IP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind((DHCP_IP,DHCP_PORT))
    print(f"DHCP server listening on {DHCP_IP}:{DHCP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        try:
            msg = decode(data)
        except Exception:
            print(f"DHCP Server didn't found free IP")
            continue
        print(f"DHCP Server recv from {addr}:{msg}")

        if msg.get("type") == "DHCP_DISCOVER":
            token = msg.get("client_token")

            if not isinstance(token, str) or not token:
                reply = {
                    "type": ""
                }

            reply = {
                "type": "DHCP_OFFER",
                "message": "I can "
            }
