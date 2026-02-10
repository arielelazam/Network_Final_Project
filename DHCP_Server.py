import json, socket
from typing import Dict, Any

# הגדרת ה-IP וה-PORT של השרת
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767

# מאגר כתובות IP
POOL = [f"192.168.1.{i}" for i in range(50,150)]
SUBNET_MASK = "255.255.255.0"

# מבנה הנתונים שיחזיק את המידע איזו כתובת IP תפוסה ועל ידי איזה מספר לקוח
ip_to_client: Dict[str, int] = {}

#  מבנה נתונים המחזיק איזה טוקן משתמש קיבל איזה מספר
token_to_id: Dict[str, int] = {}
next_client_id = 1

# פונקציה המנסה לשלוף ממאגר הכתובות כתובת פנויה
def pick_free_ip():
    for ip in POOL:
        if ip not in ip_to_client:
            return ip
    return None

# פונקציה המקבל דיקשנרי, ממירה אותו לJSON וממירה אותו לבתים
def encode(msg: Dict[str,Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")

# פונקציה המקבלת בתים, ממירה אותם לסטרינג וממירה לJSON
def decode(data: bytes) -> dict[str,Any]:
    return json.loads(data.decode("utf-8"))

def ip_available_for_client(requested_ip: str, client_id: int) -> bool:
    owner = ip_to_client.get(requested_ip)
    return owner is None or owner == client_id

# יצירת הסוקט שיאזין לבקשות המבקשות לקבל IP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind((DHCP_IP,DHCP_PORT))
    print(f"DHCP server listening on {DHCP_IP}:{DHCP_PORT}")

    while True:
        data, addr = sock.recvfrom(4096)
        try:
            msg = decode(data)
        except Exception:
            print(f"[SERVER] got invalid JSON from {addr}: {data!r}")
            continue

        print(f"[SERVER] recv from {addr}: {msg}")

        if msg.get("type") == "DHCP_DISCOVER":
            token = msg.get("client_token")

            if not isinstance(token, str) or not token:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_TOKEN"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            if token not in token_to_id:
                token_to_id[token] = next_client_id
                next_client_id += 1

            client_id = token_to_id[token]

            offered_ip = pick_free_ip()
            if offered_ip is None:
                reply = {"type": "DHCP_NAK", "reason": "NO_FREE_IP", "client_id": client_id}
            else:
                reply = {
                    "type": "DHCP_OFFER",
                    "client_id": client_id,
                    "offered_ip": offered_ip,
                    "subnet_mask": SUBNET_MASK
                }

            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")


        elif msg.get("type") == "DHCP_REQUEST":
            token = msg.get("client_token")
            requested_ip = msg.get("requested_ip")

            if not isinstance(token, str) or not token:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_TOKEN"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            if token not in token_to_id:
                reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_CLIENT"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            if not isinstance(requested_ip, str) or not requested_ip:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_REQUESTED_IP"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            client_id = token_to_id[token]

            if requested_ip not in POOL:
                reply = {"type": "DHCP_NAK", "reason": "IP_NOT_IN_POOL", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue


            if not ip_available_for_client(requested_ip, client_id):
                reply = {"type": "DHCP_NAK", "reason": "IP_TAKEN", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            ip_to_client[requested_ip] = client_id

            reply = {
                "type": "DHCP_ACK",
                "client_id": client_id,
                "your_ip": requested_ip,
                "subnet_mask": SUBNET_MASK
            }
            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")

        else:
            reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_MESSAGE_TYPE"}
            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")
