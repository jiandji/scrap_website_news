import random
import os
from scrapy.exceptions import DropItem


"""
Config IP, User-Agent, Headers

"""
class HumanBehaviorMiddleware:
    def __init__(self):
        # 1. Load proxy list dari file
        self.proxies = []
        if os.path.exists('proxy/ip_list.txt'):
            with open('proxy/ip_list.txt', 'r') as f:
                # Format proxy di txt harus: http://ip:port atau http://user:pass@ip:port
                self.proxies = [line.strip() for line in f if line.strip()]

        # load user agents dari file txt
        with open('config/user-agents.txt', 'r', encoding='utf-8') as f:
            self.user_agents = [line.strip() for line in f if line.strip()]

    def process_request(self, request, spider):
        # Rotasi IP (Proxy)
        if self.proxies:
            proxy = random.choice(self.proxies)
            request.meta['proxy'] = proxy
            
        # Rotasi User-Agent
        ua = random.choice(self.user_agents)
        request.headers['User-Agent'] = ua

        # 4. Human-like Request Headers
        request.headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8'
        request.headers['Accept-Language'] = 'id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7'
        request.headers['Sec-Ch-Ua'] = '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"'
        request.headers['Sec-Ch-Ua-Mobile'] = '?0'
        request.headers['Sec-Ch-Ua-Platform'] = '"Windows"'
        request.headers['Sec-Fetch-Dest'] = 'document'
        request.headers['Sec-Fetch-Mode'] = 'navigate'
        request.headers['Sec-Fetch-Site'] = 'none'
        request.headers['Sec-Fetch-User'] = '?1'
        request.headers['Upgrade-Insecure-Requests'] = '1'
        

"""
Early sort deduplicate news by media_name + title 
"""

class DeduplicatePipeline:
    def __init__(self):
        # Menggunakan struktur data 'set' agar proses pencarian (lookup) duplikat super cepat
        self.seen_news = set()

    def process_item(self, item, spider):
        # Validasi keamanan jika newspaper3k gagal mengambil judul
        if not item.get('title') or not item.get('media_name'):
            raise DropItem("Data tidak lengkap, membuang item.")

        # Buat kombinasi unik. Contoh format: "tribun batam | gempa bumi hari ini"
        unique_key = f"{item['media_name']} | {item['title']}".lower()

        if unique_key in self.seen_news:
            # DropItem akan membatalkan penyimpanan ke JSON
            raise DropItem(f"Duplicate news found: {unique_key}")
        else:
            # Simpan kombinasi ke memori, lalu teruskan datanya untuk disave ke JSON
            self.seen_news.add(unique_key)
            return item