import socket, json, os, threading

# כתובת השרת - ברשת המקומית כמו שמוגדר ב-DNS (app.local)
SERVER_IP = "0.0.0.0"

# פורט TCP - ערוץ בקרה (רשימת סרטים, בחירה)
TCP_PORT = 9000

# פורט UDP - ערוץ נתונים (שליחת סגמנטי וידאו)
UDP_PORT = 9001

# קידוד טקסט
ENCODING = "utf-8"

# גודל באפר לקריאה מהסוקט
BUFFER_SIZE = 4096

# נתיב לתיקיית המדיה (יחסית למיקום הסקריפט)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_DIR = os.path.join(SCRIPT_DIR, "media")
CATALOG_FILE = os.path.join(MEDIA_DIR, "catalog.json")

# גודל מקסימלי של חתיכת נתונים בחבילת UDP (בבתים)
# 64KB מקסימום ל-UDP, מינוס 12 בתים ל-Header שלנו
MAX_CHUNK_SIZE = 60000

# סוגי הודעות - כל מספר מייצג סוג אחר
MSG_DATA = 1      # חתיכת נתונים (סגמנט)
MSG_ACK = 2       # אישור קבלה
MSG_SEG_REQ = 3   # בקשת סגמנט
MSG_FIN = 4       # סיום


# טוען את קטלוג הסרטים מקובץ catalog.json
# מחזיר מילון עם כל הסרטים והמידע עליהם, או מילון ריק אם הקובץ לא קיים
def load_catalog() -> dict:
    # בודק אם קובץ הקטלוג קיים
    if not os.path.exists(CATALOG_FILE):
        print(f"[!] Catalog not found: {CATALOG_FILE}")
        print(f"[!] Run prepare_media.py first!")
        return {}  # מחזיר מילון ריק אם אין קטלוג

    # פותח את הקובץ וממיר מ-JSON למילון Python
    with open(CATALOG_FILE, "r", encoding=ENCODING) as f:
        catalog = json.load(f)

    print(f"[OK] Catalog loaded: {len(catalog)} movies")
    return catalog  # מחזיר את הקטלוג כמילון


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


# מטפל בלקוח בודד שהתחבר ב-TCP
# מקבל פקודות ומחזיר תשובות עד שהלקוח מתנתק
def handle_tcp_client(client_sock: socket.socket, addr, catalog: dict):
    print(f"[TCP] Client connected: {addr}")

    try:
        while True:
            # מחכה לקבל הודעה מהלקוח
            msg = tcp_recv(client_sock)
            if not msg:
                break  # הלקוח ניתק

            msg_type = msg.get("type", "")
            print(f"[TCP] Got from {addr}: {msg_type}")

            # פקודת LIST - הלקוח רוצה רשימת סרטים
            if msg_type == "LIST":
                # בונה תשובה עם כל הקטלוג
                reply = {
                    "type": "LIST_RESPONSE",
                    "movies": catalog
                }
                # שולח את התשובה ללקוח
                tcp_send(client_sock, reply)

            # פקודת SELECT - הלקוח בחר סרט
            elif msg_type == "SELECT":
                # שולף את שם הסרט שהלקוח ביקש
                movie_name = msg.get("movie", "")

                # בדיקה שהסרט קיים בקטלוג
                if movie_name not in catalog:
                    tcp_send(client_sock, {
                        "type": "ERROR",
                        "reason": f"Movie '{movie_name}' not found"
                    })
                    continue  # חוזר לחכות לפקודה הבאה

                # שולף את המידע על הסרט מהקטלוג
                movie_info = catalog[movie_name]

                # בונה תשובה עם כל הפרטים שהלקוח צריך
                reply = {
                    "type": "SELECT_OK",
                    "movie": movie_name,
                    "total_segments": movie_info["segments"],
                    "segment_duration": movie_info["segment_duration_sec"],
                    "qualities": list(movie_info["qualities"].keys()),
                    "udp_port": UDP_PORT
                }
                tcp_send(client_sock, reply)
                print(f"[TCP] Client {addr} selected: {movie_name}")

            # פקודה לא מוכרת - מחזיר שגיאה
            else:
                tcp_send(client_sock, {
                    "type": "ERROR",
                    "reason": f"Unknown command: {msg_type}"
                })

    except Exception as e:
        print(f"[TCP] Error with {addr}: {e}")
    finally:
        # סוגר את החיבור כשהלקוח מסיים
        client_sock.close()
        print(f"[TCP] Client disconnected: {addr}")


# קורא קובץ סגמנט מהדיסק ומחזיר את הבתים שלו
# movie_name: שם הסרט (למשל "movie1")
# seg_num: מספר הסגמנט (למשל 2)
# quality: איכות (למשל "HIGH")
def load_segment(movie_name: str, seg_num: int, quality: str) -> bytes:
    # בונה את שם הקובץ, למשל: seg_002_HIGH.mp4
    filename = f"seg_{seg_num:03d}_{quality}.mp4"

    # בונה את הנתיב המלא, למשל: media/movie1/seg_002_HIGH.mp4
    filepath = os.path.join(MEDIA_DIR, movie_name, filename)

    # בודק שהקובץ קיים
    if not os.path.exists(filepath):
        print(f"[!] Segment not found: {filepath}")
        return b""  # מחזיר בתים ריקים אם לא נמצא

    # קורא את כל הבתים מהקובץ
    with open(filepath, "rb") as f:
        data = f.read()

    print(f"[UDP] Loaded: {filename} ({len(data)} bytes)")
    return data


# מפצל נתונים (בתים) לרשימה של חתיכות בגודל MAX_CHUNK_SIZE
# מחזיר רשימה של חתיכות בתים
def split_to_chunks(data: bytes) -> list:
    chunks = []
    # עובר על הנתונים בקפיצות של MAX_CHUNK_SIZE
    for i in range(0, len(data), MAX_CHUNK_SIZE):
        # חותך פרוסה מ-i עד i+MAX_CHUNK_SIZE
        chunk = data[i : i + MAX_CHUNK_SIZE]
        chunks.append(chunk)

    return chunks


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


# מאזין לבקשות UDP ושולח סגמנטים ללקוחות
# catalog: הקטלוג של הסרטים
def handle_udp(catalog: dict):
    # יוצר סוקט UDP וקושר לפורט
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, UDP_PORT))
    print(f"[UDP] Listening on {SERVER_IP}:{UDP_PORT}")

    while True:
        try:
            # מחכה לקבל חבילה מלקוח
            raw_data, client_addr = sock.recvfrom(BUFFER_SIZE)

            # חבילה קצרה מדי ל-header -> מדלגים
            if len(raw_data) < 12:
                continue

            # פורק את החבילה ל-Header + Data
            packet = parse_packet(raw_data)

            # מטפלים רק בבקשות SEG_REQ
            if packet["type"] != MSG_SEG_REQ:
                continue

            # פענוח הבקשה - אם JSON לא תקין מדלגים
            try:
                request = json.loads(packet["data"].decode(ENCODING))
            except Exception:
                continue

            movie_name = request.get("movie", "")
            seg_num = request.get("segment", 0)
            quality = request.get("quality", "MEDIUM")

            print(f"[UDP] {client_addr} requested: {movie_name} seg={seg_num} quality={quality}")

            # טוען את הסגמנט מהדיסק
            seg_data = load_segment(movie_name, seg_num, quality)
            if not seg_data:
                continue

            # מפצל את הסגמנט לחתיכות
            chunks = split_to_chunks(seg_data)
            total_chunks = len(chunks)

            print(f"[UDP] Sending {total_chunks} chunks ({len(seg_data)} bytes)")

            # שולח את החתיכות אחת-אחת
            for i, chunk in enumerate(chunks):
                # האם זו החתיכה האחרונה?
                is_last = 1 if i == total_chunks - 1 else 0

                # בונה חבילת DATA עם מספר רצף ודגל סיום
                pkt = build_packet(
                    msg_type=MSG_DATA,
                    seq=i,              # מספר רצף: 0, 1, 2, ...
                    flags=is_last,      # 1 = חתיכה אחרונה, 0 = יש עוד
                    data=chunk          # הנתונים עצמם
                )

                # שולח ללקוח
                sock.sendto(pkt, client_addr)

            print(f"[UDP] Done sending {movie_name} seg={seg_num}")

        except Exception as e:
            print(f"UDP -> Error handling packet: {e}")
            continue


# הפעלת השרת - TCP + UDP
def main():
    # טוען את קטלוג הסרטים
    catalog = load_catalog()
    if not catalog:
        return  # אין קטלוג, לא ניתן להפעיל

    # מפעיל את שרת ה-UDP ב-thread נפרד (רץ ברקע)
    udp_thread = threading.Thread(target=handle_udp, args=(catalog,), daemon=True)
    udp_thread.start()

    # יוצר סוקט TCP ומאזין לחיבורים
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # מאפשר שימוש חוזר בפורט
    tcp_sock.bind((SERVER_IP, TCP_PORT))
    tcp_sock.listen(5)  # מוכן לקבל עד 5 לקוחות בתור

    print("=" * 50)
    print("  DASH Video Server")
    print("=" * 50)
    print(f"  TCP (control): {SERVER_IP}:{TCP_PORT}")
    print(f"  UDP (data):    {SERVER_IP}:{UDP_PORT}")
    print(f"  Movies:        {len(catalog)}")
    print("=" * 50)

    try:
        while True:
            # מחכה ללקוח חדש שיתחבר
            client_sock, addr = tcp_sock.accept()

            # מפעיל thread נפרד לטיפול בלקוח
            t = threading.Thread(
                target=handle_tcp_client,
                args=(client_sock, addr, catalog),
                daemon=True
            )
            t.start()

    except KeyboardInterrupt:
        print("\n[Server] Shutting down...")
    finally:
        tcp_sock.close()


# נקודת הכניסה - מפעיל את main
if __name__ == "__main__":
    main()
