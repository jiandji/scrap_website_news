import scrapy
from scrapy.crawler import CrawlerProcess
import pandas as pd
import os
from datetime import datetime
from newspaper import Article
import nest_asyncio
import aiofiles



from twisted.internet.error import DNSLookupError, TimeoutError, TCPTimedOutError, ConnectionRefusedError
from twisted.web._newclient import ResponseNeverReceived
from scrapy.spidermiddlewares.httperror import HttpError

class UniversalNewsSpider(scrapy.Spider):
    name = 'universal_news'
    
    custom_settings = {
        'CONCURRENT_REQUESTS': 16, 
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        
        # 3. HUMAN-LIKE RANDOM INTERVAL REQUEST
        'DOWNLOAD_DELAY': 5.0,               # Base delay 2 detik
        'RANDOMIZE_DOWNLOAD_DELAY': True,    # Scrapy akan otomatis mengacak delay antara 1.0s s/d 3.0s
        
        'DOWNLOAD_TIMEOUT': 15,              
        'LOG_LEVEL': 'INFO',                
        
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 1,                    
        'RETRY_HTTP_CODES': [500, 502, 504, 408], 
        
        'FEEDS': {
            f'output/hasil_berita_{datetime.now().strftime("%Y-%m-%d")}.json': {
                'format': 'jsonlines',
                'encoding': 'utf8',
                'overwrite': True,
            },
        },

        # Registrasi class Middleware & Pipeline dari Bagian 1 & 2
        'DOWNLOADER_MIDDLEWARES': {
            'middlewares.HumanBehaviorMiddleware': 400,
        },
        'ITEM_PIPELINES': {
            'middlewares.DeduplicatePipeline': 300,
        }
    }

    async def start(self):
        # Membuat/membersihkan file log gagal akses setiap kali script dijalankan
        async with aiofiles.open('log_gagal_akses.txt', 'w', encoding='utf-8') as f:
            await f.write("=== LOG LAPORAN GAGAL AKSES CRAWLING ===\n")
            await f.write("Format: [KATEGORI] | Media | Alasan Detail | URL\n\n")

        try:
            df = pd.read_json('config/crawler_config.json', orient='records', lines=True)
        except FileNotFoundError:
            self.logger.error("File crawler_config.json tidak ditemukan!")
            return

        for index, row in df.iterrows():
            if row['crawl_method'] in ['rss', 'sitemap']:
                yield scrapy.Request(
                    url=row['target_url'],
                    callback=self.parse_router,
                    errback=self.handle_error, 
                    meta={'method': row['crawl_method'], 'media_name': row['media_name']},
                    dont_filter=True
                )

    def parse_router(self, response):
        method = response.meta['method']
        if method == 'rss':
            # Menggunakan yield from agar request diteruskan langsung ke mesin Scrapy
            yield from self.parse_rss(response)
        elif method == 'sitemap':
            yield from self.parse_sitemap(response)

    def parse_rss(self, response):
        links = response.xpath('//item/link/text() | //entry/link/@href').getall()
        
        for link in set(links):
            clean_link = link.strip()
            if clean_link:
                absolute_url = response.urljoin(clean_link)
                if absolute_url.startswith('http'):
                    yield scrapy.Request(
                        url=absolute_url, 
                        callback=self.parse_article, 
                        errback=self.handle_error,
                        meta=response.meta
                    )

    def parse_sitemap(self, response):
        response.selector.remove_namespaces()

        # Cek apakah ini sitemap index (berisi link ke sitemap lain)
        sub_sitemaps = response.xpath('//sitemap/loc/text()').getall()
        if sub_sitemaps:
            for sitemap_url in sub_sitemaps:
                clean_url = sitemap_url.strip()
                if clean_url:
                    yield scrapy.Request(
                        url=response.urljoin(clean_url),
                        callback=self.parse_sitemap,
                        errback=self.handle_error,
                        meta=response.meta,
                        dont_filter=True
                    )
            return

        # Sitemap biasa: ambil semua <url><loc>
        links = response.xpath('//url/loc/text()').getall()

        for link in list(set(links))[:50]:
            clean_link = link.strip()
            if clean_link:
                absolute_url = response.urljoin(clean_link)
                if absolute_url.startswith('http'):
                    yield scrapy.Request(
                        url=absolute_url,
                        callback=self.parse_article,
                        errback=self.handle_error,
                        meta=response.meta
                    )

    def parse_article(self, response):
        try:
            article = Article(response.url)
            article.set_html(response.body)
            article.parse()
            
            # format article.publish_date in a safe way
            date_berita = None
            if article.publish_date:
                if isinstance(article.publish_date, datetime):
                    date_berita = article.publish_date.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    try:
                        parsed = datetime.fromisoformat(str(article.publish_date))
                        date_berita = parsed.strftime("%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        date_berita = str(article.publish_date)

            if article.text and len(article.text) > 50:
                yield {
                    #'id': hashlib.md5(response.url.encode('utf-8')).hexdigest(), # need to remove posgres will handle
                    'media_name': response.meta['media_name'],
                    'title': article.title,
                    'content': article.text,
                    'news_link': response.url,
                    'news_date_crawled': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'news_date': date_berita,
                    'author': ", ".join(article.authors) if article.authors else None
                }
        except Exception:
            pass 

    def handle_error(self, failure):
        request = failure.request
        media_name = request.meta.get('media_name', 'Unknown')
        
        def tulis_ke_log(kategori, alasan_detail):  
            with open('log_gagal_akses.txt', 'a', encoding='utf-8') as f:
                f.write(f"[{kategori}] | {media_name} | {alasan_detail} | {request.url}\n")

        if failure.check(HttpError):
            response = failure.value.response
            status = response.status
            
            server_header = response.headers.get(b'Server', b'').lower()
            waf_signatures = [b'cloudflare', b'akamaighost', b'sucuri', b'imperva', b'ddos-guard']
            is_waf_detected = any(waf in server_header for waf in waf_signatures)

            if status in [403, 429, 503] and is_waf_detected:
                waf_name = server_header.decode('utf-8').capitalize()

                self.logger.error(f"[WAF BLOCKED - {waf_name}] {media_name} (Status: {status}) -> {request.url}")
                tulis_ke_log("WAF_BLOCKED", f"Diblokir oleh sistem keamanan {waf_name} (HTTP {status})")
                
            elif status == 404:

                self.logger.warning(f"[NOT FOUND] {media_name} (404) -> {request.url}")
                tulis_ke_log("HTTP_404", "Halaman/RSS tidak ditemukan atau sudah dihapus oleh admin web")
                
            elif status == 403:

                self.logger.warning(f"[FORBIDDEN] {media_name} (403) -> {request.url}")
                tulis_ke_log("HTTP_403", "Akses ditolak oleh server asal (Mungkin IP proxy kita di-blacklist atau direktori dikunci)")
                
            elif status == 500:
                self.logger.warning(f"[SERVER ERROR] {media_name} (500) -> {request.url}")
                tulis_ke_log("HTTP_500", "Server website sedang rusak / Internal Server Error")
                
            else:
                self.logger.warning(f"[HTTP ERROR] {media_name} (Status: {status}) -> {request.url}")
                tulis_ke_log(f"HTTP_{status}", f"Website mengembalikan kode error HTTP {status} yang tidak terduga")
        
        # Menangkap Domain yang mati/salah ketik
        elif failure.check(DNSLookupError):

            self.logger.warning(f"[DOMAIN MATI] {media_name} DNS tidak ditemukan -> {request.url}")
            tulis_ke_log("DNS_ERROR", "Domain tidak aktif, salah ketik (typo), atau website sudah tutup permanen")
            
        # Menangkap server yang lemot/down
        elif failure.check(TimeoutError, TCPTimedOutError, ResponseNeverReceived):

            self.logger.warning(f"[TIMEOUT] {media_name} Server terlalu lambat merespons -> {request.url}")
            tulis_ke_log("TIMEOUT", "Server sangat lambat atau down, tidak merespons dalam batas waktu 15 detik")
            
        # Menangkap server yang menolak koneksi secara aktif
        elif failure.check(ConnectionRefusedError):

            self.logger.warning(f"[CONNECTION REFUSED] {media_name} Server menolak koneksi -> {request.url}")
            tulis_ke_log("CONN_REFUSED", "Server aktif secara sadar menolak koneksi kita (Mungkin sedang maintenance atau port ditutup)")
            
        # Penyelamat terakhir untuk error yang sangat aneh
        else:
            error_msg = repr(failure.value) if failure.value else "Unknown Error"

            self.logger.warning(f"[ERROR LAIN] {media_name} -> {error_msg}")
            tulis_ke_log("UNKNOWN_ERROR", f"Error tidak terdefinisi: {error_msg[:100]}...")
            
if __name__ == "__main__":

    nest_asyncio.apply()

    if not os.path.exists('proxy/ip_list.txt'):
        print("WARNING: File 'proxy/ip_list.txt' tidak ditemukan. Script akan tetap jalan tapi TANPA rotasi IP!")
    else:
        print("SUCCESS: File 'proxy/ip_list.txt' ditemukan. Rotasi IP Aktif!")
        
    print("Mulai proses crawling dengan Stealth Mode & Deduplikasi...")
    process = CrawlerProcess()
    process.crawl(UniversalNewsSpider)
    process.start()
    print("Crawling selesai!")