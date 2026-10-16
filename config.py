APP_BASE_URL = "https://fasih-sm.bps.go.id/app"
LOGIN_URL = APP_BASE_URL
API_BASE_URL = f"{APP_BASE_URL}/api"
SURVEY_PAGE_URL = f"{APP_BASE_URL}/survey-collection/survey"

BASE_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://fasih-sm.bps.go.id",
    "Referer": SURVEY_PAGE_URL,
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

payload_survey ={
    "pageNumber": 0,
    "pageSize": 100,
    "sortBy": "CREATED_AT",
    "sortDirection": "DESC",
    "keywordSearch": ""
}

survey_datatable_url = f"{API_BASE_URL}/survey/api/v1/surveys/datatable?surveyType=pencacahan"
surveys_base_url = f"{API_BASE_URL}/survey/api/v1/surveys/"
survey_periods_url = f"{API_BASE_URL}/survey/api/v1/survey-periods/my?surveyId="
myinfo_url = f"{API_BASE_URL}/survey/api/v1/users/myinfo?surveyPeriodId="
region_level1_url = f"{API_BASE_URL}/region/api/v1/region/level1?groupId="
region_level2_url = f"{API_BASE_URL}/region/api/v1/region/level2?groupId="

report_user_assignment_url = f"{API_BASE_URL}/analytic/api/v2/assignment/report-user-assignment"
report_progress_assignment_url = f"{API_BASE_URL}/analytic/api/v2/assignment/report-progress-assignment"

# Powers the survey "Data" tab: one row per sampled unit for a survey period.
datatable_all_user_url = f"{API_BASE_URL}/analytic/api/v2/assignment/datatable-all-user-survey-periode"

# The FASIH data-tab endpoint returns each survey's sample columns as bare
# positional keys (data1..data10) with no header metadata, so titles cannot be
# scraped from the response. Map them per survey instead: the key is a
# case-insensitive substring of the survey name, the value its labels.
#
# Only surveys whose headers we have confirmed belong here. Anything else shows
# an honest "Data 1..10" rather than a label borrowed from another survey -
# the old single shared map put names like "Desa" on columns holding a status.
data_column_labels_by_survey = {
    "SITASI": {
        "data1": "Wilayah",
        "data2": "No. Urut",
        "data3": "Jenis",
        "data4": "Kategori Sampel",
        "data5": "Nama Usaha",
        "data6": "Nama Responden",
        "data7": "Desa",
        "data8": "Komoditas",
        "data9": "Komoditas Utama",
    },
}

pemutakhiran_base_url = f"{API_BASE_URL}/assignment-general/api/assignment-region/datatable?periodeId="
pemutakhiran_payload = {
    "draw": 2,
    "columns": [
        {"data": 0, "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
        {"data": 1, "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
        {"data": 2, "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
        {"data": 3, "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
        {"data": 4, "name": "", "searchable": True, "orderable": True, "search": {"value": "", "regex": False}},
    ],
    "order": [{"column": 0, "dir": "asc"}],
    "start": 0,
    "length": 5000,
    "search": {"value": "", "regex": False}
}
pemutakhiran_status_order = ['SudahTarikSampel', 'SelesaiListing', 'BelumSelesaiListing']

progress_status_order = [
'COMPLETED BY Admin Kabupaten',
'COMPLETED BY ADMIN PROVINSI',
'COMPLETED BY Pengawas',
'clean',
'APPROVED BY ADMIN KABUPATEN',
'APPROVED BY ADMIN PROVINSI',
'APPROVED BY Admin Kabupaten',
'APPROVED BY PENGAWAS',
'APPROVED BY Pengawas',
'SUBMITTED BY PENCACAH',
'SUBMITTED BY Pencacah',
'SUBMITTED RESPONDENT',
'DRAFT',
'EDITED BY Admin Kabupaten',
'EDITED BY ADMIN KABUPATEN',
'EDITED BY Admin Pusat',
'REJECTED BY Admin Kabupaten',
'REJECTED BY PENGAWAS',
'REJECTED BY Pengawas',
'REVOKED BY Admin Kabupaten',
'REVOKED BY PENGAWAS',
'REVOKED BY Pengawas',
'OPEN',
'belum_entry']

assignment_status_order = ['assigned', 'have-not-assigned']

palette_options = {
    "Ocean": {
        'COMPLETED': '#5cc08a',   # medium green (Completed by Admin Kab/Kota)
        'clean': '#5cc08a',
        'OPEN': '#1da8c7',        # teal blue (Sisa Target)
        'belum_entry': '#1da8c7',
        'APPROVED': '#aee0c3',    # light green (Approved by PML)
        'EDITED': '#b2b2b2',      # medium gray (Edited by Admin Kab/Kota)
        'REJECTED': '#93d2e4',    # light blue (Rejected by Admin Kab/Kota)
        'REVOKED': '#fee281',     # light yellow (Revoked by Admin Kab/Kota)
        'SUBMITTED': '#cccccc',   # light gray (Submitted by PCL)
        'DRAFT': '#a0d8e8',       # pale blue
        'SELESAILISTING': '#aee0c3',
        'BELUMSELESAILISTING': '#1da8c7',
        'SUDAHTARIKSAMPEL': '#5cc08a',
        'assigned': '#5cc08a',
        'have-not-assigned': '#1da8c7',
    },
    "Professional": {
        # Clean, semantically meaningful, print-friendly
        'COMPLETED': '#4CAF50',   # medium green
        'clean': '#4CAF50',
        'OPEN': '#F44336',        # medium red
        'belum_entry': '#F44336',
        'APPROVED': '#90A4AE',    # blue-grey (neutral)
        'EDITED': '#42A5F5',      # medium blue
        'REJECTED': '#FF7043',    # orange-red (distinct from OPEN)
        'REVOKED': '#AB47BC',     # medium purple
        'SUBMITTED': '#F2C94C',   # amber/orange
        'DRAFT': '#78909C',       # steel blue-grey
        'SELESAILISTING': '#90A4AE',
        'BELUMSELESAILISTING': '#F44336',
        'SUDAHTARIKSAMPEL': '#4CAF50',
        'assigned': '#4CAF50',
        'have-not-assigned': '#F44336',
    },
    "Warm": {
        # Softer tones, good for presentations
        'COMPLETED': '#81C784',   # soft green
        'clean': '#81C784',
        'OPEN': '#E57373',        # soft red
        'belum_entry': '#E57373',
        'APPROVED': '#B0BEC5',    # light blue-grey
        'EDITED': '#64B5F6',      # soft blue
        'REJECTED': '#FF8A65',    # soft orange (distinct from OPEN)
        'REVOKED': '#CE93D8',     # soft purple
        'SUBMITTED': '#FFD54F',   # soft yellow (darker than pastel)
        'DRAFT': '#A1887F',       # warm brown-grey
        'SELESAILISTING': '#B0BEC5',
        'BELUMSELESAILISTING': '#E57373',
        'SUDAHTARIKSAMPEL': '#81C784',
        'assigned': '#81C784',
        'have-not-assigned': '#E57373',
    },
    "Vivid": {
        'COMPLETED': '#00C853',
        'clean': '#00C853',
        'OPEN': '#D50000',
        'belum_entry': '#D50000',
        'APPROVED': '#9E9E9E',
        'EDITED': '#2962FF',
        'REJECTED': '#FF6D00',    # orange (distinct from OPEN dark red)
        'REVOKED': '#AA00FF',
        'SUBMITTED': '#FFD600',
        'DRAFT': '#00BCD4',       # cyan (distinct from REVOKED purple)
        'SELESAILISTING': '#9E9E9E',
        'BELUMSELESAILISTING': '#D50000',
        'SUDAHTARIKSAMPEL': '#00C853',
        'assigned': '#00C853',
        'have-not-assigned': '#D50000',
    },
    "Muted": {
        'COMPLETED': '#66BB6A',
        'clean': '#66BB6A',
        'OPEN': '#EF5350',
        'belum_entry': '#EF5350',
        'APPROVED': '#BDBDBD',
        'EDITED': '#64B5F6',
        'REJECTED': '#FFA07A',    # light salmon (distinct from OPEN)
        'REVOKED': '#BA68C8',
        'SUBMITTED': '#FFB74D',   # soft orange (visible on white)
        'DRAFT': '#9575CD',
        'SELESAILISTING': '#BDBDBD',
        'BELUMSELESAILISTING': '#EF5350',
        'SUDAHTARIKSAMPEL': '#66BB6A',
        'assigned': '#66BB6A',
        'have-not-assigned': '#EF5350',
    },
    "Pastel": {
        'COMPLETED': '#B5EAD7',
        'clean': '#B5EAD7',
        'OPEN': '#FF9AA2',        # soft pink-red
        'belum_entry': '#FF9AA2',
        'APPROVED': '#D3D3D3',
        'EDITED': '#ADD8E6',
        'REJECTED': '#FFDAC1',    # soft peach (distinct from OPEN)
        'REVOKED': '#C7CEEA',     # soft periwinkle (distinct from others)
        'SUBMITTED': '#FFFACD',   # lemon chiffon (slightly more visible)
        'DRAFT': '#E0BBE4',
        'SELESAILISTING': '#D3D3D3',
        'BELUMSELESAILISTING': '#FF9AA2',
        'SUDAHTARIKSAMPEL': '#B5EAD7',
        'assigned': '#B5EAD7',
        'have-not-assigned': '#FF9AA2',
    },
    "Pastel_v2": {
        # Slightly deeper pastels — just a touch more depth than Pastel
        'COMPLETED': '#93D9B9',   # slightly deeper mint
        'clean': '#93D9B9',
        'OPEN': '#F0838C',        # slightly deeper rose
        'belum_entry': '#F0838C',
        'APPROVED': '#BFBFBF',    # slightly deeper grey
        'EDITED': '#94C5D9',      # slightly deeper sky blue
        'REJECTED': '#F4BFA2',    # slightly deeper peach
        'REVOKED': '#B1B9DE',     # slightly deeper periwinkle
        'SUBMITTED': '#F7F1BE',   # soft lemon
        'DRAFT': '#D0A4D5',       # slightly deeper lavender
        'SELESAILISTING': '#BFBFBF',
        'BELUMSELESAILISTING': '#F0838C',
        'SUDAHTARIKSAMPEL': '#93D9B9',
        'assigned': '#93D9B9',
        'have-not-assigned': '#F0838C',
    },
    "DarkMode": {
        'COMPLETED': '#2E7D32',
        'clean': '#2E7D32',
        'OPEN': '#C62828',
        'belum_entry': '#C62828',
        'APPROVED': '#607D8B',    # blue-grey (more visible than near-black)
        'EDITED': '#0277BD',
        'REJECTED': '#E65100',    # deep orange (distinct from OPEN)
        'REVOKED': '#6A1B9A',
        'SUBMITTED': '#F9A825',
        'DRAFT': '#00838F',       # dark cyan (distinct from REVOKED purple)
        'SELESAILISTING': '#607D8B',
        'BELUMSELESAILISTING': '#C62828',
        'SUDAHTARIKSAMPEL': '#2E7D32',
        'assigned': '#2E7D32',
        'have-not-assigned': '#C62828',
    },
    "HighContrast": {
        'COMPLETED': '#00C853',   # strong green (less harsh than #00FF00)
        'clean': '#00C853',
        'OPEN': '#D50000',        # strong red (less harsh than #FF0000)
        'belum_entry': '#D50000',
        'APPROVED': '#757575',
        'EDITED': '#0091EA',
        'REJECTED': '#FF6D00',    # orange
        'REVOKED': '#AA00FF',
        'SUBMITTED': '#FFD600',   # yellow
        'DRAFT': '#00B8D4',       # cyan
        'SELESAILISTING': '#757575',
        'BELUMSELESAILISTING': '#D50000',
        'SUDAHTARIKSAMPEL': '#00C853',
        'assigned': '#00C853',
        'have-not-assigned': '#D50000',
    },
}
