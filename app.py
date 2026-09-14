import polars as pl
import duckdb

def main():
    print("Initializing application with Polars, uv, and DuckDB...")
    
    # Example processing with Polars
    try:
        df = pl.read_csv("sample.csv")
        print("Data loaded successfully with Polars:")
        print(df)
        
        # Example query with DuckDB
        result = duckdb.sql("SELECT * FROM df WHERE 1=1").pl()
        print("DuckDB query result:")
        print(result)
    except Exception as e:
        print(f"Running without sample.csv: {e}")

if __name__ == "__main__":
    main()
