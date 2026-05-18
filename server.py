import socket
import threading

# HOST       = 'localhost'
HOST       = '0.0.0.0'
import os

PORT = int(os.environ.get("PORT", 65432))

EOF_MARKER = b'<<END>>'
clients    = []
lock       = threading.Lock()           # ← منع التعارض بين الـ threads

def broadcast(data, sender):
    with lock:
        for conn in clients[:]:         # نسخة من القائمة عشان نتجنب مشكلة الحذف أثناء الـ loop
            if conn != sender:
                try:
                    conn.sendall(data)
                except:
                    clients.remove(conn)

def handle_client(conn, addr):
    print(f"Connected: {addr}")
    with lock:
        clients.append(conn)
    buf = b''                           # ← buffer منفصل لكل client يحل مشكلة خلط الرسائل
    try:
        while True:
            part = conn.recv(4096)
            if not part:
                break
            buf += part
            while EOF_MARKER in buf:    # ← نعالج كل الرسائل الكاملة في الـ buffer
                msg, buf = buf.split(EOF_MARKER, 1)
                broadcast(msg + EOF_MARKER, conn)
    except:
        pass
    finally:                            # ← دايماً بينظف حتى لو حصل error
        with lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()
        print(f"Disconnected: {addr}")

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ← إعادة تشغيل سريعة بدون انتظار
server.bind((HOST, PORT))
server.listen()
print("Server is running...")

while True:
    conn, addr = server.accept()
    threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()