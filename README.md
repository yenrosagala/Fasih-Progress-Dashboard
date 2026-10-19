# fasih-analytics

Tool untuk mengambil data progres dan assignment petugas survei dari platform FASIH (https://fasih-sm.bps.go.id/app) dan menghasilkan grafik monitoring serta laporan pivot Excel.

## Fitur

- Login otomatis dengan session cache (Selenium)
- Fetch data progres pencacahan dan pemutakhiran secara paralel (async)
- Interaktif memilih survei yang ingin di-scrape
- Generate grafik stacked bar per survei dan per provinsi
- Generate grafik donut status kabupaten per survei
- Generate laporan pivot Excel
- Mendukung kustomisasi judul grafik via argumen CLI


## Instalasi

```bash
# Clone repo dan masuk ke folder
cd fasih-analytics

# Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install font (macOS)
brew install --cask font-roboto-condensed
```

## Penggunaan

### Cara 1: Double-click
- **macOS**: Jalankan `launch.command` dari Finder
- **Windows**: Jalankan `launch.bat` dari File Explorer

### Cara 2: Terminal

```bash
source venv/bin/activate
python main.py
```

### Opsi CLI

| Argumen | Keterangan |
|---|---|
| `--relogin` | Hapus session cache dan login ulang |
| `--title "Judul"` | Set judul grafik progres (disimpan permanen) |
| `--user-title "Judul"` | Set judul grafik penugasan user (disimpan permanen) |
| `--kab-status-title "Judul"` | Set judul grafik donut status kabupaten (disimpan permanen) |

Contoh:
```bash
python main.py --relogin
python main.py --title "Monitoring Maret 2026"
```

### Catatan akses FASIH

Jika FASIH/BPS menampilkan peringatan `BOT-...`, hentikan script dan coba buka FASIH secara manual dari browser biasa. Jika browser biasa bisa membuka FASIH tetapi browser Selenium terkena `BOT-...`, gunakan session dari browser biasa:

1. Buka `https://fasih-sm.bps.go.id/app` di Chrome biasa dan login.
2. Buka DevTools > Network, klik request API FASIH, lalu copy nilai header `Cookie`.
3. Buat file `inputs/manual_session.json`:

```json
{
  "cookie_header": "PASTE_COOKIE_HEADER_DI_SINI"
}
```

Script akan membaca file itu lebih dulu dan tidak perlu membuka Selenium jika session valid.

Untuk membuat file itu tanpa edit manual, jalankan helper:

```bash
./venv/bin/python make_manual_session.py --from-clipboard
```

Atau kirim header langsung:

```bash
./venv/bin/python make_manual_session.py --cookie-header "PASTE_COOKIE_HEADER_DI_SINI"
```

Di macOS dan Windows, `launch.command` / `launch.bat` juga akan mencoba membaca clipboard dan membuat session file otomatis sebelum menjalankan scraping.

Jika FASIH mulai mengembalikan `504`, `429`, atau `BOT-...`, jalankan ulang dengan mode lebih pelan:

```bash
FASIH_MAX_CONCURRENCY=1 FASIH_REQUEST_INTERVAL=2 python main.py --relogin
```

## Output

- `outputs/csv/report_assignment.csv` — data progres & penugasan terbaru
- `outputs/csv/report_pemutakhiran.csv` — data pemutakhiran terbaru
- `outputs/csv/survey_collection_deadline_adjusted.csv` — metadata survei
- `outputs/pivot_report.xlsx` — laporan pivot Excel
- `images/progress_assignment.png` — grafik progres pencacahan
- `images/user_assignment.png` — grafik penugasan user
- `images/kabupaten_status.png` — grafik donut status kabupaten per survei

## Dependencies

| Package | Versi |
|---|---|
| httpx | 0.28.1 |
| InquirerPy | 0.3.4 |
| matplotlib | 3.10.8 |
| numpy | 2.4.3 |
| openpyxl | 3.1.5 |
| pandas | 3.0.1 |
| selenium | 4.41.0 |

## Deployment (Docker)

Dashboard server (`server.py`) berjalan sebagai satu proses uvicorn. Gunakan Docker:

```bash
docker build -t fasih-analytics .
docker run -p 8080:8080 \
  -e SESSION_SECRET="$(openssl rand -hex 32)" \
  -e PUBLIC_BASE_URL="https://dashboard.example.com" \
  -e GOOGLE_CLIENT_ID="..." \
  -e GOOGLE_CLIENT_SECRET="..." \
  -e GOOGLE_HD="bps.go.id" \
  -e FASIH_SESSION="<cookie_header>" \
  fasih-analytics
```

Image hanya memasang `requirements-server.txt` (runtime server). `requirements.txt` (matplotlib/pygame/openpyxl/InquirerPy) hanya untuk scraper `main.py`.

### Environment

| Variabel | Wajib | Keterangan |
|---|---|---|
| `SESSION_SECRET` | ya (prod) | Kunci tanda tangan cookie. Tanpa ini sesi login hilang tiap restart. |
| `PUBLIC_BASE_URL` | ya (prod) | URL publik (https) untuk redirect OAuth. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | ya | Jika kosong, app jalan tanpa login (mode dev). |
| `GOOGLE_HD` | tidak | Batasi domain Workspace, mis. `bps.go.id`. |
| `FASIH_SESSION` | ya (untuk refresh) | Cookie header FASIH; sesi file tidak ikut ke image. |
| `AUTH_DISABLED=1` | tidak | Paksa mode tanpa login. |
| `SESSION_TTL` | tidak | Umur cookie (detik), default 8 jam. |
| `HOST` / `PORT` | tidak | Default `0.0.0.0:PORT`; platform biasanya mengisi `PORT`. |

### Catatan

- **Satu proses saja.** Queue refresh disimpan di memori; jangan pakai banyak worker/replica.
- **Persistensi.** Hasil refresh ditulis ke `outputs/site/`; pada filesystem ephemeral hilang saat restart (site asli tetap ada di image). Untuk menyimpan, mount volume ke `/app/outputs`.
- **Sesi FASIH.** Tidak ikut ke image dan cepat kedaluwarsa. Ada dua cara menyetel: (1) dari **UI** — buka dashboard, klik **Atur Sesi**, tempel header `Cookie` dari FASIH (ada instruksi di dialognya) — sesi disimpan ke `inputs/manual_session.json` di server dan langsung dipakai tanpa restart; (2) dari **server** — setel `FASIH_SESSION` (atau mount `inputs/manual_session.json`) lalu restart. Perbarui berkala saat kedaluwarsa (banner di dashboard akan mengingatkan).
- **Ephemeral & sesi dari UI.** Pada filesystem ephemeral (tanpa volume), sesi yang diset lewat UI juga hilang saat container restart; setel ulang lewat UI atau pakai `FASIH_SESSION` agar permanen.
- Mendukung Fly.io, Render, Railway, dan VPS — arahkan ke Dockerfile ini.

## Streamlit Cloud + browser bridge

Cloud **tidak pernah** menyimpan cookie FASIH. Sesi diambil di mesin lokal dari
Chrome yang sudah login (lewat CDP), data hasil scrape dikirim ke repo data privat,
dan Cloud hanya menyajikan data itu (mode viewer read-only).

1. **Jalankan Chrome bridge** (sekali): double-click `start_bridge.cmd`. Jendela
   Chrome baru terbuka dengan remote debugging (port 9222) dan profil tersendiri —
   login FASIH di jendela itu; login tersimpan untuk seterusnya.
2. **Scrape lokal**: jalankan `python main.py` seperti biasa. CLI
   (`get_cookies_and_csrf`) mencoba bridge **otomatis** sebelum jatuh ke login
   Selenium manual — begitu Chrome bridge valid, tidak ada login ulang. (Dashboard
   Docker/`server.py` memakai `load_session()`, jadi set `FASIH_BRIDGE=1` bila ingin
   tombol refresh di sana juga ambil sesi dari bridge.) Sesi lalu di-cache ke
   `inputs/manual_session.json`.
3. **Publish data**: `python publish_data.py` menyalin `outputs/site` (`surveys.json`
   + `data/*.json`) ke repo data privat (satu commit, force-push — repo data tidak
   ikut membengkak).
4. **Cloud**: isi secrets `DATA_REPO` + `DATA_TOKEN` lewat **Settings → Secrets**.
   Saat keduanya ada, app jadi viewer: `_sync_data()` menarik blob dari repo privat
   ke folder yang disajikan, dan UI scrape (pilih survei/periode, tombol ambil data)
   tidak dirender. Tanpa secrets itu, app berperilaku seperti sebelumnya (scrape live).

| Secret | Isi |
|---|---|
| `DATA_REPO` | `yenrosagala/fasih-data` (repo **privat**, data-only). |
| `DATA_TOKEN` | Fine-grained PAT, **Contents: read-only** untuk repo data itu. |

Catatan privasi: repo kode ini publik dan hanya menyajikan dashboard; sampel
berisi PII hanya hidup di repo data privat, tidak pernah masuk repo publik.

Untuk memperbarui data di Cloud: ulangi langkah 1–3 (sesi diperbarui otomatis;
tidak ada cookie yang ditempel atau di-renew manual). Cache viewer 60 detik, jadi
Cloud menampilkan versi terbaru dalam ~1 menit.

