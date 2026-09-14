"""Tiny data tool: reads a CSV and provides an interactive Streamlit dashboard.
Runs the same everywhere thanks to Docker."""
import os
import pandas as pd
import streamlit as st

def main() -> None:
    st.title("Interactive Data App")
    st.write("Upload a CSV file or use the default dataset.")

    uploaded_file = st.file_uploader("Choose a CSV file", type="csv")
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
    elif os.path.exists("sample.csv"):
        df = pd.read_csv("sample.csv")
    else:
        st.warning("No dataset found. Please upload a CSV file.")
        return

    st.subheader("Dataset Preview")
    st.dataframe(df)

    st.subheader("Dataset Summary")
    st.write(f"Rows: {len(df):,}  |  Columns: {len(df.columns)}")
    
    if not df.select_dtypes(include="number").empty:
        st.subheader("Statistical Summary")
        st.table(df.describe(include="number"))

        st.subheader("Numeric Data Visualization")
        st.bar_chart(df.select_dtypes(include="number"))

if __name__ == "__main羽根__":
    main()
