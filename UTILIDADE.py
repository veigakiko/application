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

###############################################################################
#                                   UTILITIES
###############################################################################
def format_currency(value: float) -> str:
    """
    Format a numerical value as Brazilian currency.
    Example: 1234.56 -> 'R$ 1.234,56'
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Provide a Streamlit download button for downloading a DataFrame as a CSV file.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")

def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """
    Convert a pandas DataFrame to PDF bytes using FPDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Header
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()
    # Rows
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()
    return pdf.output(dest='S')

###############################################################################
#                            DATABASE OPERATIONS
###############################################################################
@st.cache_resource
def get_db_connection():
    """
    Create a connection to the PostgreSQL database using secrets. 
    Cached as a resource to avoid repeated connections.
    """
    try:
        conn = psycopg2.connect(
            host=st.secrets["db"]["host"],
            database=st.secrets["db"]["name"],
            user=st.secrets["db"]["user"],
            password=st.secrets["db"]["password"],
            port=st.secrets["db"]["port"]
        )
        return conn
    except OperationalError:
        st.error("Não foi possível conectar ao banco de dados. Por favor, tente novamente mais tarde.")
        return None

def run_query(query: str, values=None, commit: bool = False):
    """
    Execute a SQL query. If commit=True, changes are committed (INSERT/UPDATE/DELETE).
    Otherwise, results are fetched and returned.
    """
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values or ())
            if commit:
                conn.commit()
                return True
            else:
                return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return None
    finally:
        conn.close()

###############################################################################
#                          DATA LOADING AND CACHING
###############################################################################
@st.cache_data
def load_all_data():
    """
    Load all relevant data from the database and return as a dictionary.
    Data is cached to avoid re-fetching on every interaction.
    """
    data = {}
    try:
        orders_query = 'SELECT "Cliente", "Produto", "Quantidade", "Data", status FROM public.tb_pedido ORDER BY "Data" DESC'
        products_query = 'SELECT supplier, product, quantity, unit_value, total_value, creation_date FROM public.tb_products ORDER BY creation_date DESC'
        clients_query = 'SELECT DISTINCT "Cliente" FROM public.tb_pedido ORDER BY "Cliente"'
        stock_query = 'SELECT "Produto", "Quantidade", "Transação", "Data" FROM public.tb_estoque ORDER BY "Data" DESC'

        data["orders"] = run_query(orders_query) or []
        data["products"] = run_query(products_query) or []
        data["clients"] = run_query(clients_query) or []
        data["stock"] = run_query(stock_query) or []
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
    return data

def refresh_data():
    """
    Force-refresh the cached data by clearing and re-calling load_all_data().
    """
    load_all_data.clear()
    st.session_state.data = load_all_data()

###############################################################################
#                                 PAGE FUNCTIONS
###############################################################################
def home_page():
    """
    Página inicial (Home) do Boituva Beach Club.
    Exibe algumas informações gerais e alertas de pedidos abertos.
    """
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

    notification_placeholder = st.empty()
    client_count_query = """
        SELECT COUNT(DISTINCT "Cliente") AS client_count
        FROM public.tb_pedido
        WHERE status = %s
    """
    client_count = run_query(client_count_query, ('em aberto',))
    if client_count and client_count[0][0] > 0:
        notification_placeholder.success(f"Há {client_count[0][0]} clientes com pedidos em aberto!")
    else:
        notification_placeholder.info("Nenhum cliente com pedido em aberto no momento.")

def orders_page():
    """
    Página para registrar e gerenciar pedidos.
    Administradores podem editar e deletar pedidos.
    """
    st.title("Orders")
    st.subheader("Register a new order")

    # Carrega dados dos produtos e clientes
    product_data = st.session_state.data.get("products", [])
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products available"]

    with st.form(key='order_form'):
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo')
        customer_list = [""] + [row[0] for row in clientes] if clientes else []
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
                VALUES (%s, %s, %s, %s, 'em aberto')
            """
            timestamp = datetime.now()
            success = run_query(query, (customer_name, product, quantity, timestamp), commit=True)
            if success:
                st.success("Order registered successfully!")
                refresh_data()
            else:
                st.error("Failed to register the order.")
        else:
            st.warning("Please fill in all fields correctly.")

    # Exibe todos os pedidos
    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("All Orders")
        columns = ["Client", "Product", "Quantity", "Date", "Status"]
        df_orders = pd.DataFrame(orders_data, columns=columns)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Download Orders CSV")
    else:
        st.info("No orders found.")

def main():
    """
    Main entry point for the Streamlit app. 
    Does NOT run automatically on import—only when called.
    """
    st.set_page_config(page_title="Improved Beach Club App")
    
    # Initialize session data if not present
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()

    st.sidebar.title("Navigation")
    selected = option_menu(
        "Menu Principal",
        ["Home", "Orders"],
        icons=["house", "file-text"],
        menu_icon="cast",
        default_index=0
    )

    if selected == "Home":
        home_page()
    elif selected == "Orders":
        orders_page()

    # Simple logout button (optional)
    if st.sidebar.button("Stop App"):
        st.stop()

# NOTE: We do NOT call main() here by default.
# To run this app:
#   1) Save this file (e.g., as 'improved_app.py').
#   2) From the command line, run: streamlit run improved_app.py
#   OR import this module into another script and call main() there.
