import streamlit as st
import pandas as pd
from datetime import datetime

from db_utils import run_query, run_insert
from app_utils import download_df_as_csv

def stock_page():
    st.title("Stock")
    st.subheader("Add a new stock record")
    st.write("""
        This page is designed to record **only product entries** into the stock in a practical and organized way.
        With this system, you can monitor all additions to the stock with greater control and traceability.
    """)

    # Retrieve product names from DB
    product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
    product_list = [row[0] for row in product_data] if product_data else ["No products available"]

    # Form to add a new stock entry
    with st.form(key='stock_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            product = st.selectbox("Product", product_list)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, step=1)
        with col3:
            transaction = st.selectbox("Transaction Type", ["Entrada"])  # Only input for now
        with col4:
            date_input = st.date_input("Date", value=datetime.now().date())

        submit_stock = st.form_submit_button(label="Register")

    if submit_stock:
        if product and quantity > 0:
            current_datetime = datetime.combine(date_input, datetime.min.time())
            query = """
                INSERT INTO public.tb_estoque ("Produto", "Quantidade", "Transação", "Data")
                VALUES (%s, %s, %s, %s);
            """
            success = run_insert(query, (product, quantity, transaction, current_datetime))
            if success:
                st.success("Stock record added successfully!")
                st.session_state.data = st.session_state.load_all_data()
            else:
                st.error("Failed to add stock record.")
        else:
            st.warning("Please select a product and enter a quantity greater than 0.")

    # Display all stock records
    stock_data = st.session_state.data.get("stock", [])
    if stock_data:
        st.subheader("All Stock Records")
        columns = ["Product", "Quantity", "Transaction", "Date"]
        df_stock = pd.DataFrame(stock_data, columns=columns)
        st.dataframe(df_stock, use_container_width=True)

        download_df_as_csv(df_stock, "stock.csv", label="Download Stock CSV")

        # Admin can edit or delete stock records
        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Stock Record")
            df_stock["unique_key"] = df_stock.apply(
                lambda row: f"{row['Product']}|{row['Transaction']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_stock["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select a stock record to edit/delete:", [""] + unique_keys)

            if selected_key:
                matching_rows = df_stock[df_stock["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple stock records found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_transaction = selected_row["Transaction"]
                    original_date = selected_row["Date"]

                    with st.form(key='edit_stock_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_product = st.selectbox(
                                "Product",
                                product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input("Quantity", min_value=1, step=1, value=int(original_quantity))
                        with col3:
                            # Let's allow "Saída" (outflow) also
                            edit_transaction = st.selectbox(
                                "Transaction Type",
                                ["Entrada", "Saída"],
                                index=["Entrada", "Saída"].index(original_transaction)
                                if original_transaction in ["Entrada", "Saída"] else 0
                            )
                        with col4:
                            edit_date = st.date_input("Date", value=original_date.date())

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Update Stock Record")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Stock Record")

                    if update_button:
                        edit_datetime = datetime.combine(edit_date, datetime.min.time())
                        update_query = """
                            UPDATE public.tb_estoque
                            SET "Produto" = %s, "Quantidade" = %s, "Transação" = %s, "Data" = %s
                            WHERE "Produto" = %s AND "Transação" = %s AND "Data" = %s;
                        """
                        success = run_insert(update_query, (
                            edit_product,
                            edit_quantity,
                            edit_transaction,
                            edit_datetime,
                            original_product,
                            original_transaction,
                            original_date
                        ))
                        if success:
                            st.success("Stock record updated successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to update the stock record.")

                    if delete_button:
                        confirm = st.checkbox("Are you sure you want to delete this stock record?")
                        if confirm:
                            delete_query = """
                                DELETE FROM public.tb_estoque
                                WHERE "Produto" = %s AND "Transação" = %s AND "Data" = %s;
                            """
                            success = run_insert(delete_query, (
                                original_product,
                                original_transaction,
                                original_date
                            ))
                            if success:
                                st.success("Stock record deleted successfully!")
                                st.session_state.data = st.session_state.load_all_data()
                            else:
                                st.error("Failed to delete the stock record.")
    else:
        st.info("No stock records found.")
