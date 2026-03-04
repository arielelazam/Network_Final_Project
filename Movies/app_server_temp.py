import socket
import json
import os
import threading

# הגדרות כלליות של שרת האפליקציה
SERVER_IP = "127.0.0.1" # כתובת ה-IP של האפליקציה
TCP_PORT = 9000 # ה-PORT עליו שרת האפליקציה יאזין לבקשת TCP
UDP_PORT = 9001 # ה-PORT עליו שרת האפליקציה יאזין לבקשות UDP
ENCODING = "utf-8"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) # הנתיב של תיקיית ה-script הנוכחי
MEDIA_DIR = os.path.join(SCRIPT_DIR, "media") # הנתיב של תיקיית המדיה
CATALOG_FILE = os.path.join(MEDIA_DIR, "catalog.json") # הנתיב לקובץ ה-JSON בו מאוחסנים הסרטים

# הגדרות UDP Reliable
MAX_CHUNK_SIZE = 60000 # הגודל המקסימלי לכל פיסת מידע
ACK_TIMEOUT = 1.0 # הזמן שנקצה לקבלת ACK
MAX_RETRIES = 3  # מספר הניסיונות לשליחה חוזרת במידת הצורך

# פונקציית טעינת הקטלוג
def load_catalog():
    if not os.path.exists(CATALOG_FILE): # אם לא נמצא קטלוג, נדפיס הודעת שגיאה ונחזיר דיקשנרי ריק
        print(f"Catalog not found: {CATALOG_FILE}")
        print(f"Run prepare_media.py first!")
        return {}

    # נפתח את קובץ הקטלוג ונטען ממנו את רשימת הסרטים
    with open(CATALOG_FILE, "r", encoding=ENCODING) as catalog_file:
        catalog = json.load(catalog_file) # נמיר את קובץ המידע לדיקשנרי

    print(f"Loaded {len(catalog)} movies from catalog")
    return catalog

# פונקציה שאחראית על הכנת הודעת tcp למשלוח, נשלח את ההודעה יחד עם אורכה ע"מ שהלקוח ידע מתי להפסיק לקרוא
def tcp_send(sock, msg):
    data = json.dumps(msg).encode(ENCODING) # נמיר את המחרוזת של ההודעה לבייטים
    length = len(data).to_bytes(4, "big") # נשמור את אורכו ב-4 בתים בשיטת BIG ENDIAN
    sock.sendall(length + data) # נשלח את ההודעה כך שאורכה יהיה בראשה

# פונקציה האחראית על קריאת הודעת tcp
def tcp_recv(sock):
    length_bytes = sock.recv(4) #  נקרא את אורכה של ההודעה בבייטים
    if not length_bytes: # אם אין בייטים, נסיק שהיא ריקה ונחזיר דיקשנרי ריק
        return {}

    length = int.from_bytes(length_bytes, "big") # נשמור את אורך ההודעה

    # קריאת המידע
    data = b"" # נגדיר את ה-buffer של בייטים שיאסוף את כל פיסות המידע שיגיעו
    while len(data) < length: # כל עוד מספר הבייטים שיש ב-buffer קטן ממספר הבייטים של ההודעה
        chunk = sock.recv(length - len(data)) # נקלוט את מספר הבייטים החסרים לנו בשביל שנדע שקראנו את כל ההודעה
        if not chunk: # אם לא הצלחנו לקרוא בייטים לפני שסיימנו לקרוא את כל הבייטים של ההודעה, נחזיר דיקשנרי ריק
            return {}
        data += chunk # נוסיף ל-buffer את הבייטים שקראנו

    return json.loads(data.decode(ENCODING)) # נחזיר את מה שקראנו ארוז כקובץ JSON


# פונקציית טיפול בבקשות לקוח מסוג TCP
def handle_tcp_client(client_sock, addr, catalog):
    print(f"Client connected in TCP from address: {addr}\n")

    with client_sock:
        try:
            while True:
                msg = tcp_recv(client_sock)  # נקלוט את הודעת ה-tcp
                if not msg:  # אם לא התקבלה הודעה נעצור
                    break

                msg_type = msg.get("type", "")  # נקלוט את סוג ההודעה שנקלטה
                print(f"TCP Request from {addr}: {msg_type}")

                # אם סוג ההודעה הוא LIST נחזיר ללקוח דיקשנרי עם קטלוג הסרטים
                if msg_type == "LIST":
                    response = {
                        "type": "LIST_RESPONSE",
                        "movies": catalog
                    }
                    tcp_send(client_sock, response)
                    print(f"[TCP] Sent movie list to {addr}")

                elif msg_type == "SELECT":  # אם סוג ההודעה היה SELECT
                    movie_name = msg.get("movie", "")  # נחלץ את שם הסרט שהוא ביקש

                    # אם שם הסרט שהלקוח ביקש לא נמצא בקטלוג, נחזיר הודעת שגיאה
                    if movie_name not in catalog:
                        tcp_send(client_sock, {
                            "type": "ERROR",
                            "reason": f"Movie '{movie_name}' not found"
                        })
                        continue

                    # נשלוף מהקטלוג את הפרטים על הסרט המבוקש ונשלח ללקוח הודעה עם הפרטים הרלוונטיים על הסרט שבחר
                    movie_info = catalog[movie_name]
                    response = {
                        "type": "SELECT_OK",
                        "movie": movie_name,
                        "total_segments": movie_info["segments"],
                        "qualities": list(movie_info["qualities"].keys()),
                        "udp_port": UDP_PORT
                    }
                    tcp_send(client_sock, response)
                    print(f"Client {addr} selected: {movie_name}")

                else:  # אחרת נחזיר לו הודעת שגיאה
                    tcp_send(client_sock, {
                        "type": "ERROR",
                        "reason": f"Unknown command: {msg_type}"
                    })

        # טיפול בשגיאות בזמן השיחה עם הלקוח
        except Exception as e:
            print(f"TCP Error with {addr}: {e}")

    # ברגע שיצאנו מבלוק ה-with, הסוקט נסגר אוטומטית
    print(f"TCP Client disconnected: {addr}")

# הפונקציה שאחראית לייבא את הסגמנט המבוקש
def load_segment(movie_name, seg_num, quality):

    filename = f"seg_{seg_num:03d}_{quality}.mp4" # שם הסגמנט שיקבע לפי מספר הסגמנט (ב-3 ספרות) והאיכות המבוקשת
    filepath = os.path.join(MEDIA_DIR, movie_name, filename) # הנתיב לסגמנט הספציפי בסרט

    # אם הסגמנט המבוקש לא קיים או לא נמצא נחזיר בייטים ריקים
    if not os.path.exists(filepath):
        print(f"Segment not found: {filepath}")
        return b""

    # נפתח את הקובץ הבינארי המכיל את הסגמנט ונחזיר אותו
    with open(filepath, "rb") as segment_file:
        data = segment_file.read()

    return data

# הפונקציה שאחראית לשלוח את הסגמנט המבוקש בחלקים
def send_segment_reliable(sock, client_addr, movie_name, seg_num, quality):

    print(f"UDP Starting transfer: {movie_name} seg={seg_num} quality={quality}")

    seg_data = load_segment(movie_name, seg_num, quality) # טעינת הסגמנט
    if not seg_data: # אם לא נמצא הסגמנט או שלא הצלחנו לטעון נחזיר False
        return False

    # נפצל את הסגמנט לחתיכות בגודל אפשרי ונאחסן את החתיכות בתוך chunks
    chunks = []
    for i in range(0, len(seg_data), MAX_CHUNK_SIZE):
        chunks.append(seg_data[i:i + MAX_CHUNK_SIZE])

    total_chunks = len(chunks) # מספר החתיכות שחילקנו את הסגמנט
    print(f"Segment size: {len(seg_data)} bytes, {total_chunks} chunks")

    #התחלת שלב השליחה באמצעות Congestion Control, נתחיל ב-Slow Start, עם window קטן
    window = 1  # כמה חתיכות לשלוח ביחד
    max_window = 10  # מקסימום
    ssthresh = 5  # הסף ל-Slow Start
    sent_chunks = 0  # כמה חתיכות שלחנו עד כה

    while sent_chunks < total_chunks: # כל עוד סך החתיכות ששלחנו קטן ממספר החתיכות המרכיבות את הסגמנט
        batch_end = min(sent_chunks + window, total_chunks) # נקבע את המקבץ של החתיכות הבאות שישלחו
        batch_size = batch_end - sent_chunks # גודל המקבץ הנוחכי

        print(f"UDP Sending chunks {sent_chunks}-{batch_end - 1} (window={window})")

        success_count = 0  # כמה חתיכות מתוך המקבץ נשלחו בהצלחה

        # שליחת החתיכות במקבץ
        for i in range(sent_chunks, batch_end): # נעבור על כל החתיכות במקבץ הנוכחי
            chunk_data = chunks[i] # נשלוף את נתוני הביטים של החתיכה
            is_last_in_segment = (i == total_chunks - 1) # נבדוק האם זאת החתיכה האחרונה

            if send_chunk_with_ack(sock, client_addr, i, chunk_data, is_last_in_segment): #  אם החבילה נשלחה בהצלחה והתקבל עבורה Ack אחרי מספר ניסיונות
                success_count += 1 # נספור את השליחה כהצלחה אם היא הגיעה בתוך ה-TimeOut
            else: # אם לא התקבל Ack אחרי מספר נסיונות, נסיק שיש עומס ברשת
                print(f"UDP Chunk {i} failed after retries")
                print(f"UDP Congestion detected! Reducing window")
                ssthresh = max(window // 2, 1)  # נחתוך את הסף בחצי על מנת למנוע עומס
                window = 1  # נאתחל בחזרה את גודל החלון ל-1 בשביל להתחיל Slow Start מחדש
                break # נעצור את הלולאה וננסה לשלוח מחדש שוב את המקבץ הנוכחי

        # אם מספר החתיכות שנשלחו בהצלחה שווה לגודל המקבץ - כלומר כל המקבץ נשלח בהצלחה
        if success_count == batch_size:
            if window < ssthresh: # אם גודל החלון עדיין קטן מהסף, נכפיל את גודל החלון ונשמיך ב-Slow Start
                window = min(window * 2, max_window)
                print(f"UDP Slow Start: window → {window}")
            else: # אחרת, עברנו את הסף ונגדיל את החלון ב-1
                window = min(window + 1, max_window)
                print(f"UDP Congestion Avoidance: window → {window}")

            sent_chunks = batch_end # נגדיר את תחילת הטווח הבא להיות סוף הטווח שסיימנו לשלוח כעת
        # אחרת - כלומר מספר החבילות שנשלחו קטן מגדול המקבץ
        else:
            print(f"UDP Algorithm Score Dropped! Resetting logic to pool.")
            window = 1  # נחזיר את window בחזרה לגודל 1 בשביל להתחיל את שליחת המקבץ מחדש בצורה איטית יותר
            ssthresh = 2  # הקטנת סף ה-Slow Start

    print(f"UDP Transfer complete: {movie_name} seg={seg_num}")
    return True

# הפונקציה האחראית על שליחת כל חתיכת סגמנט והחזרת המידע האם היא נמסרה בהצלחה או לא
def send_chunk_with_ack(sock, client_addr, chunk_num, data, is_last):

    # נבנה את החבילה המכילה את חתיכת הסגמנט וננסה לשלוח אותה לכל היותר כמספר הניסיונות שהקצנו
    for attempt in range(MAX_RETRIES):
        packet = {
            "seq": chunk_num,  # מספר רצף
            "data": data.hex(),  # המידע (כ-hex string)
            "last": is_last  # האם זו החתיכה האחרונה
        }

        sock.sendto(json.dumps(packet).encode(ENCODING), client_addr) # נשלח את החתיכה ללקוח
        sock.settimeout(ACK_TIMEOUT) # נמתין לקבלת ACK מהלקוח

        try:
            ack_data, addr = sock.recvfrom(1024) # נקלוט את המידע שהתקבל מהלקוח ואת הכתובת שלו
            ack = json.loads(ack_data.decode(ENCODING))

            if ack.get("type") == "ACK" and ack.get("seq") == chunk_num: # אם סוג המידע שהתקבל מהלקוח הוא ACK
                print(f"Chunk {chunk_num} ACK received (attempt {attempt + 1})")
                return True

        # טיפול בשגיאת TimeOut
        except socket.timeout:
            print(f"Chunk {chunk_num} timeout (attempt {attempt + 1}/{MAX_RETRIES})")

    return False # נכשל אחרי כל הניסיונות

# פונקציית טיפול בבקשות לקוח מסוג UDP
def handle_udp(catalog):

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # ניצור סוקט ממשפחת IPv4 ומסוג UDP
    sock.bind((SERVER_IP, UDP_PORT)) # נחבר את הסוקט ל-IP ול-PORT שהקצנו לו
    print(f"UDP Listening on {SERVER_IP}:{UDP_PORT}")

    while True:
        try:
            data, client_addr = sock.recvfrom(4096) # נקלוט מידע של בקשה נכנסת ואת כתובת הלקוח
            request = json.loads(data.decode(ENCODING)) # נשמור את המידע ב-JSON
            movie_name = request.get("movie", "") # נשמור את שם הסרט המבוקש
            seg_num = request.get("segment", 0) # נשמור את הסגמנט המבוקש
            quality = request.get("quality", "MEDIUM") # נשמור את האיכות המבוקשת

            print(f"\n[UDP] Request from {client_addr}:")
            print(f"Movie={movie_name}, Segment={seg_num}, Quality={quality}")

            # שליחת הסגמנט (עם Reliability + Flow + Congestion)
            send_segment_reliable(sock, client_addr, movie_name, seg_num, quality) # נבצע שליחה של הסגמנט המבוקש, באיכות המבוקשת

        # טיפול בשגיאות לא צפויות
        except Exception as e:
            print(f"UDP Error: {e}")

# פונקציית שרת ה-TCP
def tcp_server(catalog):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # ניצור סוקט ממשפחת IPv4 ומסוג TCP
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # נרצה לאפשר לסוקט לגשת באופן מיידי לאותו פורט
    sock.bind((SERVER_IP, TCP_PORT)) # נחבר את הסוקט ל-IP ול-PORT שהקצנו לו
    sock.listen(5) # הסוקט יאזין (חובה כי הוא Connection - oriented) ובתור יוכלו להיות לכל היותר 5 לקוחות המבקשים להתחבר
    print(f"TCP Listening on {SERVER_IP}:{TCP_PORT}")

    while True:
        client_sock, addr = sock.accept() # נקלוט את הסוקט של הלקוח ואת הכתובת שלו
        thread = threading.Thread(target=handle_tcp_client,args=(client_sock, addr, catalog),daemon=True) # נקצה לו תהליך שיוכל לטפל בו במקביל לכך שנשמיך להאזין לבקשות נוספות
        thread.start()

# הפונקציה הראשית
def main():
    catalog = load_catalog() # נטען את קטלוג הסרטים של השרת
    if not catalog: # אם הקטלוג ריק נסגור את הפונקציה
        return

    print("=" * 60)
    print("Application Server - DASH Video with Reliable UDP")
    print(f"TCP (control): {SERVER_IP}:{TCP_PORT}, UDP (data): {SERVER_IP}:{UDP_PORT}, Movies: {len(catalog)}")
    print("=" * 60 + "\n")

    # הפעלת UDP ב-thread נפרד
    udp_thread = threading.Thread(target=handle_udp, args=(catalog,), daemon=True)
    udp_thread.start()

    # הפעלת TCP (ברקע הראשי)
    try:
        tcp_server(catalog)
    except KeyboardInterrupt:
        print("Server Shutting down...")

if __name__ == "__main__":
    main()