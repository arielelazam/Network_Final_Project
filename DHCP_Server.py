import json, socket
from typing import Dict, Any

# הגדרת ה-IP וה-PORT של שרת ה-DHCP
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767

# מאגר כתובות IP ששרת ה-DHCP מחזיק
POOL = [f"192.168.1.{i}" for i in range(50,150)]
SUBNET_MASK = "255.255.255.0"

# מבנה הנתונים המחזיק במפתח כתובת IP כלשהי ובערך את ה-ID של הלקוח המשתמש בה
ip_to_client: Dict[str, int] = {}

# מבנה נתונים המחזיק במפתח את שם הלקוח (שאיתו הוא מזדהה) ובערך את ה-ID שהוא קיבל
client_name_to_id: Dict[str, int] = {}
next_client_id = 1

# פונקציה המנסה לשלוף ממאגר הכתובות כתובת פנויה
def pick_free_ip():
    for ip in POOL:
        if ip not in ip_to_client:
            return ip
    return None

# פונקציה המקבל דיקשנרי, ממירה אותו ל-JSON וממירה אותו לבתים
def encode(msg: Dict[str,Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")

# פונקציה המקבלת בתים, ממירה אותם לסטרינג וממירה ל-JSON
def decode(data: bytes) -> dict[str,Any]:
    return json.loads(data.decode("utf-8"))

# פונקציה הבודקת האם כתובת IP מסויימת יכולה או לא יכולה להשתייך למשתמש המבקש אותה
def ip_available_for_client(requested_ip: str, client_id: int) -> bool:
    owner_id = ip_to_client.get(requested_ip)
    return owner_id is None or owner_id == client_id

# יצירת הסוקט שיאזין לבקשות המבקשות לקבל IP
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
    sock.bind((DHCP_IP,DHCP_PORT))
    print(f"DHCP server listening on {DHCP_IP}:{DHCP_PORT}")

    while True:
        data, addr = sock.recvfrom(4096) # קבלת הבקשה
        try:
            msg = decode(data) # המרת ההודעה מ-JSON
        except Exception:
            print(f"[SERVER] got invalid JSON from {addr}: {data!r}")
            continue

        print(f"[SERVER] recv from {addr}: {msg}")

        if msg.get("type") == "DHCP_DISCOVER": # אם הלקוח מבקש לקבל כתובת IP כלשהי
            client_name = msg.get("client_name") # נשמור את שם הלקוח

            # אם לא התקבל שם משתמש כמחרוזת או שלא התקבל בכלל נחזיר הודעה ללקוח
            if not isinstance(client_name, str) or not client_name:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_TOKEN"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            #נבצע בדיקה האם שם הלקוח לא מחזיק בכתובת IP כלשהי ואם הוא לא, נקצה לו ID ונזכור שהוא מחזיק ב-ID הזה
            if client_name not in client_name_to_id:
                client_name_to_id[client_name] = next_client_id
                next_client_id += 1

            client_id = client_name_to_id[client_name]

            # נחפש כתובת IP פנויה מהמאגר, אם לא מצאנו, נעדכן את הלקוח שאין
            # אם מצאנו, נחזיר דיקשנרי המכיל את סוג הדיקשנרי, את ה-ID שנתנו ללקוח, את הכתובת המוצעת, ואת ה-subnet_mask
            offered_ip = pick_free_ip()
            if offered_ip is None:
                reply = {"type": "DHCP_NAK", "reason": "NO_FREE_IP", "client_id": client_id}
            else:
                reply = {
                    "type": "DHCP_OFFER",
                    "client_id": client_id,
                    "offered_ip": offered_ip,
                    "subnet_mask": SUBNET_MASK,
                }

            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")


        elif msg.get("type") == "DHCP_REQUEST": # אם הלקוח מעוניין לקבל את הכתובת
            client_name = msg.get("client_name") # נשמור את שם הלקוח
            requested_ip = msg.get("requested_ip") # נשמור את כתובת ה-IP שהוא מעוניין לקבל

            # אם הלקוח שלך שם לא תקין או לא שלח שם נחזיר הודעת שגיאה
            if not isinstance(client_name, str) or not client_name:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_TOKEN"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            # אם שם הלקוח לא במאגר השמות נחזיר שגיאה
            if client_name not in client_name_to_id:
                reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_CLIENT"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            # אם הכתובת המבוקשת לא חוקית או לא קיימת, נחזיר שגיאה
            if not isinstance(requested_ip, str) or not requested_ip:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_REQUESTED_IP"}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            # אם הכתובת המבוקשת היא לא אחת מהכתובות האפשרויות, נחזיר שגיאה
            if requested_ip not in POOL:
                reply = {"type": "DHCP_NAK", "reason": "IP_NOT_IN_POOL", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            client_id = client_name_to_id[client_name] # נשמור את ה-ID של הלקוח

           # אם הלקוח לא רשאי לקבל את הכתובת שהוא מבקש, נחזיר שגיאה
            if not ip_available_for_client(requested_ip, client_id):
                reply = {"type": "DHCP_NAK", "reason": "IP_TAKEN", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"[SERVER] sent to {addr}: {reply}")
                continue

            ip_to_client[requested_ip] = client_id # נאשר למשתמש לקבל את כתובת ה-IP שהוא ביקש ונגדיר שהיא שייכת לו

            # נחזיר ללקוח הודעת ACK המאשרת לו שהוא קיבל את הכתובת, יתר הנתונים ואת הזמן שיש לו להשתמש בכתובת (בשניות)
            reply = {
                "type": "DHCP_ACK",
                "client_id": client_id,
                "your_ip": requested_ip,
                "subnet_mask": SUBNET_MASK,
                "lease_seconds": "600"
            }
            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")

        else:
            reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_MESSAGE_TYPE"}
            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")
