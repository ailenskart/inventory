"""Unit tests for the demand forecasting engine."""

import numpy as np
import pandas as pd
import pytest

from ml.forecasting.config import ForecastConfig
from ml.forecasting.evaluation import bias, coverage, mae, mase, wmape


# ─── Evaluation Metrics ─────────────────────────────────────────────────────


class TestWMAPE:
    def test_perfect_forecast(self):
        y = np.array([10, 20, 30])
        assert wmape(y, y) == 0.0

    def test_known_values(self):
        y_true = np.array([100, 200, 300])
        y_pred = np.array([110, 180, 330])
        # |100-110| + |200-180| + |300-330| = 10 + 20 + 30 = 60
        # sum(|actual|) = 600
        assert wmape(y_true, y_pred) == pytest.approx(0.1)

    def test_zero_actual(self):
        y_true = np.array([0, 0, 0])
        y_pred = np.array([1, 2, 3])
        assert np.isnan(wmape(y_true, y_pred))

    def test_single_value(self):
        assert wmape(np.array([100]), np.array([120])) == pytest.approx(0.2)


class TestMASE:
    def test_better_than_naive(self):
        y_train = np.array([10, 12, 11, 13, 10, 12, 11, 13], dtype=float)
        y_true = np.array([14, 15], dtype=float)
        y_pred = np.array([14.1, 14.9], dtype=float)  # Very close predictions
        result = mase(y_true, y_pred, y_train, season_length=4)
        assert isinstance(result, float)
        # Seasonal naive error is 0 (repeating pattern), so MASE is nan
        # Use non-repeating pattern instead
        y_train2 = np.array([10, 15, 12, 18, 11, 16, 13, 20], dtype=float)
        result2 = mase(y_true, y_pred, y_train2, season_length=4)
        assert result2 < 1.0  # Better than seasonal naive

    def test_short_training(self):
        y_train = np.array([10, 12])
        y_true = np.array([14])
        y_pred = np.array([13])
        result = mase(y_true, y_pred, y_train, season_length=4)
        assert isinstance(result, float)


class TestBias:
    def test_over_forecasting(self):
        y_true = np.array([100, 100, 100])
        y_pred = np.array([120, 120, 120])
        assert bias(y_true, y_pred) > 0  # Positive bias = over-forecasting

    def test_under_forecasting(self):
        y_true = np.array([100, 100, 100])
        y_pred = np.array([80, 80, 80])
        assert bias(y_true, y_pred) < 0  # Negative bias = under-forecasting

    def test_unbiased(self):
        y_true = np.array([100, 100])
        y_pred = np.array([90, 110])  # Errors cancel out
        assert bias(y_true, y_pred) == pytest.approx(0.0)


class TestMAE:
    def test_perfect(self):
        y = np.array([10, 20, 30])
        assert mae(y, y) == 0.0

    def test_known(self):
        y_true = np.array([10, 20, 30])
        y_pred = np.array([12, 18, 33])
        # |10-12| + |20-18| + |30-33| = 2 + 2 + 3 = 7, mean = 7/3
        assert mae(y_true, y_pred) == pytest.approx(7 / 3)


class TestCoverage:
    def test_all_within(self):
        y = np.array([10, 20, 30])
        lo = np.array([5, 15, 25])
        hi = np.array([15, 25, 35])
        assert coverage(y, lo, hi) == 1.0

    def test_none_within(self):
        y = np.array([10, 20, 30])
        lo = np.array([15, 25, 35])
        hi = np.array([20, 30, 40])
        assert coverage(y, lo, hi) == 0.0

    def test_partial(self):
        y = np.array([10, 20, 30, 40])
        lo = np.array([5, 25, 25, 45])
        hi = np.array([15, 30, 35, 50])
        assert coverage(y, lo, hi) == 0.5


# ─── Config ──────────────────────────────────────────────────────────────────


class TestForecastConfig:
    def test_defaults(self):
        config = ForecastConfig()
        assert config.horizon_weeks == 4
        assert config.season_length == 52
        assert 0.5 in config.quantiles
        assert config.censor_stockout_demand is True

    def test_custom(self):
        config = ForecastConfig(horizon_weeks=8, target_column="sell_through_signal")
        assert config.horizon_weeks == 8
        assert config.target_column == "sell_through_signal"


# ─── Data Loader (unit-testable parts) ──────────────────────────────────────


class TestStockoutCensoring:
    def test_imputes_stockout_weeks(self):
        from ml.forecasting.data_loader import apply_stockout_censoring

        config = ForecastConfig(censor_stockout_demand=True, stockout_imputation_method="mean")
        df = pd.DataFrame({
            "store_id": ["S1"] * 6,
            "sku_id": ["K1"] * 6,
            "y": [10, 12, 0, 11, 0, 13],
            "had_stockout": [0, 0, 1, 0, 1, 0],
        })

        result = apply_stockout_censoring(df, config)
        # Stockout weeks (idx 2, 4) should be imputed with mean of non-stockout (10,12,11,13)=11.5
        assert result.loc[2, "y"] == pytest.approx(11.5)
        assert result.loc[4, "y"] == pytest.approx(11.5)

    def test_no_censoring_when_disabled(self):
        from ml.forecasting.data_loader import apply_stockout_censoring

        config = ForecastConfig(censor_stockout_demand=False)
        df = pd.DataFrame({
            "store_id": ["S1"] * 4,
            "sku_id": ["K1"] * 4,
            "y": [10, 0, 12, 0],
            "had_stockout": [0, 1, 0, 1],
        })

        result = apply_stockout_censoring(df, config)
        assert result["y"].tolist() == [10, 0, 12, 0]


class TestPrepareStatsforecastDf:
    def test_format(self):
        from ml.forecasting.data_loader import prepare_statsforecast_df

        config = ForecastConfig(min_history_weeks=2)
        df = pd.DataFrame({
            "store_id": ["S1"] * 4 + ["S2"] * 4,
            "sku_id": ["K1"] * 4 + ["K2"] * 4,
            "week_start": pd.date_range("2024-01-01", periods=4, freq="W").tolist() * 2,
            "y": [10, 12, 11, 13, 5, 6, 7, 8],
        })

        result = prepare_statsforecast_df(df, config)
        assert "unique_id" in result.columns
        assert "ds" in result.columns
        assert "y" in result.columns
        assert result["unique_id"].nunique() == 2

    def test_filters_short_series(self):
        from ml.forecasting.data_loader import prepare_statsforecast_df

        config = ForecastConfig(min_history_weeks=5)
        df = pd.DataFrame({
            "store_id": ["S1"] * 3,
            "sku_id": ["K1"] * 3,
            "week_start": pd.date_range("2024-01-01", periods=3, freq="W"),
            "y": [10, 12, 11],
        })

        result = prepare_statsforecast_df(df, config)
        assert len(result) == 0  # Filtered out


# ─── Feature Generation ─────────────────────────────────────────────────────


class TestFeatureGeneration:
    def test_lag_features(self):
        from ml.forecasting.features import generate_lag_features

        config = ForecastConfig(lag_weeks=[1, 2])
        df = pd.DataFrame({
            "store_id": ["S1"] * 5,
            "sku_id": ["K1"] * 5,
            "week_start": pd.date_range("2024-01-01", periods=5, freq="W"),
            "y": [10, 20, 30, 40, 50],
        })

        result = generate_lag_features(df, config)
        assert "lag_1w" in result.columns
        assert "lag_2w" in result.columns
        assert result.iloc[2]["lag_1w"] == 20
        assert result.iloc[2]["lag_2w"] == 10

    def test_rolling_features(self):
        from ml.forecasting.features import generate_rolling_features

        config = ForecastConfig(rolling_windows=[2])
        df = pd.DataFrame({
            "store_id": ["S1"] * 5,
            "sku_id": ["K1"] * 5,
            "week_start": pd.date_range("2024-01-01", periods=5, freq="W"),
            "y": [10, 20, 30, 40, 50],
        })

        result = generate_rolling_features(df, config)
        assert "rolling_mean_2w" in result.columns
        assert "rolling_std_2w" in result.columns

    def test_calendar_features(self):
        from ml.forecasting.features import generate_calendar_features

        df = pd.DataFrame({
            "week_start": pd.date_range("2024-01-01", periods=4, freq="W"),
            "is_festive": [0, 1, 0, 0],
        })

        result = generate_calendar_features(df)
        assert "week_of_year" in result.columns
        assert "week_sin" in result.columns
        assert "month_cos" in result.columns

    def test_full_pipeline(self):
        from ml.forecasting.features import generate_all_features

        config = ForecastConfig(lag_weeks=[1], rolling_windows=[2])
        df = pd.DataFrame({
            "store_id": ["S1"] * 8,
            "sku_id": ["K1"] * 8,
            "week_start": pd.date_range("2024-01-01", periods=8, freq="W"),
            "total_qty_sold": [10, 20, 30, 40, 50, 60, 70, 80],
            "sell_through_signal": [5, 10, 15, 20, 25, 30, 35, 40],
            "prescription_order_signal": [2, 3, 4, 5, 6, 7, 8, 9],
            "display_interest_signal": [10, 12, 14, 16, 18, 20, 22, 24],
            "had_stockout": [0, 0, 1, 0, 0, 0, 1, 0],
            "is_festive": [0, 0, 0, 1, 0, 0, 0, 0],
            "sku_type": ["physical_sell"] * 8,
            "fulfillment_type": ["direct_sell"] * 8,
            "category": ["eyeglasses"] * 8,
            "lifecycle_stage": ["growth"] * 8,
            "store_cluster": ["METRO_HIGH"] * 8,
            "mrp": [2000] * 8,
        })

        result = generate_all_features(df, config)
        assert "y" in result.columns
        assert "lag_1w" in result.columns
        assert len(result) == 8


# ─── Evaluation Report ──────────────────────────────────────────────────────


class TestEvaluationReport:
    def test_evaluate_forecasts(self):
        from ml.forecasting.evaluation import evaluate_forecasts

        cv = pd.DataFrame({
            "unique_id": ["S1__K1"] * 4,
            "ds": pd.date_range("2024-01-01", periods=4, freq="W"),
            "y": [100, 200, 150, 180],
            "AutoETS": [110, 190, 160, 170],
        })

        metrics = evaluate_forecasts(cv, "AutoETS")
        assert "wmape" in metrics
        assert "mae" in metrics
        assert "bias" in metrics
        assert metrics["n_observations"] == 4

    def test_per_series_evaluation(self):
        from ml.forecasting.evaluation import evaluate_per_series

        cv = pd.DataFrame({
            "unique_id": ["S1__K1"] * 4 + ["S2__K2"] * 4,
            "ds": pd.date_range("2024-01-01", periods=4, freq="W").tolist() * 2,
            "y": [100, 200, 150, 180, 50, 60, 55, 65],
            "AutoETS": [110, 190, 160, 170, 48, 62, 53, 67],
        })

        result = evaluate_per_series(cv, "AutoETS")
        assert len(result) == 2
        assert "wmape" in result.columns
        assert "bias" in result.columns
