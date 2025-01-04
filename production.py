import streamlit as st
from streamlit_option_menu import option_menu
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime, date
import pandas as pd
from PIL import Image
import requests
from io import BytesIO
from fpdf import FPDF
import json
import os
import subprocess
import altair as alt

########################
# UTILIDADES GERAIS
########################
def format_currency(value: float) -> str:
    """
    Formata um valor para o formato monetário brasileiro: R$ x.xx
    Exemplo:
        1234.56 -> "R$ 1.234,56"
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Exibe um botão de download de um DataFrame como CSV.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(
        label=label,
        data=csv_data,
        file_name=filename,
        mime="text/csv",
    )

def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    """
    Exibe um botão de download de um DataFrame como Excel.
    """
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Stock_vs_Orders')
    towrite.seek(0)
    st.download_button(
        label=label,
        data=towrite,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    """
    Exibe um botão de download de um DataFrame como JSON.
    """
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(
        label=label,
        data=json_data,
        file_name=filename,
        mime="application/json",
    )

def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    """
    Exibe um botão de download de um DataFrame como HTML.
    """
    html_data = df.to_html(index=False)
    st.download_button(
        label=label,
        data=html_data,
        file_name=filename,
        mime="text/html",
    )

def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    """
    Exibe um botão de download de um DataFrame como Parquet.
    """
    import io
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    st.download_button(
        label=label,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/octet-stream",
    )

########################
# CONEXÃO COM BANCO (SEM CACHE)
########################
def get_db_connection():
    """
    Retorna uma conexão com o banco de dados usando st.secrets e psycopg2.
    Abre e fecha a cada consulta (sem uso de cache).
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
    except OperationalError as e:
        st.error(f"Erro ao conectar ao banco de dados: {e}")
        return None
    except Exception as e:
        st.error(f"Ocorreu um erro inesperado ao tentar se conectar ao banco de dados: {e}")
        return None

def run_query(query, values=None):
    """
    Executa uma consulta de leitura (SELECT) e retorna os dados obtidos.
    Abre e fecha a conexão a cada chamada.
    """
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values or ())
            return cursor.fetchall()
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return []
    finally:
        conn.close()

def run_insert(query, values):
    """
    Executa uma consulta de inserção, atualização ou deleção (INSERT, UPDATE ou DELETE).
    Abre e fecha a conexão a cada chamada.
    """
    conn = get_db_connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return False
    finally:
        conn.close()

#####################
# CARREGAMENTO DE DADOS
#####################
def load_all_data():
    """
    Carrega todos os dados utilizados pelo aplicativo e retorna em um dicionário.
    """
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
    """
    Recarrega todos os dados e atualiza o estado da sessão.
    """
    st.session_state.data = load_all_data()

#####################
# PÁGINA DE ANALYTICS
#####################
def analytics_page():
    st.title("Analytics - Faturamento por Produto")

    # Consulta à view
    query = """
    SELECT 
        "Produto", 
        REPLACE(total_faturado, 'R$', '')::NUMERIC AS total_faturado
    FROM 
        vw_produto_total_faturado
    ORDER BY 
        total_faturado DESC;
    """

    conn = get_db_connection()

    if conn:
        try:
            # Carregando os dados
            df = pd.read_sql_query(query, conn)

            # Fechando a conexão
            conn.close()

            # Formatação dos valores em reais
            df["total_faturado_formatado"] = df["total_faturado"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

            # Criando o gráfico
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X("total_faturado:Q", title="Total Faturado (R$)"),
                y=alt.Y("Produto:O", sort='-x', title="Produto"),
                tooltip=[ 
                    "Produto", 
                    alt.Tooltip("total_faturado:Q", title="Total Faturado (R$)", format=",.2f")
                ]
            ).properties(
                title="Faturamento por Produto",
                width=600,
                height=400
            )

            # Adicionando rótulos de texto
            text = chart.mark_text(
                align='left',
                baseline='middle',
                dx=3  # Deslocamento
            ).encode(
                text=alt.Text("total_faturado_formatado:N")
            )

            # Exibindo o gráfico
            final_chart = chart + text
            st.altair_chart(final_chart, use_container_width=True)

        except Exception as e:
            st.error(f"Erro ao processar os dados: {e}")
    else:
        st.error("Conexão com o banco de dados falhou.")

#####################
# PÁGINA HOME
#####################
def home_page():
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

#####################
# MENU LATERAL
#####################
def sidebar_navigation():
    """
    Cria um menu lateral para navegação usando streamlit_option_menu.
    """
    with st.sidebar:
        st.title("Boituva Beach Club 🎾")
        selected = option_menu(
            "Menu Principal",
            ["Home", "Orders", "Products", "Stock", "Clients", "Nota Fiscal", "Backup", "Analytics"],  # Adicionando a página Analytics
            icons=["house", "file-text", "box", "list-task", "layers", "receipt", "cloud-upload", "chart-line"],  # Ícone do gráfico
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
# INICIALIZAÇÃO
#####################
def initialize_session_state():
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

if __name__ == "__main__":
    initialize_session_state()

    selected_page = sidebar_navigation()

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
    elif selected_page == "Backup":
        admin_backup_section()
    elif selected_page == "Analytics":
        analytics_page()  # Página de Analytics

    with st.sidebar:
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.success("Desconectado com sucesso!")
            st.experimental_rerun()
