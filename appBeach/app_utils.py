# app_utils.py
import streamlit as st
import pandas as pd

def format_currency(value: float) -> str:
    """
    Formats a float to Brazilian currency (R$ x.xx).
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Displays a download button to download a DataFrame as CSV.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(
        label=label,
        data=csv_data,
        file_name=filename,
        mime="text/csv",
    )
