import streamlit as st
import pandas as pd
from datetime import date

from db_utils import run_query, run_insert
from app_utils import download_df_as_csv, format_currency

def products_page():
    st.title("Products")

    # Form to add a new product
    st.subheader("Add a new product")
    with st.form(key='product_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            supplier = st.text_input("Supplier", max_chars=100)
        with col2:
            product = st.text_input("Product", max_chars=100)
        with col3:
            quantity = st.number_input("Quantity", min_value=1, step=1)
        with col4:
            unit_value = st.number_input("Unit Value", min_value=0.0, step=0.01, format="%.2f")

        creation_date = st.date_input("Creation Date", value=date.today())
        submit_product = st.form_submit_button(label="Insert Product")

    if submit_product:
        if supplier and product and quantity > 0 and unit_value >= 0:
            total_value = quantity * unit_value
            query = """
                INSERT INTO public.tb_products (supplier, product, quantity, unit_value, total_value, creation_date)
                VALUES (%s, %s, %s, %s, %s, %s);
            """
            success = run_insert(query, (supplier, product, quantity, unit_value, total_value, creation_date))
            if success:
                st.success("Product added successfully!")
                st.session_state.data = st.session_state.load_all_data()
            else:
                st.error("Failed to add the product.")
        else:
            st.warning("Please fill in all fields correctly.")

    # Display all products
    products_data = st.session_state.data.get("products", [])
    if products_data:
        st.subheader("All Products")
        columns = ["Supplier", "Product", "Quantity", "Unit Value", "Total Value", "Creation Date"]
        df_products = pd.DataFrame(products_data, columns=columns)
        st.dataframe(df_products, use_container_width=True)

        download_df_as_csv(df_products, "products.csv", label="Download Products CSV")

        # Admin can edit or delete products
        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Product")
            df_products["unique_key"] = df_products.apply(
                lambda row: f"{row['Supplier']}|{row['Product']}|{row['Creation Date'].strftime('%Y-%m-%d')}",
                axis=1
            )
            unique_keys = df_products["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select a product to edit/delete:", [""] + unique_keys)

            if selected_key:
                matching_rows = df_products[df_products["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple products found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_supplier = selected_row["Supplier"]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_unit_value = selected_row["Unit Value"]
                    original_creation_date = selected_row["Creation Date"]

                    with st.form(key='edit_product_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_supplier = st.text_input("Supplier", value=original_supplier, max_chars=100)
                        with col2:
                            edit_product = st.text_input("Product", value=original_product, max_chars=100)
                        with col3:
                            edit_quantity = st.number_input(
                                "Quantity",
                                min_value=1,
                                step=1,
                                value=int(original_quantity)
                            )
                        with col4:
                            edit_unit_value = st.number_input(
                                "Unit Value",
                                min_value=0.0,
                                step=0.01,
                                format="%.2f",
                                value=float(original_unit_value)
                            )

                        edit_creation_date = st.date_input("Creation Date", value=original_creation_date)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Update Product")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Product")

                    if update_button:
                        edit_total_value = edit_quantity * edit_unit_value
                        update_query = """
                            UPDATE public.tb_products
                            SET supplier = %s,
                                product = %s,
                                quantity = %s,
                                unit_value = %s,
                                total_value = %s,
                                creation_date = %s
                            WHERE supplier = %s AND product = %s AND creation_date = %s;
                        """
                        success = run_insert(update_query, (
                            edit_supplier, edit_product, edit_quantity, edit_unit_value,
                            edit_total_value, edit_creation_date,
                            original_supplier, original_product, original_creation_date
                        ))
                        if success:
                            st.success("Product updated successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to update the product.")

                    if delete_button:
                        confirm = st.checkbox("Are you sure you want to delete this product?")
                        if confirm:
                            delete_query = """
                                DELETE FROM public.tb_products
                                WHERE supplier = %s AND product = %s AND creation_date = %s;
                            """
                            success = run_insert(delete_query, (
                                original_supplier, original_product, original_creation_date
                            ))
                            if success:
                                st.success("Product deleted successfully!")
                                st.session_state.data = st.session_state.load_all_data()
                            else:
                                st.error("Failed to delete the product.")
    else:
        st.info("No products found.")
