import pandas as pd

def load_temp_data(path):
    return pd.read_csv(path)

def get_survey_name(survey_collection_df, surveyPeriodId):
    return survey_collection_df.loc[
        survey_collection_df['survey_period_id'] == surveyPeriodId, 'name'].iloc[0]