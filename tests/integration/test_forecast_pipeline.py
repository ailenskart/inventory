"""Integration test for the full forecast training + scoring pipeline.

Runs against the DuckDB warehouse (requires data foundation to be materialized).
"""

import os

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "data", "dev.duckdb")


def has_duckdb_with_marts():
    """Check if DuckDB exists with materialized marts."""
    try:
        import duckdb
        if not os.path.exists(DB_PATH):
            return False
        con = duckdb.connect(DB_PATH, read_only=True)
        con.execute("select 1 from main_marts.mart_demand_base limit 1")
        con.close()
        return True
    except Exception:
        return False


@pytest.mark.integration
class TestForecastPipeline:
    """End-to-end integration test for the forecasting pipeline."""

    @pytest.fixture(scope="class")
    def config(self):
        from ml.forecasting.config import ForecastConfig
        return ForecastConfig(
            db_path=DB_PATH,
            horizon_weeks=4,
            min_history_weeks=8,
            cv_n_windows=2,
            cv_step_size=4,
        )

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_data_loading(self, config):
        """Data loader returns non-empty DataFrame with expected columns."""
        from ml.forecasting.data_loader import load_demand_data

        df = load_demand_data(config)
        assert len(df) > 0
        assert "store_id" in df.columns
        assert "sku_id" in df.columns
        assert "y" in df.columns
        assert "had_stockout" in df.columns
        assert "store_cluster" in df.columns

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_stockout_censoring(self, config):
        """Stockout censoring imputes demand for stockout weeks."""
        from ml.forecasting.data_loader import apply_stockout_censoring, load_demand_data

        df = load_demand_data(config)
        censored = apply_stockout_censoring(df, config)
        assert len(censored) == len(df)

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_feature_generation(self, config):
        """Feature pipeline generates expected feature columns."""
        from ml.forecasting.data_loader import load_demand_data
        from ml.forecasting.features import generate_all_features

        df = load_demand_data(config)
        features = generate_all_features(df, config)
        assert "lag_1w" in features.columns
        assert "rolling_mean_4w" in features.columns
        assert len(features) == len(df)

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_statsforecast_preparation(self, config):
        """StatsForecast input format is valid."""
        from ml.forecasting.data_loader import load_demand_data, prepare_statsforecast_df

        df = load_demand_data(config)
        sf_df = prepare_statsforecast_df(df, config)
        assert "unique_id" in sf_df.columns
        assert "ds" in sf_df.columns
        assert "y" in sf_df.columns
        assert sf_df["unique_id"].nunique() > 0

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_full_training_pipeline(self, config):
        """Full training pipeline runs without error and produces forecasts."""
        from ml.forecasting.train import run_training_pipeline

        result = run_training_pipeline(config)
        assert result["status"] == "success"
        assert len(result["forecasts"]) > 0
        assert len(result["report"]["model_ranking"]) > 0
        assert result["report"]["model_ranking"][0]["wmape"] < 2.0  # Reasonable upper bound

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_batch_inference(self, config):
        """Batch inference writes forecasts to DuckDB."""
        from ml.forecasting.predict import run_inference_pipeline

        forecasts = run_inference_pipeline(config, write_to_db=True)
        assert len(forecasts) > 0
        assert "store_id" in forecasts.columns
        assert "sku_id" in forecasts.columns
        assert "point_forecast" in forecasts.columns
        assert "lower_bound" in forecasts.columns
        assert "upper_bound" in forecasts.columns

        # Verify written to DB
        import duckdb
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("select count(*) from main_ml.demand_forecasts").fetchone()[0]
        con.close()
        assert count > 0

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_forecast_non_negative(self, config):
        """All forecasts should be non-negative."""
        from ml.forecasting.predict import run_inference_pipeline

        forecasts = run_inference_pipeline(config, write_to_db=False)
        assert (forecasts["point_forecast"] >= 0).all()
        assert (forecasts["lower_bound"] >= 0).all()

    @pytest.mark.skipif(not has_duckdb_with_marts(), reason="DuckDB marts not available")
    def test_hierarchy_building(self, config):
        """Hierarchy tags are constructed correctly."""
        from ml.forecasting.data_loader import load_demand_data
        from ml.forecasting.hierarchy import build_hierarchy_tags

        df = load_demand_data(config)
        agg_df, tags = build_hierarchy_tags(df)
        assert "Total" in tags
        assert "Region" in tags
        assert "Bottom" in tags
        assert len(tags["Bottom"]) > 0
        assert agg_df["unique_id"].nunique() > len(tags["Bottom"])  # More series than bottom
