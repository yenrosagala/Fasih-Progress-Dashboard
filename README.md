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
