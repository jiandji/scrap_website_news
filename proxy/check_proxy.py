import threading
import requests
import queue

q = queue.Queue()
valid_proxies = []
lock = threading.Lock()

with open('ip_list.txt', 'r') as f:
    proxies = f.read().split("\n")
    for p in proxies:
        if p.strip():
            q.put(p.strip())

def check_proxy():
    while not q.empty():
        proxy = q.get()
        try:
            res = requests.get("http://ipinfo.io/json",
                               proxies={"http": proxy,
                                        "https": proxy},
                               timeout=10)
        except:
            continue
        if res.status_code == 200:
            print(f"VALID: {proxy}")
            with lock:
                valid_proxies.append(proxy)

threads = []
for _ in range(10):
    t = threading.Thread(target=check_proxy)
    t.start()
    threads.append(t)

for t in threads:
    t.join()

# Simpan proxy yang valid ke file untuk dipakai main.py & middlewares.py
output_path = '../proxy_list.txt'
with open(output_path, 'w') as f:
    for proxy in valid_proxies:
        f.write(f"http://{proxy}\n")

print(f"\nSelesai! {len(valid_proxies)} proxy valid disimpan ke {output_path}")
