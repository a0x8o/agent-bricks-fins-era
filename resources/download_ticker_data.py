# Databricks notebook source
# MAGIC %pip install yfinance pyyaml

# COMMAND ----------

import yfinance as yf
import pandas as pd
import sys
import logging

# Add parent directory to path for config import
sys.path.append('..')
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

print(f"Using Unity Catalog configuration:")
print(f"  Catalog: {config.catalog}")
print(f"  Schema: {config.schema}")
print(f"  Target table: {config.catalog}.{config.schema}.ticker_data")

# The original Mag7 set, kept because the committed corpus in data/10k and
# data/10Q is still theirs and the Genie demo questions reference them.
MAG7 = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"]

# Everything else comes from conf/companies.yaml, so adding a company in one
# place prices it here, files it in the corpus, and puts it in the graph.
#
# Note this is deliberately NOT the same list as the companies: American Honda
# Finance files a 10-K but has no listed equity, so it is in the corpus and the
# graph with no row here, while Henkel and Munich Re have ADR tickers but no SEC
# filing. Company coverage and price coverage genuinely differ.
# (sys.path already has '..' from the config import above.)
from era.ingest.companies import load_companies, tickers as manifest_tickers  # noqa: E402

_COMPANIES = load_companies()
_NAME_BY_TICKER = {c.ticker: c.name for c in _COMPANIES if c.ticker}
TICKERS = MAG7 + [t for t in manifest_tickers(_COMPANIES) if t not in MAG7]

def get_ticker_data(period="1y"):
    """Download daily prices and valuation metrics for the covered universe."""
    all_data = []

    logger.info(f"Downloading ticker data for {len(TICKERS)} companies (period: {period})...")

    for symbol in TICKERS:
        try:
            logger.info(f"Downloading data for {symbol}...")
            t = yf.Ticker(symbol)

            # --- Daily price history ---
            hist = t.history(period=period, interval="1d", auto_adjust=False).reset_index()

            if hist.empty:
                logger.warning(f"No data found for {symbol}")
                continue

            # --- Fundamental / valuation data ---
            info = t.info or {}

            # Add symbol and valuation metrics to each daily row
            hist["symbol"] = symbol
            # Real name where the manifest knows one. This column is what 05b uses
            # to name graph nodes, so leaving it as the ticker symbol - which it
            # used to be - produced a graph whose nodes were called "AAPL".
            hist["company_name"] = _NAME_BY_TICKER.get(
                symbol, (info.get("longName") or symbol)
            )
            hist["price_open"] = hist["Open"]
            hist["price_close"] = hist["Close"]
            hist["volume"] = hist["Volume"]

            hist["pe_trailing"] = info.get("trailingPE")
            hist["pe_forward"] = info.get("forwardPE")
            hist["peg"] = info.get("pegRatio")
            hist["ev_ebitda"] = info.get("enterpriseToEbitda")
            hist["market_cap"] = info.get("marketCap")
            hist["beta"] = info.get("beta")

            # Keep only the requested columns (fix date column reference)
            hist = hist[[
                "Date",
                "symbol",
                "company_name",
                "price_open",
                "price_close",
                "volume",
                "pe_trailing",
                "pe_forward",
                "peg",
                "ev_ebitda",
                "market_cap",
                "beta"
            ]]

            # Rename Date column to date
            hist = hist.rename(columns={"Date": "date"})

            all_data.append(hist)
            logger.info(f"Downloaded {len(hist)} records for {symbol}")

        except Exception as e:
            logger.error(f"Error downloading data for {symbol}: {e}")
            continue

    if not all_data:
        raise Exception("No ticker data was successfully downloaded")

    combined_df = pd.concat(all_data, ignore_index=True)
    logger.info(f"Combined dataset: {len(combined_df)} total records")

    return combined_df


# Run it
df = get_ticker_data(period="1y")

# Preview
print("📊 Preview of downloaded data:")
print(df.head())
print(f"\nDataset shape: {df.shape}")

# COMMAND ----------

# Skip CSV save step - upload directly to Unity Catalog using config settings
full_table = f"{config.catalog}.{config.schema}.ticker_data"

print(f"Uploading to Unity Catalog table: {full_table}")

spark_df = spark.createDataFrame(df)
spark_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table)

# Verify upload
count = spark.sql(f"SELECT COUNT(*) as count FROM {full_table}").collect()[0]['count']
print(f"✅ Successfully uploaded {count:,} records to {full_table}")

# Show sample
print("\nSample data from uploaded table:")
spark.sql(f"SELECT * FROM {full_table} LIMIT 5").show()