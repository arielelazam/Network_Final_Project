import json, socket,time
from typing import Dict, Any

# הגדרת ה-IP וה-PORT של שרת ה-DHCP
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767
POOL = [f"192.168.1.{i}" for i in range(50,150)] # מאגר כתובות IP ששרת ה-DHCP מחזיק
SUBNET_MASK = "255.255.255.0"
OFFER_TIMEOUT = 10 # הזמן שנתמש בו בשביל הקצאות
LEASE_TIME = 600 # הזמן המוקצה ללקוח לשימוש בכתובת IP (שניות)

ip_to_client: Dict[str, int] = {} # מבנה הנתונים המחזיק במפתח כתובת IP כלשהי ובערך את ה-ID של הלקוח המשתמש בה

client_name_to_id: Dict[str, int] = {} # מבנה נתונים המחזיק במפתח את שם הלקוח (שאיתו הוא מזדהה) ובערך את ה-ID שהוא קיבל
next_client_id = 1 # מונה לחלוקת מספרי ID

pending_offers: Dict[int, tuple[str, float]] = {} # מבנה נתונים שיחזיק במפתח ID של משתמש ובערך יחזיק את ה-IP שהצענו לו ואת הזמן המוקצה לו

ip_leases: Dict[str, float] = {} # מבנה נתונים המחזיק במפתח כתובת IP שנמצאת בשימוש ובערך את הזמן שנותר לה להיות בשימוש

# פונקציה המנקה הצעות שפג תוקפן
def cleanup_expired_offers():
    current_time = time.time()
    expired_client_ids = []

    for cid, value in pending_offers.items():
        offered_ip, exp = value
        if exp <= current_time:
            expired_client_ids.append(cid)

    # חייבים למחוק אחרי שסיימנו לעבור על המילון
    for cid in expired_client_ids:
        del pending_offers[cid]

# פונקציה המוחקת שיוכי כתובות IP שזמן התוקף שלהן פג
def cleanup_expired_leases():
    current_time = time.time()
    expired_ips = []

    for ip, expiry in ip_leases.items():
        client_id = ip_to_client.get(ip)
        print(f"Lease expired for IP {ip} (client_id: {client_id})")
        del ip_leases[ip]
        if ip in ip_to_client:
            del ip_to_client[ip]

# פונקציה המנסה לשלוף ממאגר הכתובות כתובת פנויה
def pick_free_ip():
    current_time = time.time()
    reserved_ips = {ip for (ip, exp) in pending_offers.values() if exp > current_time}

    for ip in POOL:
        if ip in ip_to_client:
            continue
        if ip in reserved_ips:
            continue
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
        cleanup_expired_offers() # ביצוע ניקוי להצעות שפג תוקפן
        cleanup_expired_leases() # ביצוע ניקוי לכתובות שפג תוקפן והחזרתן למאגר
        data, addr = sock.recvfrom(4096) # קבלת הבקשה
        try:
            msg = decode(data) # המרת ההודעה מ-JSON
        except Exception:
            print(f"SERVER got invalid JSON from {addr}: {data!r}")
            continue

        print(f"SERVER receive from {addr}: {msg}")

        if msg.get("type") == "DHCP_DISCOVER": # אם הלקוח מבקש לקבל כתובת IP כלשהי
            client_name = msg.get("client_name") # נשמור את שם הלקוח

            # אם לא התקבל שם משתמש כמחרוזת או שלא התקבל בכלל נחזיר הודעת שגיאה ללקוח
            if not isinstance(client_name, str) or not client_name:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_NAME"}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
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
                pending_offers[client_id] = (offered_ip, time.time() + OFFER_TIMEOUT)
                reply = {
                    "type": "DHCP_OFFER",
                    "client_id": client_id,
                    "offered_ip": offered_ip,
                    "subnet_mask": SUBNET_MASK,
                    "offer_timeout": OFFER_TIMEOUT
                }

            sock.sendto(encode(reply), addr)
            print(f"[SERVER] sent to {addr}: {reply}")


        elif msg.get("type") == "DHCP_REQUEST": # אם הלקוח מעוניין לקבל את הכתובת
            client_name = msg.get("client_name") # נשמור את שם הלקוח
            requested_ip = msg.get("requested_ip") # נשמור את כתובת ה-IP שהוא מעוניין לקבל

            # אם הלקוח שלך שם לא תקין או לא שלח שם נחזיר הודעת שגיאה
            if not isinstance(client_name, str) or not client_name:
                reply = {"type": "DHCP_NAK", "reason": "MISSING_CLIENT_NAME"}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

            # אם שם הלקוח לא במאגר השמות נחזיר שגיאה
            if client_name not in client_name_to_id:
                reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_CLIENT"}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

            client_id = client_name_to_id[client_name]  # נשמור את ה-ID של הלקוח

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

            offer = pending_offers.get(client_id)

            # אם לא שוריינה ללקוח אף כתובת, נחזיר שגיאה
            if offer is None:
                reply = {"type": "DHCP_NAK", "reason": "NO_PENDING_OFFER", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

            offered_ip, expiry_time = offer

            # אם הלקוח מעוניין בכתובת אבל פג הזמן, נחזיר שגיאה
            if time.time() > expiry_time:
                del pending_offers[client_id]
                reply = {"type": "DHCP_NAK", "reason": "OFFER_EXPIRED", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

            # אם הלקוח מעוניין לקבל כתובת אחרת ממה שהצענו לו, נחזיר שגיאה
            if requested_ip != offered_ip:
                del pending_offers[client_id]
                reply = {"type": "DHCP_NAK", "reason": "REQUEST_NOT_MATCH_OFFER", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

           # אם הלקוח לא רשאי לקבל את הכתובת שהוא מבקש (למשל אם היא שייכת כבר למישהו אחר), נחזיר שגיאה
            if not ip_available_for_client(requested_ip, client_id):
                del pending_offers[client_id]
                reply = {"type": "DHCP_NAK", "reason": "IP_TAKEN", "client_id": client_id}
                sock.sendto(encode(reply), addr)
                print(f"SERVER sent to {addr}: {reply}")
                continue

            ip_to_client[requested_ip] = client_id # נאשר למשתמש לקבל את כתובת ה-IP שהוא ביקש ונגדיר שהיא שייכת לו
            ip_leases[requested_ip] = time.time() + LEASE_TIME # נשמור את הזמן שיש למשתמש עם כתובת ה-IP שנתנו לו
            del pending_offers[client_id] # נמחק אותו מרשימת הבקשות הממתינות

            # נחזיר ללקוח הודעת ACK המאשרת לו שהוא קיבל את הכתובת, יתר הנתונים ואת הזמן שיש לו להשתמש בכתובת (בשניות)
            reply = {
                "type": "DHCP_ACK",
                "client_id": client_id,
                "your_ip": requested_ip,
                "subnet_mask": SUBNET_MASK,
                "lease_seconds": 600
            }
            sock.sendto(encode(reply), addr)
            print(f"SERVER sent to {addr}: {reply}")

        else:
            reply = {"type": "DHCP_NAK", "reason": "UNKNOWN_MESSAGE_TYPE"}
            sock.sendto(encode(reply), addr)
            print(f"SERVER sent to {addr}: {reply}")