import socket

SERVER_IP = "127.0.0.2"
SERVER_PORT = 5300
BUFFER_SIZE = 1024
ENCODING_FORMAT = "utf-8"

# מאגר הנתונים על פי value ו key
DNS_DB ={
    "video.server.com": "127.0.0.1",
    "ftp.server.com": "127.0.0.1",
    "google.com": "8.8.8.8"
}

def start_dns_server():
    # AF_INET = IP 4 שימוש בפרוטוקול , SOCK_DGRAM = UDP שימוש בפרוטוקול
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        # מאזין ל IP ול PORT
        server_sock.bind((SERVER_IP,SERVER_PORT))
        print(f"[DNS Server] Server is running and listening on {SERVER_IP}:{SERVER_PORT}...")

        while True:
            #  מי מבקש את הבקשה על מנת לדעת למי להחזיר תשובה
            data, client_address = server_sock.recvfrom(BUFFER_SIZE)

            #המרה מביטים לטקס וניקוי רווחים מיותרים 
            domain_query = data.decode(ENCODING_FORMAT).strip()
            print(f"[DNS Server] Received query: '{domain_query}' from {client_address}")


