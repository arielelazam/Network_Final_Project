import socket
import json
import time
# הגדרות כלליות לעבודה מול השרתים
DHCP_IP = "127.0.0.1"
DHCP_PORT = 6767
CLIENT_NAME = "my_client"
DNS_IP = "127.0.0.1"
DNS_PORT = 9999
ENCODING = "utf-8"
MY_SITE_DOMAIN = "mysite.local"
TIMEOUT = 5

# פונקציות להמרת קוד ל-JSON ולהיפך
def encode_json(msg: dict) -> bytes:
    return json.dumps(msg).encode(ENCODING)

def decode_json(data: bytes) -> dict:
    return json.loads(data.decode(ENCODING))

# פונקציות עבודה מול שרת ה-DHCP

# פונקציית בקשת כתובת מה-DHCP
def dhcp_get_ip():
    print("Starting the process with DHCP to get IP address")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: # ניצור סוקט ממשפחת IPv4 מסוג UDP
        sock.settimeout(TIMEOUT) # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

        # נשלח לשרת ה-DHCP חבילת מידע עם השם שלנו ונגדיר שזאת בקשת DISCOVER
        try:
            discover_msg = {
                "type": "DHCP_DISCOVER",
                "client_name": CLIENT_NAME
            }

            print("Sending DISCOVER message to DHCP\n")
            sock.sendto(encode_json(discover_msg), (DHCP_IP, DHCP_PORT))

            # נקלוט מה-DHCP את כתובת ה-IP שהוא מציע לנו
            print("Waiting for DHCP OFFER\n")
            data, addr = sock.recvfrom(1024)
            offer = decode_json(data)

            print("DHCP OFFER received from DHCP\n")
            if offer.get("type") != "DHCP_OFFER": # אם החבילה שהתקבלה היא לא OFFER
                print("Didn't receive DHCP OFFER - ERROR!!!")
                if offer.get("reason"):
                    print(f"The reason for the ERROR is : {offer.get('reason')}") # נדפיס מה הסיבה שבגללה שקרתה השגיאה
                return None

            client_id = offer.get("client_id")
            offered_ip = offer.get("offered_ip")
            subnet_mask = offer.get("subnet_mask")
            offer_timeout = offer.get("offer_timeout")

            print(f"Client ID: {client_id},Offered IP: {offered_ip}, Subnet mask: {subnet_mask}, Time to take the offered IP: {offer_timeout} seconds\n")

            # קיבלנו את הצעת ה-DHCP וכעת נשלח לו REQUEST ונאשר לו שאנחנו רוצים את ההצעה
            requested_msg = {
                "type": "DHCP_REQUEST",
                "client_name": CLIENT_NAME,
                "requested_ip": offered_ip
            }
            print("Sending REQUEST message to DHCP\n")
            sock.sendto(encode_json(requested_msg), (DHCP_IP, DHCP_PORT))

            data, addr = sock.recvfrom(1024)
            ack = decode_json(data)

            if ack.get("type") != "DHCP_ACK": # אם המידע שהתקבל הוא לא ACK נחזיר שגיאה ואת הסיבה שבגללה היא קרתה
                print("Didn't receive DHCP ACK - ERROR!!!")
                if ack.get("reason"):
                    print(f"The reason for the ERROR is : {ack.get('reason')}")
                return None

            my_ip = ack.get("your_ip")
            lease_time_in_seconds = ack.get("lease_seconds")

            print(f"Client IP: {my_ip}, Time to use the IP: {lease_time_in_seconds} seconds\n")

            return my_ip

        #תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
        except socket.timeout:
            print("TIMEOUT ERROR!!!")
            return None

        except Exception as e:
            print(f"UNEXPECTED ERROR!!! Reason: {e}")
            return None

# פונקציית כתובת מה-DNS
def dns_resolve():
    print("Starting the process with DNS to resolve IP address\n") # נגדיר זמן לזריקת שגיאה אם מידע לא הגיע ותוקע את התוכנית

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock: # ניצור סוקט ממשפחת IPv4 ומסוג UDP
        sock.settimeout(TIMEOUT)

        # נשלח ל-DNS את הדומיין שאנחנו רוצים לקבל את ה-IP שלו
        try:
            query = {"domain": MY_SITE_DOMAIN}
            print("Sending query to DNS\n")
            sock.sendto(encode_json(query), (DNS_IP, DNS_PORT))

            data, addr = sock.recvfrom(1024)
            response = decode_json(data)

            if response.get("status") != "success": # אם מסיבה כלשהי ה-DNS לא החזיר לנו את ה-IP המבוקש נחזיר הדועת שגיאה ואת הסיבה שגרמה לה לקרות
                print(f"DNS is not responding - ERROR!!!")
                if response.get("reason"):
                    print(f"The reason for the ERROR is : {response.get('reason')}")
                return None

            # נקלוט מהמידע שהתקבל את הדומיין עבורו ביקשנו IP, את כתובת ה-IP שהתקבלה ומאיפה ה-DNS שלף לנו את הכתובת הזאת
            resolved_domain = response.get("domain")
            resolved_ip = response.get("ip")
            resolved_method = response.get("method")

            print(f"The IP of the requested domain {resolved_domain} is: {resolved_ip} and the method is: {resolved_method}\n")

            return resolved_ip

        # תפיסת שגיאות TIMEOUT או שגיאות אחרות לא צפויות
        except socket.timeout:
            print("TIMEOUT ERROR!!!")
            return None

        except Exception as e:
            print(f"UNEXPECTED ERROR!!! Reason: {e}")

# פונקצייה ראשית
def main():
    print("Temp client is running!")

    my_ip = dhcp_get_ip() # נפנה ל-DHCP לקבל IP

    # אם לא הצלחנו לקבל כתובת IP מה-DHCP נחזיר הודעת שגיאה
    if not my_ip:
        print("Failed to get IP from DHCP")
        return

    time.sleep(1)

    app_ip = dns_resolve() # נבקש מה-DNS את כתובת ה-IP של השרת מולו אנחנו רוצים לעבוד

    # אם לא הצלחנו לקבל את הכתובת מה-DNS נחזיר הודעת שגיאה
    if not app_ip:
        print("Failed to get IP from DNS")
        return

    print("\nEverything worked successfully!\n")
    print(f"My IP: {my_ip}, App IP: {app_ip}\n")
    print("Ready to connect to application!\n")

if __name__ == "__main__":
    main()