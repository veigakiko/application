import streamlit as st
import pandas as pd
from datetime import datetime

from db_utils import run_query, run_insert
from app_utils import download_df_as_csv

def orders_page():
    st.title("Orders")
    st.subheader("Register a new order")

    # Text input to filter by client name in the table below
    search_client = st.text_input("Filter by Client Name:")

    # Retrieve product data from session state (already loaded/cached in application.py)
    product_data = st.session_state.data.get("products", [])
    # In the DB, we expect each row to be something like: (supplier, product, quantity, unit_value, total_value, creation_date)
    # product_data[row][1] is the "product" name
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products available"]

    # Form to create a new order
    with st.form(key='order_form'):
        # For example, get a list of registered clients from the DB
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo;')
        customer_list = [""] + [row[0] for row in clientes]

        col1, col2, col3 = st.columns(3)
        with col1:
            customer_name = st.selectbox("Customer Name", customer_list, index=0)
        with col2:
            product = st.selectbox("Product", product_list, index=0)
        with col3:
            quantity = st.number_input("Quantity", min_value=1, step=1)

        submit_button = st.form_submit_button(label="Register Order")

    if submit_button:
        if customer_name and product and quantity > 0:
            query = """
                INSERT INTO public.tb_pedido ("Cliente", "Produto", "Quantidade", "Data", status)
                VALUES (%s, %s, %s, %s, 'em aberto');
            """
            timestamp = datetime.now()
            success = run_insert(query, (customer_name, product, quantity, timestamp))
            if success:
                st.success("Order registered successfully!")
                # Force a data refresh in session state
                st.session_state.data = st.session_state.load_all_data()
            else:
                st.error("Failed to register the order.")
        else:
            st.warning("Please fill in all fields correctly.")

    # Display all orders
    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("All Orders")
        columns = ["Client", "Product", "Quantity", "Date", "Status"]
        df_orders = pd.DataFrame(orders_data, columns=columns)

        if search_client:
            df_orders = df_orders[df_orders["Client"].str.contains(search_client, case=False)]

        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Download Orders CSV")

        # Admin users can edit/delete orders
        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Order")
            # Create a unique key so we can identify an order
            df_orders["unique_key"] = df_orders.apply(
                lambda row: f"{row['Client']}|{row['Product']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_orders["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select an order to edit/delete:", [""] + unique_keys)

            if selected_key:
                matching_rows = df_orders[df_orders["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple orders found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_client = selected_row["Client"]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_date = selected_row["Date"]
                    original_status = selected_row["Status"]

                    with st.form(key='edit_order_form'):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            edit_product = st.selectbox(
                                "Product",
                                product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input(
                                "Quantity",
                                min_value=1,
                                step=1,
                                value=int(original_quantity)
                            )
                        with col3:
                            edit_status_list = [
                                "em aberto",
                                "Received - Debited",
                                "Received - Credit",
                                "Received - Pix",
                                "Received - Cash"
                            ]
                            if original_status in edit_status_list:
                                edit_status_index = edit_status_list.index(original_status)
                            else:
                                edit_status_index = 0
                            edit_status = st.selectbox("Status", edit_status_list, index=edit_status_index)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Update Order")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Order")

                    if delete_button:
                        delete_query = """
                            DELETE FROM public.tb_pedido
                            WHERE "Cliente" = %s AND "Produto" = %s AND "Data" = %s;
                        """
                        success = run_insert(delete_query, (original_client, original_product, original_date))
                        if success:
                            st.success("Order deleted successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to delete the order.")

                    if update_button:
                        update_query = """
                            UPDATE public.tb_pedido
                            SET "Produto" = %s, "Quantidade" = %s, status = %s
                            WHERE "Cliente" = %s AND "Produto" = %s AND "Data" = %s;
                        """
                        success = run_insert(update_query, (
                            edit_product, edit_quantity, edit_status,
                            original_client, original_product, original_date
                        ))
                        if success:
                            st.success("Order updated successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to update the order.")
    else:
        st.info("No orders found.")
