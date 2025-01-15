import streamlit as st
from streamlit_option_menu import option_menu
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime, date, timedelta
import pandas as pd
from PIL import Image
import requests
from io import BytesIO
from fpdf import FPDF
import os
import uuid
import calendar
import altair as alt
import numpy as np
from sklearn.linear_model import LinearRegression
import mitosheet  # Importing MitoSheet
from mitosheet.streamlit.v1 import spreadsheet
from mitosheet.streamlit.v1.spreadsheet import _get_mito_backend

# Configure the page layout to wide
st.set_page_config(layout="wide")

#############################################################################
#                                   UTILITIES
###############################################################################
def format_currency(value: float) -> str:
    """Formats a float value to US currency format."""
    return f"${value:,.2f}"

def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Download CSV"):
    """Allows downloading a DataFrame as CSV."""
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")

def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Download Excel"):
    """Allows downloading a DataFrame as Excel."""
    import io
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    towrite.seek(0)
    st.download_button(
        label=label,
        data=towrite,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Download JSON"):
    """Allows downloading a DataFrame as JSON."""
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")

def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Download HTML"):
    """Allows downloading a DataFrame as HTML."""
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")

def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Download Parquet"):
    """Allows downloading a DataFrame as Parquet."""
    import io
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    st.download_button(label=label, data=buffer.getvalue(), file_name=filename, mime="application/octet-stream")

###############################################################################
#                      FUNCTIONS FOR PDF AND UPLOAD (OPTIONAL)
###############################################################################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """Converts a DataFrame to PDF using FPDF."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Headers
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()

    # Rows
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()

    return pdf.output(dest='S')

def upload_pdf_to_fileio(pdf_bytes: bytes) -> str:
    """Uploads a PDF to file.io and returns the link."""
    try:
        response = requests.post(
            'https://file.io/',
            files={'file': ('stock_vs_orders_summary.pdf', pdf_bytes, 'application/pdf')}
        )
        if response.status_code == 200:
            json_resp = response.json()
            if json_resp.get('success'):
                return json_resp.get('link', "")
            else:
                return ""
        else:
            return ""
    except:
        return ""

###############################################################################
#                               TWILIO (WHATSAPP)
###############################################################################
def send_whatsapp(recipient_number: str, media_url: str = None):
    """
    Sends WhatsApp messages via Twilio (credentials in st.secrets["twilio"]).
    Example 'recipient_number': '5511999999999' (without '+').
    """
    from twilio.rest import Client
    try:
        account_sid = st.secrets["twilio"]["account_sid"]
        auth_token = st.secrets["twilio"]["auth_token"]
        whatsapp_from = st.secrets["twilio"]["whatsapp_from"]

        client = Client(account_sid, auth_token)
        if media_url:
            message = client.messages.create(
                body="Here is the requested PDF!",
                from_=whatsapp_from,
                to=f"whatsapp:+{recipient_number}",
                media_url=[media_url]
            )
        else:
            message = client.messages.create(
                body="Hello! Test message via Twilio WhatsApp.",
                from_=whatsapp_from,
                to=f"whatsapp:+{recipient_number}"
            )
    except:
        pass

###############################################################################
#                            DATABASE CONNECTION
###############################################################################
def get_db_connection():
    """Establishes connection to PostgreSQL database using Streamlit Secrets credentials."""
    try:
        conn = psycopg2.connect(
            host=st.secrets["db"]["host"],
            database=st.secrets["db"]["name"],
            user=st.secrets["db"]["user"],
            password=st.secrets["db"]["password"],
            port=st.secrets["db"]["port"]
        )
        return conn
    except:
        return None

def run_query(query: str, values=None, commit: bool = False):
    """
    Executes a query on the database.
    - query: SQL query string.
    - values: Values for query parameterization.
    - commit: If True, commits after execution.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values or ())
            if commit:
                conn.commit()
                return True
            else:
                return cursor.fetchall()
    except:
        pass
    finally:
        if not conn.closed:
            conn.close()
    return None

###############################################################################
#                         DATA LOADING (CACHE)
###############################################################################
@st.cache_data(show_spinner=False)  # Do not show spinner
def load_all_data():
    """Loads all necessary data from the database and stores it in session_state."""
    data = {}
    try:
        data["orders"] = run_query(
            'SELECT "Cliente","Produto","Quantidade","Data",status FROM public.tb_pedido ORDER BY "Data" DESC'
        ) or []
        data["products"] = run_query(
            'SELECT supplier,product,quantity,unit_value,total_value,creation_date FROM public.tb_products ORDER BY creation_date DESC'
        ) or []
        data["clients"] = run_query(
            'SELECT DISTINCT "Cliente" FROM public.tb_pedido ORDER BY "Cliente"'
        ) or []
        data["stock"] = run_query(
            'SELECT "Produto","Quantidade","Transação","Data" FROM public.tb_estoque ORDER BY "Data" DESC'
        ) or []
        data["revenue"] = run_query(
            """
            SELECT date("Data") as dt, SUM("total") as total_day
            FROM public.vw_pedido_produto
            WHERE status IN ('Received - Debited','Received - Credit','Received - Pix','Received - Cash')
            GROUP BY date("Data")
            ORDER BY date("Data")
            """
        ) or pd.DataFrame()
    except:
        pass
    return data

def refresh_data():
    """Updates the data stored in session_state."""
    load_all_data.clear()
    st.session_state.data = load_all_data()

###############################################################################
#                           APPLICATION PAGES
###############################################################################
def home_page():
    """Home page of the application."""
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Worker Avenue, 1879 — 🏆 5th Open BBC")

    notification_placeholder = st.empty()
    client_count_query = """
        SELECT COUNT(DISTINCT "Cliente") 
        FROM public.tb_pedido
        WHERE status=%s
    """
    client_count = run_query(client_count_query, ('open',))
    if client_count and client_count[0][0] > 0:
        notification_placeholder.success(f"There are {client_count[0][0]} clients with open orders!")
    else:
        notification_placeholder.info("No clients with open orders at the moment.")

    if st.session_state.get("username") == "admin":
        # Expander to group administrative reports
        with st.expander("Open Orders Summary"):
            open_orders_query = """
                SELECT "Cliente",SUM("total") AS Total
                FROM public.vw_pedido_produto
                WHERE status=%s
                GROUP BY "Cliente"
                ORDER BY "Cliente" DESC
            """
            open_orders_data = run_query(open_orders_query, ('open',))
            if open_orders_data:
                df_open = pd.DataFrame(open_orders_data, columns=["Client","Total"])
                total_open = df_open["Total"].sum()
                df_open["Total_display"] = df_open["Total"].apply(format_currency)
                st.table(df_open[["Client","Total_display"]])
                st.markdown(f"**Total (Open Orders):** {format_currency(total_open)}")
            else:
                st.info("No open orders found.")

        with st.expander("Stock vs. Orders Summary"):
            try:
                stock_vs_orders_query = """
                    SELECT product,stock_quantity,orders_quantity,total_in_stock
                    FROM public.vw_stock_vs_orders_summary
                """
                stock_vs_orders_data = run_query(stock_vs_orders_query)
                if stock_vs_orders_data:
                    df_svo = pd.DataFrame(
                        stock_vs_orders_data,
                        columns=["Product","Stock_Quantity","Orders_Quantity","Total_in_Stock"]
                    )
                    df_svo.sort_values("Total_in_Stock", ascending=False, inplace=True)
                    df_display = df_svo[["Product","Total_in_Stock"]]
                    st.table(df_display)
                    total_val = int(df_svo["Total_in_Stock"].sum())
                    st.markdown(f"**Total (Stock vs. Orders):** {total_val}")

                    pdf_bytes = convert_df_to_pdf(df_svo)
                    st.subheader("Download 'Stock vs Orders' PDF")
                    st.download_button(
                        label="Download PDF",
                        data=pdf_bytes,
                        file_name="stock_vs_orders_summary.pdf",
                        mime="application/pdf"
                    )

                    st.subheader("Send this PDF via WhatsApp")
                    phone_number = st.text_input("Number (e.g., 5511999999999)")
                    if st.button("Upload and Send"):
                        link = upload_pdf_to_fileio(pdf_bytes)
                        if link and phone_number:
                            send_whatsapp(phone_number, media_url=link)
                            st.success("PDF successfully sent via WhatsApp!")
                        else:
                            st.warning("Please provide the number and ensure the upload was successful.")
                else:
                    st.info("View 'vw_stock_vs_orders_summary' has no data or does not exist.")
            except:
                st.info("Error generating Stock vs. Orders summary.")

        # NEW ITEM: Total Revenue
        with st.expander("Total Revenue"):
            revenue_query = """
                SELECT date("Data") as dt, SUM("total") as total_day
                FROM public.vw_pedido_produto
                WHERE status IN ('Received - Debited','Received - Credit','Received - Pix','Received - Cash')
                GROUP BY date("Data")
                ORDER BY date("Data")
            """
            revenue_data = run_query(revenue_query)
            if revenue_data:
                df_rev = pd.DataFrame(revenue_data, columns=["Date","Day Total"])
                df_rev["Day Total"] = df_rev["Day Total"].apply(format_currency)
                st.table(df_rev)
            else:
                st.info("No revenue data found.")

def orders_page():
    """Page to manage orders."""
    st.title("Manage Orders")
    # Create tabs to separate "New Order" and "Order Listing"
    tabs = st.tabs(["New Order", "Order Listing"])

    # ======================= TAB: New Order =======================
    with tabs[0]:
        st.subheader("New Order")
        product_data = st.session_state.data.get("products", [])
        product_list = [""] + [row[1] for row in product_data] if product_data else ["No products"]

        with st.form(key='order_form'):
            # Retrieving clients from tb_clients table
            clients = run_query('SELECT full_name FROM public.tb_clients ORDER BY full_name')
            customer_list = [""] + [row[0] for row in clients] if clients else []

            col1, col2, col3 = st.columns(3)
            with col1:
                customer_name = st.selectbox("Client", customer_list)
            with col2:
                product = st.selectbox("Product", product_list)
            with col3:
                quantity = st.number_input("Quantity", min_value=1, step=1)

            submit_button = st.form_submit_button("Register Order")

        if submit_button:
            if customer_name and product and quantity > 0:
                query_insert = """
                    INSERT INTO public.tb_pedido("Cliente","Produto","Quantidade","Data",status)
                    VALUES (%s,%s,%s,%s,'open')
                """
                run_query(query_insert, (customer_name, product, quantity, datetime.now()), commit=True)
                st.success("Order successfully registered!")
                refresh_data()
            else:
                st.warning("Please fill in all fields.")

    # ======================= TAB: Order Listing =======================
    with tabs[1]:
        st.subheader("Order Listing")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            cols = ["Client","Product","Quantity","Date","Status"]
            df_orders = pd.DataFrame(orders_data, columns=cols)
            st.dataframe(df_orders, use_container_width=True)
            download_df_as_csv(df_orders, "orders.csv", label="Download Orders CSV")

            # Only show edit form if admin
            if st.session_state.get("username") == "admin":
                st.markdown("### Edit or Delete Order")
                df_orders["unique_key"] = df_orders.apply(
                    lambda row: f"{row['Client']}|{row['Product']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                    axis=1
                )
                unique_keys = df_orders["unique_key"].unique().tolist()
                selected_key = st.selectbox("Select Order", [""] + unique_keys)

                if selected_key:
                    match = df_orders[df_orders["unique_key"] == selected_key]
                    if len(match) > 1:
                        st.warning("Multiple records with the same key.")
                    else:
                        sel = match.iloc[0]
                        original_client = sel["Client"]
                        original_product = sel["Product"]
                        original_qty = sel["Quantity"]
                        original_date = sel["Date"]
                        original_status = sel["Status"]

                        with st.form(key='edit_order_form'):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                if original_product in product_list:
                                    prod_index = product_list.index(original_product)
                                else:
                                    prod_index = 0
                                edit_prod = st.selectbox("Product", product_list, index=prod_index)
                            with col2:
                                edit_qty = st.number_input("Quantity", min_value=1, step=1, value=int(original_qty))
                            with col3:
                                status_opts = [
                                    "open", "Received - Debited", "Received - Credit",
                                    "Received - Pix", "Received - Cash"
                                ]
                                if original_status in status_opts:
                                    s_index = status_opts.index(original_status)
                                else:
                                    s_index = 0
                                edit_status = st.selectbox("Status", status_opts, index=s_index)

                            col_upd, col_del = st.columns(2)
                            with col_upd:
                                update_btn = st.form_submit_button("Update Order")
                            with col_del:
                                delete_btn = st.form_submit_button("Delete Order")

                        if delete_btn:
                            q_del = """
                                DELETE FROM public.tb_pedido
                                WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                            """
                            run_query(q_del, (original_client, original_product, original_date), commit=True)
                            st.success("Order deleted!")
                            refresh_data()

                        if update_btn:
                            q_upd = """
                                UPDATE public.tb_pedido
                                SET "Produto"=%s,"Quantidade"=%s,status=%s
                                WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                            """
                            run_query(q_upd, (
                                edit_prod, edit_qty, edit_status,
                                original_client, original_product, original_date
                            ), commit=True)
                            st.success("Order updated!")
                            refresh_data()
        else:
            st.info("No orders found.")

def products_page():
    """Page to manage products."""
    st.title("Products")
    # Use tabs to separate "New Product" and "Product Listing"
    tabs = st.tabs(["New Product", "Product Listing"])

    # ======================= TAB: New Product =======================
    with tabs[0]:
        st.subheader("Add New Product")
        with st.form(key='product_form'):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                supplier = st.text_input("Supplier")
            with col2:
                product = st.text_input("Product")
            with col3:
                quantity = st.number_input("Quantity", min_value=1, step=1)
            with col4:
                unit_value = st.number_input("Unit Value", min_value=0.0, step=0.01, format="%.2f")
            creation_date = st.date_input("Creation Date", value=date.today())
            submit_prod = st.form_submit_button("Insert Product")

        if submit_prod:
            if supplier and product and quantity > 0 and unit_value >= 0:
                total_value = quantity * unit_value
                q_ins = """
                    INSERT INTO public.tb_products
                    (supplier,product,quantity,unit_value,total_value,creation_date)
                    VALUES (%s,%s,%s,%s,%s,%s)
                """
                run_query(q_ins, (supplier, product, quantity, unit_value, total_value, creation_date), commit=True)
                st.success("Product successfully added!")
                refresh_data()
            else:
                st.warning("Please fill in all fields.")

    # ======================= TAB: Product Listing =======================
    with tabs[1]:
        st.subheader("All Products")
        products_data = st.session_state.data.get("products", [])
        if products_data:
            cols = ["Supplier","Product","Quantity","Unit Value","Total Value","Creation Date"]
            df_prod = pd.DataFrame(products_data, columns=cols)
            st.dataframe(df_prod, use_container_width=True)
            download_df_as_csv(df_prod, "products.csv", label="Download Products CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Edit / Delete Product")
                df_prod["unique_key"] = df_prod.apply(
                    lambda row: f"{row['Supplier']}|{row['Product']}|{row['Creation Date'].strftime('%Y-%m-%d')}",
                    axis=1
                )
                unique_keys = df_prod["unique_key"].unique().tolist()
                selected_key = st.selectbox("Select Product:", [""] + unique_keys)
                if selected_key:
                    match = df_prod[df_prod["unique_key"] == selected_key]
                    if len(match) > 1:
                        st.warning("Multiple products with the same key.")
                    else:
                        sel = match.iloc[0]
                        original_supplier = sel["Supplier"]
                        original_product = sel["Product"]
                        original_quantity = sel["Quantity"]
                        original_unit_value = sel["Unit Value"]
                        original_creation_date = sel["Creation Date"]

                        with st.form(key='edit_product_form'):
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                edit_supplier = st.text_input("Supplier", value=original_supplier)
                            with col2:
                                edit_product = st.text_input("Product", value=original_product)
                            with col3:
                                edit_quantity = st.number_input(
                                    "Quantity", min_value=1, step=1, value=int(original_quantity)
                                )
                            with col4:
                                edit_unit_val = st.number_input(
                                    "Unit Value", min_value=0.0, step=0.01, format="%.2f",
                                    value=float(original_unit_value)
                                )
                            edit_creation_date = st.date_input("Creation Date", value=original_creation_date)

                            col_upd, col_del = st.columns(2)
                            with col_upd:
                                update_btn = st.form_submit_button("Update Product")
                            with col_del:
                                delete_btn = st.form_submit_button("Delete Product")

                        if update_btn:
                            edit_total_val = edit_quantity * edit_unit_val
                            q_upd = """
                                UPDATE public.tb_products
                                SET supplier=%s,product=%s,quantity=%s,unit_value=%s,
                                    total_value=%s,creation_date=%s
                                WHERE supplier=%s AND product=%s AND creation_date=%s
                            """
                            run_query(q_upd, (
                                edit_supplier, edit_product, edit_quantity, edit_unit_val, edit_total_val,
                                edit_creation_date, original_supplier, original_product, original_creation_date
                            ), commit=True)
                            st.success("Product updated!")
                            refresh_data()

                        if delete_btn:
                            confirm = st.checkbox("Confirm deletion of this product?")
                            if confirm:
                                q_del = """
                                    DELETE FROM public.tb_products
                                    WHERE supplier=%s AND product=%s AND creation_date=%s
                                """
                                run_query(q_del, (
                                    original_supplier, original_product, original_creation_date
                                ), commit=True)
                                st.success("Product deleted!")
                                refresh_data()
        else:
            st.info("No products found.")

def stock_page():
    """Page to manage stock."""
    st.title("Stock")
    tabs = st.tabs(["New Transaction", "Transactions"])

    # ======================= TAB: New Transaction =======================
    with tabs[0]:
        st.subheader("Register New Stock Movement")
        product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
        product_list = [row[0] for row in product_data] if product_data else ["No products"]

        with st.form(key='stock_form'):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                product = st.selectbox("Product", product_list)
            with col2:
                quantity = st.number_input("Quantity", min_value=1, step=1)
            with col3:
                transaction = st.selectbox("Transaction Type", ["Entry","Exit"])
            with col4:
                date_input = st.date_input("Date", value=datetime.now().date())
            submit_st = st.form_submit_button("Register")

        if submit_st:
            if product and quantity > 0:
                current_datetime = datetime.combine(date_input, datetime.min.time())
                q_ins = """
                    INSERT INTO public.tb_estoque("Produto","Quantidade","Transação","Data")
                    VALUES(%s,%s,%s,%s)
                """
                run_query(q_ins, (product, quantity, transaction, current_datetime), commit=True)
                st.success("Stock movement registered!")
                refresh_data()
            else:
                st.warning("Select product and quantity > 0.")

    # ======================= TAB: Transactions =======================
    with tabs[1]:
        st.subheader("Stock Transactions")
        stock_data = st.session_state.data.get("stock", [])
        if stock_data:
            cols = ["Product","Quantity","Transaction","Date"]
            df_stock = pd.DataFrame(stock_data, columns=cols)
            st.dataframe(df_stock, use_container_width=True)
            download_df_as_csv(df_stock, "stock.csv", label="Download Stock CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Edit/Delete Stock Record")
                df_stock["unique_key"] = df_stock.apply(
                    lambda row: f"{row['Product']}|{row['Transaction']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                    axis=1
                )
                unique_keys = df_stock["unique_key"].unique().tolist()
                selected_key = st.selectbox("Select Record", [""] + unique_keys)
                if selected_key:
                    match = df_stock[df_stock["unique_key"] == selected_key]
                    if len(match) > 1:
                        st.warning("Multiple records with the same key.")
                    else:
                        sel = match.iloc[0]
                        original_product = sel["Product"]
                        original_qty = sel["Quantity"]
                        original_trans = sel["Transaction"]
                        original_date = sel["Date"]

                        with st.form(key='edit_stock_form'):
                            col1, col2, col3, col4 = st.columns(4)
                            product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
                            product_list = [row[0] for row in product_data] if product_data else ["No products"]

                            with col1:
                                if original_product in product_list:
                                    prod_index = product_list.index(original_product)
                                else:
                                    prod_index = 0
                                edit_prod = st.selectbox("Product", product_list, index=prod_index)
                            with col2:
                                edit_qty = st.number_input("Quantity", min_value=1, step=1, value=int(original_qty))
                            with col3:
                                edit_trans = st.selectbox(
                                    "Type", ["Entry","Exit"],
                                    index=["Entry","Exit"].index(original_trans)
                                    if original_trans in ["Entry","Exit"] else 0
                                )
                            with col4:
                                edit_date = st.date_input("Date", value=original_date.date())

                            col_upd, col_del = st.columns(2)
                            with col_upd:
                                update_btn = st.form_submit_button("Update")
                            with col_del:
                                delete_btn = st.form_submit_button("Delete")

                        if update_btn:
                            new_dt = datetime.combine(edit_date, datetime.min.time())
                            q_upd = """
                                UPDATE public.tb_estoque
                                SET "Produto"=%s,"Quantidade"=%s,"Transação"=%s,"Data"=%s
                                WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                            """
                            run_query(q_upd, (
                                edit_prod, edit_qty, edit_trans, new_dt,
                                original_product, original_trans, original_date
                            ), commit=True)
                            st.success("Stock updated!")
                            refresh_data()

                        if delete_btn:
                            q_del = """
                                DELETE FROM public.tb_estoque
                                WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                            """
                            run_query(q_del, (original_product, original_trans, original_date), commit=True)
                            st.success("Record deleted!")
                            refresh_data()
        else:
            st.info("No stock transactions found.")

def clients_page():
    """Page to manage clients."""
    st.title("Clients")
    tabs = st.tabs(["New Client", "Client Listing"])

    # ======================= TAB: New Client =======================
    with tabs[0]:
        st.subheader("Register New Client")
        with st.form(key='client_form'):
            full_name = st.text_input("Full Name")
            submit_client = st.form_submit_button("Register Client")

        if submit_client:
            if full_name:
                birth_date = date(2000,1,1)
                gender = "Other"
                phone = "0000-0000"
                address = "Default Address"
                unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
                email = f"{full_name.replace(' ','_').lower()}_{unique_id}@example.com"

                q_ins = """
                    INSERT INTO public.tb_clients(
                        full_name, birth_date, gender, phone,
                        email, address, registration_date
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                """
                run_query(q_ins, (full_name, birth_date, gender, phone, email, address), commit=True)
                st.success("Client registered!")
                refresh_data()
            else:
                st.warning("Please provide the full name.")

    # ======================= TAB: Client Listing =======================
    with tabs[1]:
        st.subheader("All Clients")
        clients_data = run_query("SELECT full_name,email FROM public.tb_clients ORDER BY registration_date DESC;")
        if clients_data:
            cols = ["Full Name","Email"]
            df_clients = pd.DataFrame(clients_data, columns=cols)
            # Display only the Full Name column
            st.dataframe(df_clients[["Full Name"]], use_container_width=True)
            download_df_as_csv(df_clients[["Full Name"]], "clients.csv", label="Download Clients CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Edit/Delete Client")
                client_display = [""] + [f"{row['Full Name']} ({row['Email']})"
                                         for _, row in df_clients.iterrows()]
                selected_display = st.selectbox("Select Client:", client_display)
                if selected_display:
                    try:
                        original_name, original_email = selected_display.split(" (")
                        original_email = original_email.rstrip(")")
                    except ValueError:
                        st.error("Invalid selection.")
                        st.stop()

                    sel_row = df_clients[df_clients["Email"] == original_email].iloc[0]
                    with st.form(key='edit_client_form'):
                        edit_name = st.text_input("Full Name", value=sel_row["Full Name"])
                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_btn = st.form_submit_button("Update Client")
                        with col_del:
                            delete_btn = st.form_submit_button("Delete Client")

                    if update_btn:
                        if edit_name:
                            q_upd = """
                                UPDATE public.tb_clients
                                SET full_name=%s
                                WHERE email=%s
                            """
                            run_query(q_upd, (edit_name, original_email), commit=True)
                            st.success("Client updated!")
                            refresh_data()
                        else:
                            st.warning("Please provide the full name.")

                    if delete_btn:
                        q_del = "DELETE FROM public.tb_clients WHERE email=%s"
                        run_query(q_del, (original_email,), commit=True)
                        st.success("Client deleted!")
                        refresh_data()
                        st.experimental_rerun()
        else:
            st.info("No clients found.")

###############################################################################
#                     AUXILIARY FUNCTIONS FOR INVOICE
###############################################################################
def process_payment(client, payment_status):
    """Processes the payment by updating the order status."""
    query = """
        UPDATE public.tb_pedido
        SET status=%s,"Data"=CURRENT_TIMESTAMP
        WHERE "Cliente"=%s AND status='open'
    """
    run_query(query, (payment_status, client), commit=True)

def generate_invoice_for_printer(df: pd.DataFrame):
    """Generates a textual representation of the invoice for printing."""
    company = "Boituva Beach Club"
    address = "Worker Avenue 1879"
    city = "Boituva - SP 18552-100"
    cnpj = "05.365.434/0001-09"
    phone = "(13) 99154-5481"

    invoice = []
    invoice.append("==================================================")
    invoice.append("                      INVOICE                    ")
    invoice.append("==================================================")
    invoice.append(f"Company: {company}")
    invoice.append(f"Address: {address}")
    invoice.append(f"City: {city}")
    invoice.append(f"CNPJ: {cnpj}")
    invoice.append(f"Phone: {phone}")
    invoice.append("--------------------------------------------------")
    invoice.append("DESCRIPTION           QTY     TOTAL")
    invoice.append("--------------------------------------------------")

    # Ensure df["total"] is numeric
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    grouped_df = df.groupby('Product').agg({'Quantity':'sum','total':'sum'}).reset_index()
    total_general = 0
    for _, row in grouped_df.iterrows():
        description = f"{row['Product'][:20]:<20}"
        quantity = f"{int(row['Quantity']):>5}"
        total_item = row['total']
        total_general += total_item
        total_formatted = format_currency(total_item)
        invoice.append(f"{description} {quantity} {total_formatted}")

    invoice.append("--------------------------------------------------")
    invoice.append(f"{'TOTAL:':>30} {format_currency(total_general):>10}")
    invoice.append("==================================================")
    invoice.append("THANK YOU FOR YOUR PREFERENCE!")
    invoice.append("==================================================")

    st.text("\n".join(invoice))

###############################################################################
#                          INVOICE PAGE
###############################################################################
def invoice_page():
    """Page to generate and manage invoices."""
    st.title("Invoice")
    open_clients_query = 'SELECT DISTINCT "Cliente" FROM public.vw_pedido_produto WHERE status=%s'
    open_clients = run_query(open_clients_query, ('open',))
    client_list = [row[0] for row in open_clients] if open_clients else []
    selected_client = st.selectbox("Select a Client", [""] + client_list)

    if selected_client:
        invoice_query = """
            SELECT "Produto","Quantidade","total"
            FROM public.vw_pedido_produto
            WHERE "Cliente"=%s AND status=%s
        """
        invoice_data = run_query(invoice_query, (selected_client, 'open'))
        if invoice_data:
            df = pd.DataFrame(invoice_data, columns=["Product","Quantity","total"])

            # Convert to numeric
            df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
            total_without_discount = df["total"].sum()

            # Fixed example coupon
            valid_coupons = {
                "DISCOUNT10": 0.10,
                "DISCOUNT15": 0.15,
            }

            coupon_code = st.text_input("COUPON (optional discount)")
            applied_discount = 0.0
            if coupon_code in valid_coupons:
                applied_discount = valid_coupons[coupon_code]
                st.success(f"Coupon {coupon_code} applied! {applied_discount*100:.0f}% discount")

            # Final calculation
            total_without_discount = float(total_without_discount or 0)
            applied_discount = float(applied_discount or 0)
            total_with_discount = total_without_discount * (1 - applied_discount)

            # Generate invoice (still showing values without applying discount item by item, but displaying total_with_discount at the end)
            generate_invoice_for_printer(df)

            st.write(f"**Total without discount:** {format_currency(total_without_discount)}")
            st.write(f"**Discount:** {applied_discount*100:.0f}%")
            st.write(f"**Total with discount:** {format_currency(total_with_discount)}")

            # Payment buttons
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("Debit"):
                    process_payment(selected_client, "Received - Debited")
                    st.success("Debit payment processed!")
            with col2:
                if st.button("Credit"):
                    process_payment(selected_client, "Received - Credit")
                    st.success("Credit payment processed!")
            with col3:
                if st.button("Pix"):
                    process_payment(selected_client, "Received - Pix")
                    st.success("Pix payment processed!")
            with col4:
                if st.button("Cash"):
                    process_payment(selected_client, "Received - Cash")
                    st.success("Cash payment processed!")
        else:
            st.info("There are no open orders for this client.")
    else:
        st.warning("Please select a client.")

###############################################################################
#                            BACKUP (ADMIN)
###############################################################################
def export_table_to_csv(table_name):
    """Allows downloading a specific table as CSV."""
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name};", conn)
            csv_data = df.to_csv(index=False)
            st.download_button(
                label=f"Download {table_name} CSV",
                data=csv_data,
                file_name=f"{table_name}.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Error exporting table {table_name}: {e}")
        finally:
            conn.close()

def backup_all_tables(tables):
    """Allows downloading all specified tables as a single CSV."""
    conn = get_db_connection()
    if conn:
        try:
            frames = []
            for table in tables:
                df = pd.read_sql_query(f"SELECT * FROM {table};", conn)
                df["table_name"] = table
                frames.append(df)
            if frames:
                combined = pd.concat(frames, ignore_index=True)
                csv_data = combined.to_csv(index=False)
                st.download_button(
                    label="Download All Tables CSV",
                    data=csv_data,
                    file_name="backup_all_tables.csv",
                    mime="text/csv"
                )
        except Exception as e:
            st.error(f"Error exporting all tables: {e}")
        finally:
            conn.close()

def perform_backup():
    """Backup section for administrators."""
    st.header("Backup System")
    st.write("Click to download backups of the database tables.")

    tables = ["tb_pedido", "tb_products", "tb_clients", "tb_estoque"]

    st.subheader("Download All Tables at Once")
    if st.button("Download All Tables"):
        backup_all_tables(tables)

    st.markdown("---")

    st.subheader("Download Tables Individually")
    for table in tables:
        export_table_to_csv(table)

def admin_backup_section():
    """Displays the backup section only for administrators."""
    if st.session_state.get("username") == "admin":
        perform_backup()
    else:
        st.warning("Access restricted to administrators.")

###############################################################################
#                           EVENTS CALENDAR
###############################################################################
def events_calendar_page():
    """Page to manage the events calendar."""
    st.title("Events Calendar")

    # ----------------------------------------------------------------------------
    # 1) Helper: Read events from the database
    # ----------------------------------------------------------------------------
    def get_events_from_db():
        """
        Returns a list of tuples (id, name, description, event_date, registration_open, creation_date)
        ordered by event_date.
        """
        query = """
            SELECT id, name, description, event_date, registration_open, creation_date
            FROM public.tb_eventos
            ORDER BY event_date;
        """
        rows = run_query(query)  # Adjust according to your DB functions
        return rows if rows else []

    # ----------------------------------------------------------------------------
    # 2) Register new event
    # ----------------------------------------------------------------------------
    st.subheader("Schedule New Event")
    with st.form(key="new_event_form"):
        col1, col2 = st.columns(2)
        with col1:
            event_name = st.text_input("Event Name")
            event_date = st.date_input("Event Date", value=date.today())
        with col2:
            registration_open = st.checkbox("Registration Open?", value=True)
            event_description = st.text_area("Event Description")
        btn_register = st.form_submit_button("Schedule")

    if btn_register:
        if event_name.strip():
            q_insert = """
                INSERT INTO public.tb_eventos
                    (nome, descricao, data_evento, inscricao_aberta, data_criacao)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """
            run_query(q_insert, (event_name, event_description, event_date, registration_open), commit=True)
            st.success("Event successfully registered!")
            st.experimental_rerun()
        else:
            st.warning("Please provide at least the event name.")

    st.markdown("---")

    # ----------------------------------------------------------------------------
    # 3) Month/Year Filters
    # ----------------------------------------------------------------------------
    current_date = date.today()
    default_year = current_date.year
    default_month = current_date.month

    col_year, col_month = st.columns(2)
    with col_year:
        selected_year = st.selectbox(
            "Select Year",
            list(range(default_year - 2, default_year + 3)),  # e.g., from 2 years ago to 2 years ahead
            index=2  # by default, selects the current year
        )
    with col_month:
        month_names = [calendar.month_name[i] for i in range(1, 13)]
        selected_month = st.selectbox(
            "Select Month",
            options=list(range(1, 13)),
            format_func=lambda x: month_names[x-1],
            index=default_month - 1
        )

    # ----------------------------------------------------------------------------
    # 4) Read data and filter
    # ----------------------------------------------------------------------------
    event_rows = get_events_from_db()
    if not event_rows:
        st.info("No events registered.")
        return

    df_events = pd.DataFrame(
        event_rows,
        columns=["id", "name", "description", "event_date", "registration_open", "creation_date"]
    )
    df_events["event_date"] = pd.to_datetime(df_events["event_date"], errors="coerce")

    df_filtered = df_events[
        (df_events["event_date"].dt.year == selected_year) &
        (df_events["event_date"].dt.month == selected_month)
    ].copy()

    # ----------------------------------------------------------------------------
    # 5) Build the calendar
    # ----------------------------------------------------------------------------
    st.subheader("Calendar View")

    cal = calendar.HTMLCalendar(firstweekday=0)
    html_calendar = cal.formatmonth(selected_year, selected_month)

    # Highlight days with events
    for _, ev in df_filtered.iterrows():
        day = ev["event_date"].day
        # Adjust background color to blue and text to white
        highlight_str = (
            f' style="background-color:blue; color:white; font-weight:bold;" '
            f'title="{ev["name"]}: {ev["description"]}"'
        )
        # Replace the <td> tags corresponding to the day
        # This may overwrite multiple identical days; a more robust approach may be needed
        html_calendar = html_calendar.replace(
            f'<td class="mon">{day}</td>',
            f'<td class="mon"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="tue">{day}</td>',
            f'<td class="tue"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="wed">{day}</td>',
            f'<td class="wed"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="thu">{day}</td>',
            f'<td class="thu"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="fri">{day}</td>',
            f'<td class="fri"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="sat">{day}</td>',
            f'<td class="sat"{highlight_str}>{day}</td>'
        )
        html_calendar = html_calendar.replace(
            f'<td class="sun">{day}</td>',
            f'<td class="sun"{highlight_str}>{day}</td>'
        )

    st.markdown(html_calendar, unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    # 6) Listing events in the selected month
    # ----------------------------------------------------------------------------
    st.subheader(f"Events in {calendar.month_name[selected_month]} / {selected_year}")
    if len(df_filtered) == 0:
        st.info("No events this month.")
    else:
        df_display = df_filtered.copy()
        df_display["event_date"] = df_display["event_date"].dt.strftime("%Y-%m-%d")
        df_display.rename(columns={
            "id": "ID",
            "name": "Event Name",
            "description": "Description",
            "event_date": "Date",
            "registration_open": "Registration Open",
            "creation_date": "Creation Date"
        }, inplace=True)
        st.dataframe(df_display, use_container_width=True)

    st.markdown("---")

    # ----------------------------------------------------------------------------
    # 7) Editing and Deleting Events (without extra confirmation)
    # ----------------------------------------------------------------------------
    st.subheader("Edit / Delete Events")

    df_events["event_label"] = df_events.apply(
        lambda row: f'{row["id"]} - {row["name"]} ({row["event_date"].strftime("%Y-%m-%d")})',
        axis=1
    )
    events_list = [""] + df_events["event_label"].tolist()
    selected_event = st.selectbox("Select an event:", events_list)

    if selected_event:
        # Extract ID from format "123 - Event X (2025-01-01)"
        event_id_str = selected_event.split(" - ")[0]
        try:
            event_id = int(event_id_str)
        except ValueError:
            st.error("Failed to interpret event ID.")
            return

        # Load selected event data
        ev_row = df_events[df_events["id"] == event_id].iloc[0]
        original_name = ev_row["name"]
        original_desc = ev_row["description"]
        original_date = ev_row["event_date"]
        original_insc = ev_row["registration_open"]

        with st.expander("Edit Event", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                new_name = st.text_input("Event Name", value=original_name)
                new_date = st.date_input("Event Date", value=original_date.date())
            with col2:
                new_insc = st.checkbox("Registration Open?", value=original_insc)
                new_desc = st.text_area("Event Description", value=original_desc)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Update Event"):
                    if new_name.strip():
                        q_update = """
                            UPDATE public.tb_eventos
                            SET nome=%s, descricao=%s, data_evento=%s, inscricao_aberta=%s
                            WHERE id=%s
                        """
                        run_query(q_update, (new_name, new_desc, new_date, new_insc, event_id), commit=True)
                        st.success("Event updated successfully!")
                        st.experimental_rerun()
                    else:
                        st.warning("Event Name cannot be empty.")

            with col_btn2:
                # Immediate deletion without extra confirmation
                if st.button("Delete Event"):
                    q_delete = "DELETE FROM public.tb_eventos WHERE id=%s;"
                    run_query(q_delete, (event_id,), commit=True)
                    st.success(f"Event ID={event_id} deleted!")
                    st.experimental_rerun()
    else:
        st.info("Select an event to edit or delete.")

###############################################################################
#                     LOYALTY PROGRAM (ADJUSTED)
###############################################################################
def loyalty_program_page():
    """Loyalty program page."""
    st.title("Loyalty Program")

    # 1) Load data from view vw_client_sum_total
    query = 'SELECT "Cliente", total_general FROM public.vw_cliente_sum_total;'
    data = run_query(query)  # Assume run_query returns list of tuples

    # 2) Display in dataframe
    if data:
        df = pd.DataFrame(data, columns=["Client", "Total General"])
        st.subheader("Clients - Loyalty")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No data found in view vw_cliente_sum_total.")

    st.markdown("---")

    # 3) (Optional) If you wish to keep the logic to accumulate points locally,
    # just keep the block below. If not needed, remove it.

    st.subheader("Earn points with every purchase!")
    if 'points' not in st.session_state:
        st.session_state.points = 0

    points_earned = st.number_input("Points to add", min_value=0, step=1)
    if st.button("Add Points"):
        st.session_state.points += points_earned
        st.success(f"Points added! Total: {st.session_state.points}")

    if st.button("Redeem Reward"):
        if st.session_state.points >= 100:
            st.session_state.points -= 100
            st.success("Reward redeemed!")
        else:
            st.error("Insufficient points.")

###############################################################################
#                     NEW PAGE: ANALYTICS (Revenue)
###############################################################################
import matplotlib.pyplot as plt

def analytics_page():
    """Analytics page containing revenue charts."""
    st.title("Analytics")

    # 1) Load revenue data
    revenue_query = """
        SELECT date("Data") as dt, SUM("total") as total_day
        FROM public.vw_pedido_produto
        WHERE status IN ('Received - Debited','Received - Credit','Received - Pix','Received - Cash')
        GROUP BY date("Data")
        ORDER BY date("Data")
    """
    revenue_data = run_query(revenue_query)
    if revenue_data:
        df_revenue = pd.DataFrame(revenue_data, columns=["Date", "Total Day"])
        df_revenue["Date"] = pd.to_datetime(df_revenue["Date"])
    else:
        df_revenue = pd.DataFrame(columns=["Date", "Total Day"])

    # 2) Display revenue chart
    st.subheader("Revenue Over Time")
    if not df_revenue.empty:
        chart = alt.Chart(df_revenue).mark_line(point=True).encode(
            x='Date:T',
            y=alt.Y('Total Day:Q', axis=alt.Axis(title='Total Revenue ($)')),
            tooltip=['Date:T', 'Total Day:Q']
        ).properties(
            width=800,
            height=400
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No revenue data to display.")

    st.markdown("---")

    # 3) Revenue Forecast using Linear Regression
    st.subheader("Revenue Forecast for the Next 30 Days")
    if not df_revenue.empty:
        df_revenue = df_revenue.sort_values("Date")
        df_revenue['Timestamp'] = df_revenue['Date'].map(datetime.timestamp)

        # Linear Regression Model
        X = df_revenue[['Timestamp']]
        y = df_revenue['Total Day']
        model = LinearRegression()
        model.fit(X, y)

        # Forecast for the next 30 days
        last_date = df_revenue['Date'].max()
        future_dates = [last_date + timedelta(days=i) for i in range(1, 31)]
        future_timestamps = [[datetime.timestamp(d)] for d in future_dates]
        predictions = model.predict(future_timestamps)

        df_pred = pd.DataFrame({
            "Date": future_dates,
            "Revenue Forecast": predictions
        })

        # Chart
        chart_pred = alt.Chart(pd.concat([df_revenue, df_pred])).mark_line().encode(
            x='Date:T',
            y=alt.Y('Total Day:Q', title='Total Revenue ($)'),
            color=alt.condition(
                alt.datum.Date <= last_date,
                alt.value('steelblue'),  # color for actual data
                alt.value('orange')      # color for forecasts
            ),
            tooltip=['Date:T', 'Total Day:Q']
        ).properties(
            width=800,
            height=400
        )
        st.altair_chart(chart_pred, use_container_width=True)
    else:
        st.info("No revenue data to perform forecasting.")

    st.markdown("---")

    # 4) MitoSheet Section for editing tb_pedido data
    st.subheader("Edit Orders with MitoSheet")

    # Function to load tb_pedido data
    @st.cache_data(show_spinner=False)
    def load_pedido_data():
        query = 'SELECT "Cliente", "Produto", "Quantidade", "Data", status, id FROM public.tb_pedido;'
        results = run_query(query)
        if results:
            df = pd.DataFrame(results, columns=["Client", "Product", "Quantity", "Date", "Status", "ID"])
            # Convert the "Date" column to datetime
            df["Date"] = pd.to_datetime(df["Date"], errors='coerce')
            return df
        else:
            return pd.DataFrame(columns=["Client", "Product", "Quantity", "Date", "Status", "ID"])

    pedido_data = load_pedido_data()

    if not pedido_data.empty:
        # Initialize MitoSheet with tb_pedido data
        new_dfs, code = spreadsheet(pedido_data)
        code = code if code else "# Edit the spreadsheet above to generate code"
        st.code(code)

        # Function to clear MitoSheet cache periodically
        def clear_mito_backend_cache():
            _get_mito_backend.clear()

        # Function to store the last execution time
        @st.cache_resource
        def get_cached_time():
            return {"last_executed_time": None}

        def try_clear_cache():
            CLEAR_DELTA = timedelta(hours=12)
            current_time = datetime.now()
            cached_time = get_cached_time()
            if cached_time["last_executed_time"] is None or cached_time["last_executed_time"] + CLEAR_DELTA < current_time:
                clear_mito_backend_cache()
                cached_time["last_executed_time"] = current_time

        try_clear_cache()

        # (Optional) Implement logic to save changes back to the database
        # This would require mapping the changes made in MitoSheet and executing the corresponding queries using `run_query`
        st.markdown("---")
        st.info("**Note:** Changes made in the spreadsheet above are not automatically saved to the database. To implement this functionality, you will need to map the changes and execute the appropriate queries using `run_query`.")
    else:
        st.info("No orders found to edit.")

###############################################################################
#                            LOGIN PAGE
###############################################################################
def login_page():
    """Login page of the application."""
    from PIL import Image
    import requests
    from io import BytesIO
    from datetime import datetime

    # ---------------------------------------------------------------------
    # 1) Custom CSS to improve appearance
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Center the container */
        .block-container {
            max-width: 450px;
            margin: 0 auto;
            padding-top: 40px;
        }
        /* Larger and bold title */
        .css-18e3th9 {
            font-size: 1.75rem;
            font-weight: 600;
            text-align: center;
        }
        /* Custom button */
        .btn {
            background-color: #004a8f !important;
            padding: 8px 16px !important;
            font-size: 0.875rem !important;
            color: white !important;
            border: none;
            border-radius: 4px;
            font-weight: bold;
            text-align: center;
            cursor: pointer;
            width: 100%;
        }
        .btn:hover {
            background-color: #003366 !important;
        }
        /* Footer message */
        .footer {
            position: fixed;
            left: 0; 
            bottom: 0; 
            width: 100%;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        /* Styled placeholder */
        input::placeholder {
            color: #bbb;
            font-size: 0.875rem;
        }
        /* Google login button */
        .gmail-login {
            background-color: #db4437;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            font-size: 0.875rem;
            font-weight: bold;
            cursor: pointer;
            text-align: center;
            margin-top: 10px;
            display: block;
            width: 100%;
        }
        .gmail-login:hover {
            background-color: #c33d30;
        }
        /* Remove space between input boxes */
        .css-1siy2j8 input {
            margin-bottom: 0 !important; /* No margin between fields */
            padding-top: 5px;
            padding-bottom: 5px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ---------------------------------------------------------------------
    # 2) Load logo
    # ---------------------------------------------------------------------
    logo_url = "https://via.placeholder.com/300x100?text=Boituva+Beach+Club"  # Direct URL to image
    logo = None
    try:
        resp = requests.get(logo_url, timeout=5)
        if resp.status_code == 200:
            logo = Image.open(BytesIO(resp.content))
    except Exception:
        pass

    if logo:
        st.image(logo, use_column_width=True)
    st.title("")

    # ---------------------------------------------------------------------
    # 3) Login Form
    # ---------------------------------------------------------------------
    with st.form("login_form", clear_on_submit=False):
        st.markdown("<p style='text-align: center;'>🌴keep the beach vibes flowing!🎾</p>", unsafe_allow_html=True)

        # Input fields
        username_input = st.text_input("", placeholder="Username")
        password_input = st.text_input("", type="password", placeholder="Password")

        # Login button
        btn_login = st.form_submit_button("Log in")

        # Google login button (outside the form)
        st.markdown(
            """
            <button class='gmail-login'>Log in with Google</button>
            """,
            unsafe_allow_html=True
        )

    # ---------------------------------------------------------------------
    # 4) Action: Login
    # ---------------------------------------------------------------------
    if btn_login:
        if not username_input or not password_input:
            st.error("Please fill in all fields.")
        else:
            try:
                # Example credentials
                creds = st.secrets["credentials"]
                admin_user = creds["admin_username"]
                admin_pass = creds["admin_password"]
                cashier_user = creds["cashier_username"]
                cashier_pass = creds["cashier_password"]
            except KeyError:
                st.error("Credentials not found in st.secrets['credentials']. Check your configuration.")
                st.stop()

            # Login verification
            if username_input == admin_user and password_input == admin_pass:
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.login_time = datetime.now()
                st.success("Successfully logged in as ADMIN!")
                st.experimental_rerun()

            elif username_input == cashier_user and password_input == cashier_pass:
                st.session_state.logged_in = True
                st.session_state.username = "cashier"
                st.session_state.login_time = datetime.now()
                st.success("Successfully logged in as CASHIER!")
                st.experimental_rerun()

            else:
                st.error("Incorrect username or password.")

    # ---------------------------------------------------------------------
    # 5) Footer
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <div class='footer'>
            © 2025 | All rights reserved | Boituva Beach Club
        </div>
        """,
        unsafe_allow_html=True
    )

###############################################################################
#                            INITIALIZATION AND MAIN
###############################################################################
def initialize_session_state():
    """Initializes variables in Streamlit's session_state."""
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

def apply_custom_css():
    """Applies custom CSS to improve the appearance of the application."""
    st.markdown(
        """
        <style>
        .css-1d391kg {
            font-size: 2em;
            color: #1b4f72;
        }
        .stDataFrame table {
            width: 100%;
            overflow-x: auto;
        }
        .css-1aumxhk {
            background-color: #1b4f72;
            color: white;
        }
        @media only screen and (max-width: 600px) {
            .css-1d391kg {
                font-size: 1.5em;
            }
        }
        .css-1v3fvcr {
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            text-align: center;
            font-size: 12px;
        }
        </style>
        <div class='css-1v3fvcr'>© Copyright 2025 - kiko Technologies</div>
        """,
        unsafe_allow_html=True
    )

def sidebar_navigation():
    """Configures the sidebar navigation."""
    with st.sidebar:
        # New text above the menu
        if 'login_time' in st.session_state:
            st.write(
                f"{st.session_state.username.capitalize()} logged in at {st.session_state.login_time.strftime('%H:%M')}"
            )

        st.title("Boituva Beach Club 🎾")
        selected = option_menu(
            "Main Menu",
            [
                "Home","Orders","Products","Stock","Clients",
                "Invoice","Backup","Menu",
                "Analytics",                # Renamed
                "Loyalty Program","Events Calendar"
            ],
            icons=[
                "house","file-text","box","list-task","layers",
                "receipt","cloud-upload","list",
                "bar-chart-line",          # Changed icon
                "gift","calendar"
            ],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"background-color": "#1b4f72"},
                "icon": {"color": "white","font-size":"18px"},
                "nav-link": {
                    "font-size": "14px","text-align":"left","margin":"0px",
                    "color":"white","--hover-color":"#145a7c"
                },
                "nav-link-selected": {"background-color":"#145a7c","color":"white"},
            }
        )
    return selected

def menu_page():
    """Menu page."""
    st.title("Menu")

    product_data = run_query("""
        SELECT supplier, product, quantity, unit_value, total_value, creation_date, image_url
        FROM public.tb_products
        ORDER BY creation_date DESC
    """)
    if not product_data:
        st.warning("No products found in the menu.")
        return

    df_products = pd.DataFrame(
        product_data,
        columns=["Supplier", "Product", "Quantity", "Unit Value", "Total Value", "Creation Date", "image_url"]
    )
    df_products["Price"] = df_products["Unit Value"].apply(format_currency)

    tabs = st.tabs(["View Menu", "Manage Images"])

    with tabs[0]:
        st.subheader("Available Items")
        for idx, row in df_products.iterrows():
            product_name = row["Product"]
            price_text   = row["Price"]
            image_url    = row["image_url"] if row["image_url"] else ""

            if not image_url:
                image_url = "https://via.placeholder.com/120"

            col1, col2 = st.columns([1, 3])
            with col1:
                try:
                    st.image(image_url, width=120)
                except:
                    st.image("https://via.placeholder.com/120", width=120)

            with col2:
                st.subheader(product_name)
                st.write(f"Price: {price_text}")

            st.markdown("---")

    with tabs[1]:
        st.subheader("Upload/Edit Product Image")

        product_names = df_products["Product"].unique().tolist()
        chosen_product = st.selectbox("Select Product", options=[""] + product_names)

        if chosen_product:
            df_sel = df_products[df_products["Product"] == chosen_product].head(1)
            if not df_sel.empty:
                current_image = df_sel.iloc[0]["image_url"] or ""
            else:
                current_image = ""

            st.write("Current Image:")
            if current_image:
                try:
                    st.image(current_image, width=200)
                except:
                    st.image("https://via.placeholder.com/200", width=200)
            else:
                st.image("https://via.placeholder.com/200", width=200)

            uploaded_file = st.file_uploader("Upload new product image (PNG/JPG)", type=["png", "jpg", "jpeg"])

            if st.button("Save Image"):
                if not uploaded_file:
                    st.warning("Please select a file before saving.")
                else:
                    file_ext = os.path.splitext(uploaded_file.name)[1]
                    new_filename = f"{uuid.uuid4()}{file_ext}"
                    os.makedirs("uploaded_images", exist_ok=True)
                    save_path = os.path.join("uploaded_images", new_filename)
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    update_query = """
                        UPDATE public.tb_products
                        SET image_url=%s
                        WHERE product=%s
                    """
                    run_query(update_query, (save_path, chosen_product), commit=True)
                    st.success("Image successfully updated!")
                    refresh_data()
                    st.experimental_rerun()

###############################################################################
#                     MAIN APPLICATION LOGIC
###############################################################################
def main():
    """Main function controlling the application flow."""
    apply_custom_css()
    initialize_session_state()

    if not st.session_state.logged_in:
        login_page()
        return

    selected_page = sidebar_navigation()

    if 'current_page' not in st.session_state:
        st.session_state.current_page = selected_page
    elif selected_page != st.session_state.current_page:
        refresh_data()
        st.session_state.current_page = selected_page

    if selected_page == "Home":
        home_page()
    elif selected_page == "Orders":
        orders_page()
    elif selected_page == "Products":
        products_page()
    elif selected_page == "Stock":
        stock_page()
    elif selected_page == "Clients":
        clients_page()
    elif selected_page == "Invoice":
        invoice_page()
    elif selected_page == "Backup":
        admin_backup_section()
    elif selected_page == "Menu":
        menu_page()
    elif selected_page == "Analytics":  # <-- New simplified page
        analytics_page()
    elif selected_page == "Loyalty Program":
        loyalty_program_page()
    elif selected_page == "Events Calendar":
        events_calendar_page()

    with st.sidebar:
        if st.button("Logout"):
            for key in ["home_page_initialized"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.logged_in = False
            st.success("Successfully logged out!")
            st.experimental_rerun()

if __name__ == "__main__":
    main()
