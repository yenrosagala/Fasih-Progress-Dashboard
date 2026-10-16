import pandas as pd

def pemutakhiran_json_to_df(data, survey_name):
    records = []
    for item in data:
        level2 = item['region']['level_1']['level_2']
        records.append({
            'kd_kab': level2['full_code'],
            'doneListing': item['doneListing'],
            'doneTarikSample': item['doneTarikSample'],
        })
    df = pd.DataFrame(records)
    agg = df.groupby('kd_kab').agg(
        _listing_done=('doneListing', 'sum'),
        SudahTarikSampel=('doneTarikSample', 'sum'),
        BelumSelesaiListing=('doneListing', lambda x: (~x).sum()),
        total=('doneListing', 'count')
    ).reset_index()
    # SelesaiListing = listed but not yet tarik sampel
    agg['SelesaiListing'] = agg['_listing_done'] - agg['SudahTarikSampel']
    agg.drop(columns=['_listing_done'], inplace=True)
    agg['name'] = survey_name
    agg['type'] = 'pemutakhiran'
    agg['time_stamp'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    return agg

def json_to_df(json_data, prov_id, survey_name):
    rows = []
    for item in json_data:
        row = {'kd_kab': item.get('label')}
        for val in item.get('values', []):
            row[val.get('label')] = val.get('value')
        rows.append(row)

    tab = pd.DataFrame(rows)
    tab['prov_id'] = prov_id
    tab['name'] = survey_name
    tab['time_stamp'] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    return tab