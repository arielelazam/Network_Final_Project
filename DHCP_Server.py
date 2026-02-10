
import json, socket
from typing import Dict, Any


# פונקציה שמקבלת דיקשנרי הופכת אותו לגיסון וממירה אותו לבתים
def encode(msg: Dict[str,Any]) -> bytes:
    return json.dumps(msg).encode("utf-8")

# פונקציה שמקבלת בתים הופת אותם לגיסון וממירה אותם לדיקשנרי
def decode(data: bytes) -> dict[str,Any]:
    return json.loads(data.decode("utf-8"))

