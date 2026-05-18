import socket
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
import io
import os
import datetime
import sounddevice as sd
import scipy.io.wavfile as wav
import numpy as np

# ===== إعدادات =====
HOST       = 'turntable.proxy.rlwy.net'
PORT       = 29412
EOF_MARKER = b'<<END>>'
hd_mode    = False
photo_refs = []
recording  = False          # ← هنا صح (global)
audio_data = []             # ← هنا صح (global)

# ===== بناء الرسائل =====
def make_text(name, text):
    return f"TEXT|{name}\n".encode() + text.encode() + EOF_MARKER

def make_image(name, img_bytes, filename):
    return f"IMAGE|{name}|{filename}\n".encode() + img_bytes + EOF_MARKER

def make_file(name, file_bytes, filename):
    return f"FILE|{name}|{filename}\n".encode() + file_bytes + EOF_MARKER

# ===== ضغط الصور =====
def compress_image(path, quality=40):
    img = Image.open(path)
    if img.mode != 'RGB':
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality)
    return buf.getvalue()

# ===== استقبال البيانات =====
def receive_loop():
    buf = b''
    while True:
        try:
            part = sock.recv(4096)
            if not part:
                break
            buf += part
            while EOF_MARKER in buf:
                msg, buf = buf.split(EOF_MARKER, 1)
                root.after(0, lambda m=msg: show_message(m, side='left'))
        except:
            add_system("Connection Lost")
            break

# ===== تحليل الرسالة وعرضها =====
def show_message(raw, side):
    header, body = raw.split(b'\n', 1)
    parts    = header.decode().split('|')
    msg_type = parts[0]
    sender   = parts[1]
    filename = parts[2] if len(parts) > 2 else ''
    is_me    = (side == 'right')
    bg       = "#c5e4ee" if is_me else "#ffffff"
    anchor   = 'e' if is_me else 'w'
    px       = (80, 8) if is_me else (8, 80)
    now      = datetime.datetime.now().strftime("%d/%m %H:%M")   # ← التاريخ + الوقت

    frame  = tk.Frame(chat_frame, bg="#ece5dd")
    frame.pack(fill='x', pady=2)
    bubble = tk.Frame(frame, bg=bg, bd=1, relief='solid')
    bubble.pack(anchor=anchor, padx=px, pady=2)

    tk.Label(bubble, text=sender, font=("Arial", 8, "bold"),
             bg=bg, fg="#0c50aa").pack(anchor='w', padx=6, pady=(4,0))

    if msg_type == 'TEXT':
        tk.Label(bubble, text=body.decode(), wraplength=280,
                 font=("Arial", 11), bg=bg).pack(padx=8, pady=4)

    elif msg_type == 'IMAGE':
        try:
            img    = Image.open(io.BytesIO(body))
            img.thumbnail((240, 240))
            tk_img = ImageTk.PhotoImage(img)
            photo_refs.append(tk_img)
            tk.Label(bubble, image=tk_img, bg=bg).pack(padx=4, pady=4)
            tk.Label(bubble, text=filename, font=("Arial",8),
                     bg=bg, fg="#555").pack(anchor='w', padx=6)
        except:
            tk.Label(bubble, text="⚠️ Error In Image", bg=bg).pack(padx=6)

    elif msg_type == 'FILE':
        tk.Label(bubble, text=f"📎 {filename}",
                 font=("Arial",11), bg=bg).pack(padx=8, pady=(4,0))
        def save_file(b=body, f=filename):
            p = filedialog.asksaveasfilename(initialfile=f)
            if p:
                open(p,'wb').write(b)
                messagebox.showinfo("Done", f"Saved {f}")
        tk.Button(bubble, text="💾 Save", command=save_file,
                  bg="#8b1414", fg="white", relief='flat').pack(padx=8, pady=(2,6))

    elif msg_type == 'AUDIO':                           # ← نوع جديد
        def play_audio(b=body):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                f.write(b); tmp = f.name
            rate, data = wav.read(tmp)
            sd.play(data, rate); sd.wait()
        tk.Button(bubble, text="▶️ Play", command=play_audio,
                  bg="#0d2c66", fg="white", relief='flat').pack(padx=8, pady=6)

    tk.Label(bubble, text=now, font=("Arial",7),
             bg=bg, fg="#272727").pack(anchor='e', padx=6, pady=(0,4))

    canvas.after(50, lambda: canvas.yview_moveto(1.0))

def add_system(text):
    root.after(0, lambda: tk.Label(chat_frame, text=text,
               font=("Arial",9,"italic"), fg="#888",
               bg="#ece5dd").pack(pady=4))

# ===== أزرار الإرسال =====
def send_to_server(data):
    show_message(data.replace(EOF_MARKER, b''), side='right')
    try:
        sock.sendall(data)                       # ← الإرسال الحقيقي للسيرفر (كان ناقص!)
    except:
        add_system("Failed to send")

def send_text():
    text = msg_var.get().strip()
    if not text: return
    send_to_server(f"TEXT|{username}\n".encode() + text.encode() + EOF_MARKER)
    msg_var.set('')

def send_image():
    path = filedialog.askopenfilename(
        filetypes=[("Images","*.jpg *.jpeg *.png *.bmp *.webp")])
    if not path: return
    filename  = os.path.basename(path)
    img_bytes = open(path,'rb').read() if hd_mode else compress_image(path)
    label     = f"HD:{filename}" if hd_mode else filename
    send_to_server(f"IMAGE|{username}|{label}\n".encode() + img_bytes + EOF_MARKER)

def send_file():
    path = filedialog.askopenfilename()
    if not path: return
    filename   = os.path.basename(path)
    file_bytes = open(path,'rb').read()
    send_to_server(f"FILE|{username}|{filename}\n".encode() + file_bytes + EOF_MARKER)

def toggle_hd():
    global hd_mode
    hd_mode = not hd_mode
    hd_btn.config(text="🔵 HD ON" if hd_mode else "⚪ HD OFF",
                  bg="#1a73e8" if hd_mode else "#555")

# ===== تسجيل الصوت =====
def start_record():
    global recording, audio_data
    recording = True; audio_data = []
    def rec():
        with sd.InputStream(samplerate=44100, channels=1, dtype='int16',
                            callback=lambda i,*_: audio_data.extend(i.flatten())):
            while recording: sd.sleep(100)
    threading.Thread(target=rec, daemon=True).start()
    rec_btn.config(text="⏹ Stop", bg="#e53935", command=stop_record)

def stop_record():
    global recording
    recording = False
    buf = io.BytesIO()
    wav.write(buf, 44100, np.array(audio_data, dtype='int16'))
    send_to_server(f"AUDIO|{username}|voice.wav\n".encode() + buf.getvalue() + EOF_MARKER)
    rec_btn.config(text="🎤 Record", bg="#ff7043", command=start_record)

# ===== بناء الـ GUI =====
root = tk.Tk()
root.geometry("480x680")
root.configure(bg="#ece5dd")
root.resizable(False, False)

top = tk.Frame(root, bg="#07435e", height=50)
top.pack(fill='x')
top.pack_propagate(False)
tk.Label(top, text="💬 Chat App", font=("Arial",14,"bold"),
         bg="#07435e", fg="white").pack(side='left', padx=10)
hd_btn = tk.Button(top, text="⚪ HD OFF", command=toggle_hd,
                   bg="#555", fg="white", font=("Arial",9,"bold"),
                   relief='flat', padx=8)
hd_btn.pack(side='right', padx=10, pady=10)

container = tk.Frame(root, bg="#ece5dd")
container.pack(fill='both', expand=True)
scrollbar = tk.Scrollbar(container)
scrollbar.pack(side='right', fill='y')
canvas = tk.Canvas(container, bg="#ece5dd",
                   yscrollcommand=scrollbar.set, highlightthickness=0)
canvas.pack(fill='both', expand=True)
scrollbar.config(command=canvas.yview)
chat_frame = tk.Frame(canvas, bg="#ece5dd")
canvas.create_window((0,0), window=chat_frame, anchor='nw', width=460)
chat_frame.bind('<Configure>', lambda e: canvas.config(
    scrollregion=canvas.bbox('all')))

progress_var = tk.DoubleVar()
pb = tk.Canvas(root, height=5, bg="#ddd", highlightthickness=0)
pb.pack(fill='x')
fill = pb.create_rectangle(0,0,0,5, fill="#081a35", outline="")
def update_pb(*_):
    w = pb.winfo_width()
    pb.coords(fill, 0, 0, int(w * progress_var.get()/100), 5)
progress_var.trace_add('write', update_pb)

tools = tk.Frame(root, bg="#f0f0f0", pady=4)
tools.pack(fill='x')
b = dict(relief='flat', font=("Arial",10), padx=6, pady=4, cursor="hand2")
tk.Button(tools, text="🖼️ Image", bg="#75a1b6", fg="white",
          command=send_image, **b).pack(side='left', padx=4)
tk.Button(tools, text="📎 File",  bg="#1a73e8", fg="white",
          command=send_file,  **b).pack(side='left', padx=4)
rec_btn = tk.Button(tools, text="🎤 Record", bg="#a51d1d", fg="white",
                    command=start_record, **b)
rec_btn.pack(side='left', padx=4)

bottom = tk.Frame(root, bg="#f0f0f0", pady=6)
bottom.pack(fill='x')
msg_var   = tk.StringVar()
msg_entry = tk.Entry(bottom, textvariable=msg_var,
                     font=("Arial",12), width=28, bd=2, relief='groove')
msg_entry.pack(side='left', padx=(8,4), ipady=5)
msg_entry.bind('<Return>', lambda e: send_text())
tk.Button(bottom, text="Send ➤", command=send_text,
          bg="#10678f", fg="white", font=("Arial",11,"bold"),
          relief='flat', padx=10, pady=5).pack(side='left', padx=4)

# ===== اتصال بالـ Server =====
username = simpledialog.askstring("Name", "Enter Your Name:", parent=root) or "Unknown"
root.title(f"💬 Chat App — {username}")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    sock.connect((HOST, PORT))
    add_system("✅ Connected to server")
    threading.Thread(target=receive_loop, daemon=True).start()
except:
    add_system("reconnect to server")

root.mainloop()