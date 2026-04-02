# Scrap Website News

Universal news scraper untuk mengumpulkan berita dari ratusan media Indonesia melalui RSS feed dan Sitemap XML.

## Fitur

- **Multi-source crawling** — mendukung RSS feed dan Sitemap XML (termasuk sitemap index)
- **Stealth mode** — rotasi User-Agent, human-like headers, dan randomized request delay
- **Proxy rotation** — rotasi IP otomatis dari daftar proxy
- **Deduplikasi** — mencegah berita duplikat berdasarkan kombinasi `media_name + title`
- **Article extraction** — parsing konten artikel otomatis menggunakan newspaper3k
- **Daily output** — output file bernama sesuai tanggal crawling (`hasil_berita_YYYY-MM-DD.json`)
- **Error logging** — log detail untuk setiap kegagalan akses (WAF block, timeout, DNS error, dll)

## Struktur Direktori

```
scrap/
├── main.py                  # Spider utama (RSS, Sitemap, Article parser)
├── middlewares.py            # Middleware (proxy, UA rotation) & pipeline (deduplikasi)
├── requirements.txt         # Dependencies
├── config/
│   ├── crawler_config.json  # Daftar media & URL target (JSONL)
│   └── user-agents.txt      # Daftar User-Agent untuk rotasi
├── proxy/
│   ├── ip_list.txt          # Daftar proxy (tidak di-commit)
│   └── check_proxy.py       # Script validasi proxy
└── output/                  # Hasil crawling (tidak di-commit)
    └── hasil_berita_YYYY-MM-DD.json
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Konfigurasi media target

Edit `config/crawler_config.json` dalam format JSONL. Setiap baris berisi satu media:

```json
{"media_name":"Harian Jogja","media_website":"www.harianjogja.com","base_url":"https://www.harianjogja.com","target_url":"https://www.harianjogja.com/sitemap.xml","crawl_method":"sitemap"}
```

Field `crawl_method` yang didukung: `rss`, `sitemap`

### 3. Setup proxy (opsional)

Tambahkan daftar proxy ke `proxy/ip_list.txt` dengan format satu proxy per baris:

```
ip:port
ip:port
```

Validasi proxy yang aktif:

```bash
cd proxy
python check_proxy.py
```

## Cara Menjalankan

```bash
python main.py
```

Output akan tersimpan di `output/hasil_berita_YYYY-MM-DD.json` dalam format JSON Lines.

## Format Output

Setiap baris di file output berisi satu artikel:

```json
{
  "media_name": "Harian Jogja",
  "title": "Judul Berita",
  "content": "Isi lengkap artikel...",
  "news_link": "https://example.com/berita/123",
  "news_date_crawled": "2026-04-01 10:30:00",
  "news_date": "2026-04-01 08:00:00",
  "author": "Nama Penulis"
}
```

## Error Log

Kegagalan akses tercatat di `log_gagal_akses.txt` dengan kategori:

| Kategori | Deskripsi |
|----------|-----------|
| `WAF_BLOCKED` | Diblokir oleh Cloudflare, Akamai, dll |
| `HTTP_403` | Akses ditolak server |
| `HTTP_404` | Halaman tidak ditemukan |
| `HTTP_500` | Server error |
| `DNS_ERROR` | Domain tidak aktif / salah |
| `TIMEOUT` | Server tidak merespons dalam 15 detik |
| `CONN_REFUSED` | Server menolak koneksi |

gege geming
