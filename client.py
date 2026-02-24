import json, ssl, socket, os, time


# הגדרות שרת האפליקציה
APP_DOMAIN = "app.local"
APP_TCP_PORT = 9000

MAX_CHUNK_SIZE = 60000

# סוגי הודעות UDP
MSG_DATA = 1       # חתיכת נתונים
MSG_ACK = 2        # אישור קבלה
MSG_SEG_REQ = 3    # בקשת סגמנט
MSG_FIN = 4        # סיום

# תיקייה לשמירת סגמנטים שהורדו
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(SCRIPT_DIR, "downloads")

# הגדרות DHCP
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767
CLIENT_NAME = "my_client"

# הגדרות DNS (שנדע ממי לבקש בקשות DNS)
DNS_Server_IP = "127.0.0.2"
DNS_Server_PORT = 5300
ENCODING = "utf-8"

CERT_FILE = "server.crt" # תעודת הזדהות של השרת

BUFFER_SIZE = 4096 # כמה לקרוא בכל פעם
REQUEST_TIMEOUT = 5 # כמה שניות לחכות

# רשומות DNS
RECORD_TYPES = {
    "A" : 1,        # IPv4
    "AAAA" : 28,    # IPv6
    "CNAME" : 5,    # תן לי את השם האמיתי(הפניה משם אחד לאחר)
    "MX" : 15,      # שרת המייל של הדומיין
    "TXT" : 16,     # רשומת טקסט
    "NS" : 2        # שרת השמות שאחראי על הדומיין
}

# מיפוי הפוך(מקבלים מספר -> שם)
RECORD_TYPE_NAMES = {v : k for k, v in RECORD_TYPES.items()}


# ------ פונקציות DHCP (UDP) ------

# ממיר דיקשנרי ל-JSON ואז לבתים לשליחה ב-UDP
def dhcp_encode(msg: dict) -> bytes:
    return json.dumps(msg).encode(ENCODING)

# ממיר בתים שהתקבלו ב-UDP חזרה לדיקשנרי
def dhcp_decode(data: bytes) -> dict:
    return json.loads(data.decode(ENCODING))


def dhcp_discover_and_request() -> dict:
    result = {}

    # יצירת סוקט UDP לתקשורת עם שרת DHCP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(REQUEST_TIMEOUT)

    try:
        #  שלב 1: DISCOVER (הקליינט מבקש כתובת)
        print("[DHCP] Sending DHCP_DISCOVER...")
        discover_msg = {
            "type": "DHCP_DISCOVER",
            "client_name": CLIENT_NAME
        }
        sock.sendto(dhcp_encode(discover_msg), (DHCP_IP, DHCP_PORT))

        # שלב 2: DHCP_OFFER (השרת מציע כתובת)
        data, addr = sock.recvfrom(BUFFER_SIZE)
        offer = dhcp_decode(data)

        if offer.get("type") != "DHCP_OFFER":
            print(f"[DHCP] ERROR: Expected DHCP_OFFER, got: {offer.get('type')}")
            if offer.get("reason"):
                print(f"[DHCP] Reason: {offer.get('reason')}")
            return result

        offered_ip = offer.get("offered_ip")
        client_id = offer.get("client_id")
        subnet_mask = offer.get("subnet_mask")
        print(f"[DHCP] Got OFFER: IP={offered_ip}, client_id={client_id}, mask={subnet_mask}")

        #שלב 3: DHCP_REQUEST (הקליינט מאשר שרוצה את הכתובת)
        print(f"[DHCP] Sending DHCP_REQUEST for {offered_ip}...")
        request_msg = {
            "type": "DHCP_REQUEST",
            "client_name": CLIENT_NAME,
            "requested_ip": offered_ip
        }
        sock.sendto(dhcp_encode(request_msg), (DHCP_IP, DHCP_PORT))

        # שלב 4: DHCP_ACK (השרת מאשר סופית)
        data, addr = sock.recvfrom(BUFFER_SIZE)
        ack = dhcp_decode(data)

        if ack.get("type") != "DHCP_ACK":
            print(f"[DHCP] ERROR: Expected DHCP_ACK, got: {ack.get('type')}")
            if ack.get("reason"):
                print(f"[DHCP] Reason: {ack.get('reason')}")
            return result

        print(f"[DHCP] Got ACK: IP={ack.get('your_ip')}, lease={ack.get('lease_seconds')}s")
        result = ack

    except socket.timeout:
        print("[DHCP] ERROR: Timeout - DHCP server is not responding.")
    except ConnectionError as e:
        print(f"[DHCP] ERROR: Connection error: {e}")
    except Exception as e:
        print(f"[DHCP] ERROR: {e}")
    finally:
        sock.close()

    return result


#------ פונקציות DNS (DoH) ------

def setup_ssl():
    """
    מגדיר SSL context עבור DoH.
    דורש תעודת SSL (server.crt) שנוצרת כששרת ה-DNS עולה.
    מחזיר את ה-ssl_context.
    """
    if not os.path.exists(CERT_FILE):
        print(f"[DNS] ERROR: Certificate file '{CERT_FILE}' not found!")
        print(f"[DNS] The DNS server creates this file when it starts.")
        print(f"[DNS] Please run DNS_Server.py first, then try again.")
        return None

    # התעודה קיימת - טוענים רק אותה בלבד(בודק את התעודה)
    ctx = ssl.create_default_context(cafile=CERT_FILE)
    ctx.check_hostname = False # סומך על בדיקת התעודה ולא על hostname
    print(f"[SSL] Certificate loaded successfully from {CERT_FILE}")
    return ctx

#
def send_https_request(path, ssl_context):
    #שלב 1: יצירת סוקט
    raw_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_socket.settimeout(REQUEST_TIMEOUT)

    # שלב 2: עטיפה ב - SSL(הצפנה)
    secure_socket = ssl_context.wrap_socket(raw_socket, server_hostname=DNS_Server_IP)

    # שלב 3: התחברות לשרת(TCP)
    try:
        secure_socket.connect((DNS_Server_IP,DNS_Server_PORT))

        # בניית בקשה HTTP GET ידנית
        http_request = (
            f"GET {path} HTTP/1.1\r\n"                         # השיטה - GET, הנתיב - {path}, גרסת הפרוטוקול HTTP/1.1 (שורת הבקשה)
            f"Host: {DNS_Server_IP}:{DNS_Server_PORT}\r\n"     # אומר לשרת באיזה כתובת הוא פנה איליו(של השרת). כי שרת יכול לארח כמה אתרים
            f"Accept: application/dns-json\r\n"                # איזה פורמט אנחנו רוצים את התשובה(אצלנו זה JSON)
            f"Connection: close\r\n"                           # אומרת לשרת לסגור את החיבור אחרי התשובה(ב TCP הוא יכול להשאיר פתוח ולחכות לעוד הודעות)
            f"\r\n"                                            #ב http חובה להשאיר שורה ריקה
        )

        # שליחת הבקשה דרך החיבור המוצפן
        secure_socket.sendall(http_request.encode(ENCODING))

        # קראית התשובה מהשרת
        response_data = b"" # מתחילים ממחרוזרת בתים ריקה וצוברים אליה את כל החתיכות
        while True:
            chunk = secure_socket.recv(BUFFER_SIZE)
            if not chunk: # השרת סיים לשלוח וסגר את החיבור
                break
            response_data += chunk

        # הפרדה בין הכותרות לגוף HTTP
        raw_text = response_data.decode(ENCODING)
        header_part, body_part = raw_text.split("\r\n\r\n", 1)

        # המרת הגוף מ- JSON ל- dictionary
        return json.loads(body_part)

    except socket.timeout:
        print("ERROR Connection timed out - the server is not responding.")
        return None
    except ConnectionError:
        print("ERROR Connection refused - is the DNS server running?")
        return None
    except Exception as e:
        print(f"ERROR {e}")
        return None
    finally:
        secure_socket.close()

# שולחת שאילתת DNS לשרת ומדפיסה את התוצאות
def dns_query(domain, record_type, ssl_context):
    # בדיקה שסוג הרשומה תקין
    if record_type not in RECORD_TYPES:
        print(f"ERROR Unknown record type '{record_type}'.")
        print(f"Available types: {', '.join(RECORD_TYPES.keys())}")
        return

    # בניית הנתיב לבקשה
    path = f"/dns-query?name={domain}&type={record_type}"
    print(f"\nQUERY {domain} ({record_type})")
    print(f" sending: GET {path}")

    # שליחת הקשה וקבלת התשובה
    result = send_https_request(path, ssl_context)

    # בדיקה אם קיבלנו תשובה
    if result is None:
        print("No response from server.")
        return

    # בדיקת סטטוס התשובה( הצלחה = 0, דומיין לא נמצא = 3)
    # get(מה להחזיר אם לא מצאנו, מה מחפשים)
    status = result.get("Status", -1)
    if status != 0:
        error = result.get("error", "UNKNOWN")
        print(f" Server returned error: {error} (Status: {status})")
        return

    # הדפסת התוצאות
    answers = result.get("Answer", [])       # שולף את רשחמת התשובות(אם אין מפתח מחזיר רשימה ריקה)
    source = result.get("source", "unknown") # שולף מאיפה הגיעה התשובה(אם אין מקור מחזיר unknown)
    print(f" Source: {source} | {len(answers)} record found") # מדפיס כמה רשומות חזרו ואת המקור

    for record in answers:
        rtype_name = RECORD_TYPE_NAMES.get(record.get("type"), "?") # מחפש את 1(A)(אם המספר לא קיים הוא מחזיר ?)
        ttl = record.get("TTL", 0)
        data = record.get("data", "")
        print(f"{record.get('name')} -> {data} [{rtype_name}, TTL: {ttl}s]")


# ------ פונקציות לשרת האפליקציה ------


# קודם שולח 4 בתים עם אורך ההודעה, ואז את ההודעה עצמה
def tcp_send(sock: socket.socket, msg: dict):
    # ממיר את המילון ל-JSON ואז לבתים
    data = json.dumps(msg).encode(ENCODING)
    # שולח את האורך כ-4 בתים (big endian) ואז את הנתונים
    sock.sendall(len(data).to_bytes(4, "big") + data)


# קודם קורא 4 בתים של אורך, ואז קורא בדיוק את הכמות הזו
def tcp_recv(sock: socket.socket) -> dict:
    # קורא 4 בתים שמייצגים את אורך ההודעה
    length_bytes = sock.recv(4)
    if not length_bytes:
        return {}  # החיבור נסגר

    # ממיר את 4 הבתים למספר
    length = int.from_bytes(length_bytes, "big")

    # קורא בדיוק length בתים (ההודעה עצמה)
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            return {}  # החיבור נסגר באמצע
        data += chunk

    # ממיר מבתים ל-JSON ומחזיר כמילון
    return json.loads(data.decode(ENCODING))


# בונה חבילת UDP מ-Header + Data
# מחזיר בתים מוכנים לשליחה
def build_packet(msg_type: int, seq: int = 0, ack: int = 0,
                 window: int = 0, flags: int = 0, data: bytes = b"") -> bytes:
    # בונה את ה-Header: סוג (1B) + דגלים (1B) + חלון (2B) + רצף (4B) + אישור (4B)
    header = (
        msg_type.to_bytes(1, "big") +
        flags.to_bytes(1, "big") +
        window.to_bytes(2, "big") +
        seq.to_bytes(4, "big") +
        ack.to_bytes(4, "big")
    )
    # מחבר Header + Data לחבילה אחת
    return header + data


# פורק חבילת UDP - מפריד Header מ-Data
# מחזיר מילון עם כל השדות
def parse_packet(packet: bytes) -> dict:
    return {
        "type":   packet[0],                                      # בית 0: סוג ההודעה
        "flags":  packet[1],                                      # בית 1: דגלים
        "window": int.from_bytes(packet[2:4], "big"),     # בתים 2-3: גודל חלון
        "seq":    int.from_bytes(packet[4:8], "big"),     # בתים 4-7: מספר רצף
        "ack":    int.from_bytes(packet[8:12], "big"),    # בתים 8-11: מספר אישור
        "data":   packet[12:]                                     # בית 12 והלאה: הנתונים
    }


# שולח שאילתת DNS ומחזיר את ה-IP כמחרוזת

def resolve_domain(domain: str, ssl_context) -> str:
    print(f"[DNS] Resolving {domain}...")

    #שולח שאילתת DNS - שימוש בפונקציה קיימת(send_https_request)
    result = send_https_request(f"/dns-query?name={domain}&type=A", ssl_context)

    # בדיקה שקיבלנו תשובה עם IP
    if not result or result.get("Status") != 0 or not result.get("Answer"):
        print(f"[DNS] ERROR: Could not resolve {domain}")
        return ""

    # שולף את ה-IP מהתשובה הראשונה(במקרה ויש כמה)
    ip = result["Answer"][0].get("data", "")
    print(f"[DNS] {domain} -> {ip}")
    return ip

# מתחבר לשרת ב TCP
# 1. שולח LIST ומקבל רשימת סרטים
# 2. מציג למשתמש את הרשימה
# 3. המשתמש בוחר סרט
# 4. שולח SELECT ומקבל אישור עם פרטי UDP
def app_browse_and_select(server_ip: str) -> dict:
    # יצירת סוקט (TCP)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(REQUEST_TIMEOUT)

    try:
        # התחברות לשרת האפליקציה (ערוץ בקרה)
        print(f"APP -> Connecting to {server_ip}:{APP_TCP_PORT}...")
        sock.connect((server_ip, APP_TCP_PORT))
        print(f"APP -> Connected!")

        # שלב 1: שולח LIST - מבקש רשימת סרטים
        tcp_send(sock, {"type": "LIST"})
        response = tcp_recv(sock)
        # בדיקה שקיבלנו תשובה מהסוג הנכון
        if response.get("type") != "LIST_RESPONSE":
            print(f"[APP] ERROR: Expected LIST_RESPONSE, got: {response.get('type')}")
            return {}

        # שליפת מילון הסרטים מהתשובה
        movies = response.get("movies", {})

        # הצגת הסרטים למשתמש
        print(f"\n{'=' * 40}")
        print(f"Available Movies ({len(movies)}):")
        print(f"{'=' * 40}")
        for name, info in movies.items():
            # מספר סגמנטים בסרט
            segs = info["segments"]
            # אורך כולל בשניות
            dur = info["total_duration_sec"]
            # הדפסה של שם פנימי + כותרת + משך + מספר סגמנטים
            print(f"{name}: {info['title']} ({dur}s, {segs} segments)")
        print(f"{'=' * 40}")

        # קלט מהמשתמש - איזה סרט לבחור
        choice = input("\nChoose movie: ").strip()

        # בדיקה שהבחירה קיימת
        if choice not in movies:
            print(f"APP -> ERROR: '{choice}' not found")
            return {}

        # בקשת SELECT - מודיעים לשרת איזה סרט נבחר
        tcp_send(sock, {"type": "SELECT", "movie": choice})

        # קבלת תשובת אישור מהשרת
        response = tcp_recv(sock)

        # בדיקה שהשרת אישר את הבחירה
        if response.get("type") != "SELECT_OK":
            print(f"APP -> ERROR: {response.get('reason', 'Unknown error')}")
            return {}

        # לוגים לסיכום הבחירה
        print(f"APP -> Selected: {choice}")
        print(f"APP -> Segments: {response['total_segments']}, UDP port: {response['udp_port']}")

        # החזרת התשובה (בה יש total_segments, udp_port, וכו')
        return response

    except socket.timeout:
        print("APP -> ERROR: Connection timed out")
        return {}
    except ConnectionError:
        # השרת לא זמין/לא קיבל חיבור
        print("APP -> ERROR: Could not connect to app server")
        return {}
    except Exception as e:
        # כל שגיאה אחרת
        print(f"APP -> ERROR: {e}")
        return {}
    finally:
        # בכל מקרה סוגרים את הסוקט
        sock.close()

#הורדת סגמנט בודד מהשרת
#1. שולחת לשרת בקשת SEG_REQ(איזה סרט, איזה סגמנט, איזה איכות)
# 2. מקבלת חבילות DATA בלולאה
# 3. שומרת את החתיכות לפי seq כדי לשמור סדר נכון
# 4. עוצרת כשמגיעה חתיכה עם flags=1 (אחרונה)
# 5. מחברת את כל החתיכות לקובץ MP4 ושומרת ב - downloads
def download_one_segment_udp(server_ip: str, udp_port: int, movie: str, seg_num: int, quality: str) -> tuple: # tuple - רשימה שאי אפשר לשנות אותה
    # יוצר סוקט UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # timeout כדי לא להיתקע אם השרת לא עונה
    sock.settimeout(REQUEST_TIMEOUT)

    # זמן התחלה למדידת מהירות הורדה
    t0 = time.time()

    try:
        # בקשת SEG_REQ
        req = {
            "movie": movie,       # שם הסרט
            "segment": seg_num,   # מספר סגמנט
            "quality": quality    # איכות מבוקשת
        }

        # בונה חבילת UDP מסוג SEG_REQ עם ה-JSON בתוך data
        req_packet = build_packet(
            msg_type=MSG_SEG_REQ,
            data=json.dumps(req).encode(ENCODING)
        )

        # שולח את הבקשה לשרת
        sock.sendto(req_packet, (server_ip, udp_port))

        # מילון זמני: seq -> chunk(כדי להרכיב בסוף בסדר הנכון)
        parts = {}

        # נשמור את מספר החתיכה האחרונה כשהיא תגיע
        last_seq = None

        while True:
            # מקבל חבילה מהשרת
            raw, _ = sock.recvfrom(MAX_CHUNK_SIZE + 64)  # קצת יותר מ-chunk עבור header
            pkt = parse_packet(raw)

            # מתעלם מכל מה שהוא לא DATA
            if pkt["type"] != MSG_DATA:
                continue

            # מספר הרצף של החתיכה
            seq = pkt["seq"]

            # שומר את החתיכה במילון לפי seq
            parts[seq] = pkt["data"]

            # אם flags=1 זו החתיכה האחרונה
            if pkt["flags"] == 1:
                last_seq = seq

            # תנאי עצירה:
            # אם כבר קיבלנו last_seq, ובפועל יש לנו את כל החתיכות מ-0 עד last_seq
            if last_seq is not None:
                if len(parts) == (last_seq + 1):
                    break

        # מרכיב את הנתונים לפי סדר seq
        ordered = [parts[i] for i in range(last_seq + 1)]
        segment_data = b"".join(ordered)

        # מבטיח שתיקיית היעד קיימת
        movie_dir = os.path.join(DOWNLOADS_DIR, movie)
        os.makedirs(movie_dir, exist_ok=True)

        # שם קובץ לשמירה מקומית
        out_path = os.path.join(movie_dir, f"seg_{seg_num:03d}.mp4")

        # שומר את הסגמנט לדיסק
        with open(out_path, "wb") as f:
            f.write(segment_data)

        # זמן כולל להורדת הסגמנט
        elapsed = time.time() - t0

        print(f"UDP -> Saved: {out_path} ({len(segment_data)} bytes, {elapsed:.2f}s)")
        # מחזירה - האם הצליח, כמה זמן לקח וכמה בתים ירדו
        return True, elapsed, len(segment_data)

    except socket.timeout:
        print(f"UDP -> ERROR: timeout on segment {seg_num}")
        return False, 0, 0
    except Exception as e:
        print(f"UDP -> ERROR on segment {seg_num}: {e}")
        return False, 0, 0
    finally:
        # סוגר סוקט
        sock.close()

# מחליט איזו איכות לבקש בסגמנט הבא
# throughput_bps = bytes per second
def choose_quality(throughput_bps: float) -> str:
    # רשת מהירה - איכות גבוהה
    if throughput_bps >= 1_500_000:
        return "HIGH"

    # רשת בינונית - איכות בינונית
    if throughput_bps >= 600_000:
        return "MEDIUM"

    # רשת איטית - איכות נמוכה
    return "LOW"

# מוריד את כל הסגמנטים של סרט אחד
# משתמש בהתאמת איכות דינמית (DASH)
def download_movie_segments(server_ip: str, select_info: dict):
    # פרטי הסרט מתוך SELECT_OK
    movie = select_info["movie"]
    total_segments = select_info["total_segments"]
    udp_port = select_info["udp_port"]

    print(f"\n[APP] Starting download for '{movie}'")
    print(f"[APP] Total segments: {total_segments}")

    # איכות התחלתית (נייטרלית)
    current_quality = "MEDIUM"

    # סטטיסטיקות לסיכום
    total_bytes = 0
    total_time = 0.0

    # הורדה של כל הסגמנטים אחד-אחד
    for seg_num in range(total_segments):
        print(f"\nAPP -> Segment {seg_num}/{total_segments - 1} | quality={current_quality}")

        # הורדת סגמנט בודד
        ok, elapsed, size_bytes = download_one_segment_udp(
            server_ip=server_ip,
            udp_port=udp_port,
            movie=movie,
            seg_num=seg_num,
            quality=current_quality
        )

        # אם נכשל - עוצרים
        if not ok:
            print(f"APP -> Stopping: failed to download segment {seg_num}")
            return

        # עדכון סטטיסטיקות
        total_bytes += size_bytes
        total_time += elapsed

        # חישוב throughput לסגמנט הנוכחי (bytes/sec)
        throughput = size_bytes / elapsed if elapsed > 0 else 0
        print(f"APP -> Throughput: {throughput:,.0f} B/s")

        # בחירת איכות לסגמנט הבא
        current_quality = choose_quality(throughput)

    # סיכום הורדה
    avg_throughput = total_bytes / total_time if total_time > 0 else 0
    print(f"\n{'='*50}")
    print(f"APP -> Download complete!")
    print(f"APP -> Movie: {movie}")
    print(f"APP -> Bytes: {total_bytes:,}")
    print(f"APP -> Time: {total_time:.2f}s")
    print(f"APP -> Avg throughput: {avg_throughput:,.0f} B/s")
    print(f"{'='*50}")

# ----- בניית תפריט שיבחר שאלת DNS או בקשה משרת האפליקציה ----

# מצב DNS ידני: המשתמש שואל כמה שאלות שרוצה עד exit
def dns_interactive_mode(ssl_context):
    print("\n--- DNS Interactive Mode ---")
    print("=" * 50)
    print(f"Available types: {', '.join(RECORD_TYPES.keys())}")
    print("Usage: domain [type]")
    print("Examples: google.com | google.com AAAA | mysite.local A")
    print("Type 'exit' to return to menu.")
    print("=" * 50)

    while True:
        user_input = input("\nDNS> ").strip()

        if user_input.lower() == "exit":
            print("Back to menu.")
            break

        if not user_input:
            continue

        parts = user_input.split()
        domain = parts[0]
        record_type = parts[1].upper() if len(parts) > 1 else "A"
        dns_query(domain, record_type, ssl_context)

# מצב App: פותר דומיין, בוחר סרט, מוריד סגמנטים
def app_mode(ssl_context):
    print("\n--- Application Server Mode ---")

    # תרגום app.local ל-IP דרך DNS
    app_server_ip = resolve_domain(APP_DOMAIN, ssl_context)
    if not app_server_ip:
        print(f"[APP] ERROR: Could not resolve {APP_DOMAIN}")
        return

    # חיבור TCP + בחירת סרט
    select_info = app_browse_and_select(app_server_ip)
    if not select_info:
        print("[APP] ERROR: Could not select movie")
        return

    # הורדת סגמנטים דרך UDP
    download_movie_segments(app_server_ip, select_info)


def main():

    #  שלב 1: DHCP - קבלת כתובת IP על גבי UDP
    print("=" * 50)
    print("  Client - DHCP + DNS (DoH)")
    print("=" * 50)

    print("\n--- Step 1: Getting IP from DHCP server (UDP) ---")
    dhcp_result = dhcp_discover_and_request()

    if not dhcp_result.get("your_ip"):
        print("\n[!] Failed to get IP from DHCP. Cannot continue.")
        print("[!] Make sure DHCP_Server.py is running.")
        return

    my_ip = dhcp_result.get("your_ip")
    subnet_mask = dhcp_result.get("subnet_mask")
    lease = dhcp_result.get("lease_seconds")
    print(f"\n[OK] Client is now configured:")
    print(f"IP Address:   {my_ip}")
    print(f"Subnet Mask:  {subnet_mask}")
    print(f"Lease Time:   {lease}s")

    #שלב 2: DNS - שאילתות DNS על גבי HTTPS
    print(f"\nStep 2: DNS queries via DoH (DNS over HTTPS)")
    ssl_context = setup_ssl()

    if ssl_context is None:
        print("\nCannot start DNS without SSL certificate.")
        print("Make sure DNS_Server.py is running (it generates the certificate).")
        return

    print(f"\n[DNS] Protocol: HTTPS (DoH)")
    print(f"[DNS] Server: {DNS_Server_IP}:{DNS_Server_PORT}")

    # תפריט ראשי
    while True:
        print("\n" + "=" * 50)
        print("Choose an action:")
        print("1) Ask DNS questions")
        print("2) Connect to Application Server (DASH)")
        print("3) Exit")
        print("=" * 50)

        choice = input("Choice (1/2/3): ").strip()

        if choice == "1":
            dns_interactive_mode(ssl_context)

        elif choice == "2":
            app_mode(ssl_context)

        elif choice == "3":
            print("Goodbye!")
            return

        else:
            print("Invalid choice, please try again.")



if __name__ == "__main__":
    main()
