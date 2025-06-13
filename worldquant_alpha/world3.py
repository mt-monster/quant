import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.model_selection import TimeSeriesSplit, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import confusion_matrix, classification_report, roc_auc_score, roc_curve
from sklearn.feature_selection import RFE
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb
from imblearn.over_sampling import SMOTE
import akshare as ak
import warnings

warnings.filterwarnings('ignore')

# Set matplotlib font to display English properly
plt.rcParams["font.family"] = ["Arial", "sans-serif"]


class CSIMarketPredictor:
    def __init__(self):
        """Initialize market predictor"""
        self.model = None
        self.scaler = StandardScaler()
        self.feature_importance = None
        self.selected_features = None

    def fetch_data(self, index_code="sh000300", start_date="20220601", end_date="20250610"):
        """Fetch CSI 300 data using akshare"""
        print("Fetching CSI 300 data...")
        try:
            # Get CSI 300 index data
            df = ak.stock_zh_index_daily(symbol=index_code)

            # Check if data is successfully retrieved
            if df.empty:
                raise ValueError("Retrieved data is empty. Please check akshare API.")

            # Convert date format
            df['date'] = pd.to_datetime(df['date'])

            # Filter date range
            df = df[(df['date'] >= pd.to_datetime(start_date, format='%Y%m%d')) &
                    (df['date'] <= pd.to_datetime(end_date, format='%Y%m%d'))]

            # Reset index
            df.reset_index(drop=True, inplace=True)

            # Check if there is data after filtering
            if df.empty:
                raise ValueError(f"No data found in the specified date range {start_date} to {end_date}")

            # Rename columns to match original code
            df.rename(columns={
                'date': 'Date',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            }, inplace=True)

            print(f"Successfully retrieved {len(df)} rows of data")
            return df

        except Exception as e:
            print(f"Data fetch failed: {e}")
            # Use simulated data for demonstration
            print("Using simulated data for demonstration...")
            dates = pd.date_range(start=pd.to_datetime(start_date, format='%Y%m%d'),
                                  end=pd.to_datetime(end_date, format='%Y%m%d'), freq='B')
            np.random.seed(42)
            close = 5000 * np.cumprod(1 + np.random.normal(0, 0.01, len(dates)))
            df = pd.DataFrame({
                'Date': dates,
                'Open': close * (1 + np.random.normal(0, 0.005, len(dates))),
                'High': close * (1 + np.random.normal(0.002, 0.005, len(dates))),
                'Low': close * (1 + np.random.normal(-0.002, 0.005, len(dates))),
                'Close': close,
                'Volume': np.random.randint(1e9, 1e10, len(dates))
            })
            return df

    def preprocess_data(self, df):
        """Data preprocessing and feature engineering"""
        print("Performing data preprocessing and feature engineering...")

        # Ensure data is sorted by date
        df.sort_values('Date', inplace=True)

        # Calculate daily return
        df['Daily_Return'] = df['Close'].pct_change()

        # Calculate moving averages
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()

        # Calculate RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Calculate MACD
        df['EMA12'] = df['Close'].ewm(span=12, adjust=False).mean()  # Fast line
        df['EMA26'] = df['Close'].ewm(span=26, adjust=False).mean()  # Slow line
        df['MACD'] = df['EMA12'] - df['EMA26']  # Fast line - Slow line
        df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()  # Signal line
        df['Histogram'] = df['MACD'] - df['Signal']  # MACD histogram

        # Calculate Bollinger Bands
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        df['BB_Upper'] = df['BB_Middle'] + 2 * df['Close'].rolling(window=20).std()
        df['BB_Lower'] = df['BB_Middle'] - 2 * df['Close'].rolling(window=20).std()
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']

        # Calculate volume volatility
        df['Volume_Volatility'] = df['Volume'].rolling(window=20).std()

        # Calculate target variable - whether next day's return exceeds threshold
        df['Target'] = (df['Daily_Return'].shift(-1) > 0.0025).astype(int)

        # Check data before dropping NaN
        before_drop = len(df)
        df.dropna(inplace=True)
        after_drop = len(df)

        print(f"Removed missing values: {before_drop - after_drop} rows deleted")

        # Check if there is enough data after processing
        if len(df) < 100:
            raise ValueError("Insufficient samples after preprocessing for effective modeling")

        return df

    def feature_selection(self, df):
        """Feature selection"""
        print("Performing feature selection...")

        # Separate features and target variable
        X = df.drop(['Date', 'Target', 'BB_Middle', 'BB_Upper', 'BB_Lower'], axis=1)
        y = df['Target']

        # Check if features and target are valid
        if X.empty or y.empty:
            raise ValueError("Feature matrix or target variable is empty. Cannot perform feature selection.")

        # Stage 1: Filter method - based on correlation
        corr_matrix = X.corrwith(y).abs()
        filtered_features = corr_matrix[corr_matrix > 0.025].index.tolist()

        # Ensure enough features are selected
        if len(filtered_features) < 5:
            print("Warning: Insufficient features selected by correlation. Using all features for next stage.")
            filtered_features = X.columns.tolist()

        X_filtered = X[filtered_features]

        # Stage 2: Wrapper method - using RFE
        estimator = LogisticRegression(random_state=42)
        selector = RFE(estimator, n_features_to_select=min(15, len(filtered_features)), step=1)
        X_rfe = selector.fit_transform(X_filtered, y)
        rfe_support = selector.get_support()
        rfe_features = X_filtered.columns[rfe_support].tolist()

        # Stage 3: Embedded method - using LightGBM
        model = lgb.LGBMClassifier(random_state=42)
        model.fit(X_rfe, y)
        feature_importance = pd.Series(model.feature_importances_, index=rfe_features).sort_values(ascending=False)

        # Ensure at least one feature is selected
        n_top_features = min(10, len(rfe_features))
        top_features = feature_importance.head(n_top_features).index.tolist()

        self.selected_features = top_features
        print(f"Final selected features: {top_features}")

        return X[top_features], y

    def train_model(self, X, y, test_size=0.2):
        """Train LightGBM model"""
        print("Training model...")

        # Check if there is enough data
        if len(X) < 100:
            raise ValueError("Insufficient samples for effective modeling")

        # Split data into training and test sets
        train_size = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:train_size], X.iloc[train_size:]
        y_train, y_test = y.iloc[:train_size], y.iloc[train_size:]

        # Check if training and test sets are valid
        if X_train.empty or y_train.empty or X_test.empty or y_test.empty:
            raise ValueError("Training or test set is empty. Cannot train model.")

        # Standardize features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Handle class imbalance
        smote = SMOTE(random_state=42)
        X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)

        # Define parameter grid
        param_grid = {
            'n_estimators': [100, 200, 300],
            'learning_rate': [0.05, 0.1, 0.15],
            'max_depth': [3, 5, 7],
            'min_child_samples': [20, 50, 100],
            'reg_alpha': [0, 0.1, 1]
        }

        # Time series cross-validation
        tscv = TimeSeriesSplit(n_splits=min(5, len(X_train_resampled) // 10))

        # Grid search
        model = lgb.LGBMClassifier(random_state=42)
        grid_search = GridSearchCV(
            estimator=model,
            param_grid=param_grid,
            cv=tscv,
            scoring='roc_auc',
            n_jobs=-1
        )
        grid_search.fit(X_train_resampled, y_train_resampled)

        # Best model
        self.model = grid_search.best_estimator_
        print(f"Best parameters: {grid_search.best_params_}")

        # Predict
        y_pred_proba = self.model.predict_proba(X_test_scaled)[:, 1]
        y_pred = self.model.predict(X_test_scaled)

        # Evaluate model
        self.evaluate_model(y_test, y_pred, y_pred_proba)

        return X_test_scaled, y_test, y_pred, y_pred_proba

    def evaluate_model(self, y_true, y_pred, y_pred_proba):
        """Evaluate model performance"""
        print("\nModel Evaluation:")
        # Calculate AUC
        auc = roc_auc_score(y_true, y_pred_proba)
        print(f"AUC: {auc:.4f}")

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred)
        print("\nConfusion Matrix:")
        print(cm)

        # Classification report
        cr = classification_report(y_true, y_pred)
        print("\nClassification Report:")
        print(cr)

        # Plot ROC curve
        self.plot_roc_curve(y_true, y_pred_proba)

    def plot_roc_curve(self, y_true, y_pred_proba):
        """Plot ROC curve"""
        fpr, tpr, _ = roc_curve(y_true, y_pred_proba)

        plt.figure(figsize=(10, 6))
        plt.plot(fpr, tpr, color='darkorange', lw=2,
                 label=f'ROC Curve (AUC = {roc_auc_score(y_true, y_pred_proba):.2f})')
        plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--')
        plt.xlim([0.0, 1.0])
        plt.ylim([0.0, 1.05])
        plt.xlabel('False Positive Rate')
        plt.ylabel('True Positive Rate')
        plt.title('Receiver Operating Characteristic Curve')
        plt.legend(loc="lower right")
        plt.grid(True)
        plt.show()  # Display the plot
        plt.close()

    def backtest_strategy(self, df, X_test, y_test, y_pred):
        """Backtest trading strategy"""
        print("Backtesting trading strategy...")

        # Get dates for test set
        test_size = len(y_test)
        if test_size == 0:
            raise ValueError("Test set is empty. Cannot perform strategy backtest.")

        test_dates = df['Date'].iloc[-test_size:].reset_index(drop=True)

        # Create backtest DataFrame
        backtest_df = pd.DataFrame({
            'Date': test_dates,
            'Close': df['Close'].iloc[-test_size:].values,
            'Actual': y_test.values,
            'Predicted': y_pred
        })

        # Calculate daily returns
        backtest_df['Daily_Return'] = backtest_df['Close'].pct_change()

        # Calculate strategy returns
        backtest_df['Strategy_Return'] = backtest_df['Predicted'] * backtest_df['Daily_Return']

        # Calculate cumulative returns
        backtest_df['Cumulative_Market_Return'] = (1 + backtest_df['Daily_Return']).cumprod() - 1
        backtest_df['Cumulative_Strategy_Return'] = (1 + backtest_df['Strategy_Return']).cumprod() - 1

        # Calculate Sharpe ratio
        risk_free_rate = 0.03 / 252  # Assume annual risk-free rate of 3%
        market_sharpe = (backtest_df['Daily_Return'].mean() - risk_free_rate) / backtest_df[
            'Daily_Return'].std() * np.sqrt(252)
        strategy_sharpe = (backtest_df['Strategy_Return'].mean() - risk_free_rate) / backtest_df[
            'Strategy_Return'].std() * np.sqrt(252)

        # Calculate maximum drawdown
        backtest_df['Market_Cummax'] = backtest_df['Cumulative_Market_Return'].cummax()
        backtest_df['Strategy_Cummax'] = backtest_df['Cumulative_Strategy_Return'].cummax()
        backtest_df['Market_Drawdown'] = backtest_df['Cumulative_Market_Return'] - backtest_df['Market_Cummax']
        backtest_df['Strategy_Drawdown'] = backtest_df['Cumulative_Strategy_Return'] - backtest_df['Strategy_Cummax']
        max_market_drawdown = backtest_df['Market_Drawdown'].min()
        max_strategy_drawdown = backtest_df['Strategy_Drawdown'].min()

        # Print backtest results
        print("\nStrategy Backtest Results:")
        print(f"Market Total Return: {backtest_df['Cumulative_Market_Return'].iloc[-1]:.2%}")
        print(f"Strategy Total Return: {backtest_df['Cumulative_Strategy_Return'].iloc[-1]:.2%}")
        print(f"Market Sharpe Ratio: {market_sharpe:.2f}")
        print(f"Strategy Sharpe Ratio: {strategy_sharpe:.2f}")
        print(f"Market Max Drawdown: {max_market_drawdown:.2%}")
        print(f"Strategy Max Drawdown: {max_strategy_drawdown:.2%}")

        # Plot cumulative returns
        self.plot_cumulative_returns(backtest_df)

        return backtest_df

    def plot_cumulative_returns(self, backtest_df):
        """Plot cumulative returns"""
        plt.figure(figsize=(12, 6))
        plt.plot(backtest_df['Date'], backtest_df['Cumulative_Market_Return'], label='Market Return')
        plt.plot(backtest_df['Date'], backtest_df['Cumulative_Strategy_Return'], label='Strategy Return')
        plt.title('Market vs Strategy Cumulative Returns')
        plt.xlabel('Date')
        plt.ylabel('Cumulative Return')
        plt.legend()
        plt.grid(True)
        plt.show()  # Display the plot
        plt.close()

    def run_full_pipeline(self):
        """Run full prediction pipeline"""
        try:
            # 1. Fetch data
            df = self.fetch_data()

            # 2. Data preprocessing
            processed_df = self.preprocess_data(df)

            # 3. Feature selection
            X, y = self.feature_selection(processed_df)

            # 4. Model training and evaluation
            X_test, y_test, y_pred, y_pred_proba = self.train_model(X, y)

            # 5. Strategy backtest
            backtest_results = self.backtest_strategy(processed_df, X_test, y_test, y_pred)

            # 6. Feature importance analysis
            self.plot_feature_importance()

            return {
                'data': processed_df,
                'X': X,
                'y': y,
                'model': self.model,
                'backtest': backtest_results
            }

        except Exception as e:
            print(f"Pipeline execution failed: {e}")
            return None

    def plot_feature_importance(self):
        """Plot feature importance"""
        if self.model is not None and self.selected_features is not None:
            feature_importance = pd.Series(
                self.model.feature_importances_,
                index=self.selected_features
            ).sort_values(ascending=True)

            plt.figure(figsize=(10, 6))
            feature_importance.plot(kind='barh')
            plt.title('Feature Importance')
            plt.xlabel('Importance Score')
            plt.tight_layout()
            plt.show()  # Display the plot
            plt.close()


if __name__ == "__main__":
    # Ensure required packages are installed
    # required_packages = ['pandas', 'numpy', 'matplotlib', 'scikit-learn', 'imblearn', 'lightgbm', 'akshare']
    # try:
    #     import importlib
    #
    #     for pkg in required_packages:
    #         importlib.import_module(pkg)
    # except ImportError as e:
    #     print(f"Missing required package: {e.name}")
    #     print(f"Please install using: pip install {e.name}")
    #     exit(1)

    predictor = CSIMarketPredictor()
    results = predictor.run_full_pipeline()

    if results:
        print("\nPrediction pipeline completed successfully!")
        print("Results displayed in respective charts.")
    else:
        print("\nPrediction pipeline failed. Please check error messages.")