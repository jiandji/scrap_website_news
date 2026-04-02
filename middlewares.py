import random
import os
import sqlite3
import json
from datetime import datetime
from scrapy.exceptions import DropItem
from dotenv import load_dotenv

load_dotenv()


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
SQLite Backup Pipeline - simpan setiap artikel ke SQLite lokal
Sync ke PostgreSQL saat spider selesai
"""

class SQLiteBackupPipeline:
    def open_spider(self, spider):
        date_str = datetime.now().strftime("%Y-%m-%d")
        os.makedirs('output/backup', exist_ok=True)
        self.db_path = f'output/backup/hasil_berita_{date_str}.db'
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS website_scraping (
                scraping_id INTEGER PRIMARY KEY AUTOINCREMENT,
                media_name TEXT,
                title TEXT,
                content TEXT,
                news_link TEXT UNIQUE,
                news_date TEXT,
                author TEXT,
                crawled_at TEXT,
                synced INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def process_item(self, item, spider):
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO website_scraping
                   (media_name, title, content, news_link, news_date, author, crawled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.get('media_name'),
                    item.get('title'),
                    item.get('content'),
                    item.get('news_link'),
                    item.get('news_date'),
                    item.get('author'),
                    item.get('news_date_crawled'),
                )
            )
            self.conn.commit()
        except Exception as e:
            spider.logger.error(f"SQLite error: {e}")
        return item

    def close_spider(self, spider):
        self._sync_to_postgres(spider)
        self.conn.close()

    def _sync_to_postgres(self, spider):
        pg_host = os.getenv('POSTGRES_HOST')
        if not pg_host:
            spider.logger.info("PostgreSQL not configured, skipping sync. Data safe in SQLite.")
            return

        try:
            import psycopg2
            pg_conn = psycopg2.connect(
                host=pg_host,
                port=os.getenv('POSTGRES_PORT', '5432'),
                dbname=os.getenv('POSTGRES_DB'),
                user=os.getenv('POSTGRES_USER'),
                password=os.getenv('POSTGRES_PASSWORD'),
            )
            cur = pg_conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS website_scraping (
                    scraping_id SERIAL PRIMARY KEY,
                    media_name TEXT,
                    title TEXT,
                    content TEXT,
                    news_link TEXT UNIQUE,
                    news_date TIMESTAMP,
                    author TEXT,
                    crawled_at TIMESTAMP
                )
            """)

            unsynced = self.conn.execute(
                "SELECT scraping_id, media_name, title, content, news_link, news_date, author, crawled_at "
                "FROM website_scraping WHERE synced = 0"
            ).fetchall()

            synced_count = 0
            for row in unsynced:
                sid, media_name, title, content, news_link, news_date, author, crawled_at = row
                try:
                    cur.execute(
                        """INSERT INTO website_scraping
                           (media_name, title, content, news_link, news_date, author, crawled_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (news_link) DO NOTHING""",
                        (media_name, title, content, news_link, news_date, author, crawled_at)
                    )
                    self.conn.execute("UPDATE website_scraping SET synced = 1 WHERE scraping_id = ?", (sid,))
                    synced_count += 1
                except Exception as e:
                    spider.logger.error(f"PostgreSQL insert error: {e}")

            pg_conn.commit()
            self.conn.commit()
            pg_conn.close()
            spider.logger.info(f"Synced {synced_count}/{len(unsynced)} articles to PostgreSQL")

        except Exception as e:
            spider.logger.error(f"PostgreSQL connection failed, data safe in SQLite: {e}")


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