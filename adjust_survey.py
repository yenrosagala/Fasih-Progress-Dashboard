import pandas as pd

def adjust_period(df):
    period_df = pd.read_excel("inputs/period.xlsx")    
    period_df.set_index('name', inplace=True)
    df.set_index('name', inplace=True)
    df.update(period_df)
    df.reset_index(inplace=True)
    return df

def adjust_sample(df):
    sample_df = pd.read_excel("inputs/dspu_dspp.xlsx")
    sample_df["total"] = sample_df['sampel_utama'] + sample_df['sampel_pengganti']   
    numeric_cols = ['sampel_utama', 'sampel_pengganti', 'total']
    sample_df[numeric_cols] = sample_df[numeric_cols].fillna(0).astype(int)
    sample_df["kd_kab"] = sample_df["kd_kab"].astype(str)

    surveys_ls = ['IMK Tahunan 2025 - Pencacahan','IMK Triwulanan 2025 - PENCACAHAN']

    for survey in surveys_ls:
        if survey in sample_df['name'].unique():
            for kab in sample_df['kd_kab'].unique():
                mask = (df['name'] == survey) & (df['kd_kab'] == kab)

                # Skip if this kab doesn't exist in df for this survey
                if not mask.any():
                    continue

                sampel_utama = sample_df.loc[sample_df['kd_kab'] == kab, 'sampel_utama'].values[0]
                sampel_pengganti = sample_df.loc[sample_df['kd_kab'] == kab, 'sampel_pengganti'].values[0]

                df.loc[mask, 'total'] = sampel_utama

                open_val = df.loc[mask, 'OPEN'].values[0]
                if open_val > sampel_pengganti:
                    df.loc[mask, 'OPEN'] = open_val - sampel_pengganti
                else:
                    df.loc[mask, 'OPEN'] = 0
        else:
            continue
    
    return df

def adjust_deadline(df):
    from survey_selector import load_survey_config

    if 'other_jadwal' not in df.columns:
        df['other_jadwal'] = None

    for entry in load_survey_config():
        name = entry['name']
        mask = df['name'] == name
        if not mask.any():
            continue
        if entry.get('startDate'):
            df.loc[mask, 'startDate'] = entry['startDate']
        if entry.get('endDate'):
            df.loc[mask, 'endDate'] = entry['endDate']
        df.loc[mask, 'other_jadwal'] = entry.get('other_jadwal') or None

    return df
