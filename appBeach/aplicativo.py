# application.py
import streamlit as st
from streamlit_option_menu import option_menu
import requests
from PIL import Image
from datetime import datetime, date
import pandas as pd

# Import your new modules
from db_utils import run_query, run_insert
from app_utils import format_currency, download_df_as_csv
from pages.home_page import home_page
from pages.orders_page import orders_page
from pages.products_page import products_page
from pages.stock_page import stock_page
from pages.clients_page import clients_page
from pages.invoice_page import invoice_page

########################
# Initialization
########################
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = None

# Optionally cache data:
@st.cache_data(show_spinner=False)
def load_all_data():
    data = {}
    try:
        data["orders"] = run_query(
            'SELECT "Cliente", "Produto", "Quantidade", "Data", status FROM public.tb_pedido ORDER BY "Data" DESC;'
        )
        data["products"] = run_query(
            'SELECT supplier, product, quantity, unit_value, total_value, creation_date FROM public.tb_products ORDER BY creation_date DESC;'
        )
        data["clients"] = run_query('SELECT DISTINCT "Cliente" FROM public.tb_pedido ORDER BY "Cliente";')
        data["stock"] = run_query(
            'SELECT "Produto", "Quantidade", "Transação", "Data" FROM public.tb_estoque ORDER BY "Data" DESC;'
        )
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
    return data

def refresh_data():
    load_all_data.clear()  # Clear the cache
    st.session_state.data = load_all_data()

if 'data' not in st.session_state:
    st.session_state.data = load_all_data()

#####################
# Login Page
#####################
def login_page():
    st.title("Beach Club")
    st.write("Por favor, insira suas credenciais para acessar o aplicativo.")

    with st.form(key='login_form'):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_login = st.form_submit_button(label="Login")

    if submit_login:
        if username == "admin" and password == "adminbeach":
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.success("Login bem-sucedido!")
        elif username == "caixa" and password == "caixabeach":
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.success("Login bem-sucedido!")
        else:
            st.error("Nome de usuário ou senha incorretos.")

#####################
# Sidebar Navigation
#####################
def sidebar_navigation():
    with st.sidebar:
        st.title("Boituva Beach Club 🎾")
        selected = option_menu(
            "Menu Principal",
            ["Home", "Orders", "Products", "Stock", "Clients", "Nota Fiscal"],
            icons=["house", "file-text", "box", "list-task", "layers", "receipt"],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"background-color": "#1b4f72"},
                "icon": {"color": "white", "font-size": "18px"},
                "nav-link": {
                    "font-size": "14px",
                    "text-align": "left",
                    "margin": "0px",
                    "color": "white",
                    "--hover-color": "#145a7c",
                },
                "nav-link-selected": {"background-color": "#145a7c", "color": "white"},
            },
        )
    return selected

#####################
# Main
#####################
def main():
    if not st.session_state.logged_in:
        login_page()
    else:
        selected_page = sidebar_navigation()

        if 'current_page' not in st.session_state:
            st.session_state.current_page = selected_page
        elif selected_page != st.session_state.current_page:
            refresh_data()
            st.session_state.current_page = selected_page

        # Route to the selected page
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
        elif selected_page == "Nota Fiscal":
            invoice_page()

        with st.sidebar:
            if st.button("Logout"):
                st.session_state.logged_in = False
                st.success("Desconectado com sucesso!")
                st.experimental_rerun()

if __name__ == "__main__":
    main()
