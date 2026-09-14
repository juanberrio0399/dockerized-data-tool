"""Tiny data tool: reads a CSV and prints a quick summary.
Runs the same everywhere thanks to Docker."""
import sys
import time
import logging
import pandas as pd
from pythonjsonlogger import jsonlogger

# Configure structured JSON logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logHandler = logging.StreamHandler(sys.stdout)
formatter = jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(rows_processed)s %(execution_time)s %(message)s')
logHandler.setFormatter(formatter)
logger.handlers = [logHandler]

def main(path: str) -> None:
    start_time = time.time()
    df = pd.read_csv(path)
    execution_time = round(time.time() - start_time, 4)
    rows_processed = len(df)
    
    logger.info(
        "CSV processed successfully",
        extra={
            "rows_processed": rows_processed,
            "execution_time": execution_time
        }
    )
    print(f"File: {path}")
    print(f"Rows: {rows_processed:,}  |  Columns: {len(df.columns)}")
    print("Columns:", ", ".join(df.columns))
    print("\nNumeric summary:")
    print(df.describe(include="number"))

if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else "sample.csv"
    main(csv_path)
