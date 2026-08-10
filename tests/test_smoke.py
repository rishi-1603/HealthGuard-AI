from src.features.feature_pipeline import bundle_to_frame
def test_features_exist():
    df = bundle_to_frame()
    assert len(df) > 0
    assert {'patient_id', 'risk_target'}.issubset(df.columns)
