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
from io import BytesIO
from zipfile import ZipFile

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
    except OperationalError:
        st.error("Não foi possível conectar ao banco de dados. Por favor, tente novamente mais tarde.")
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
            ["Home", "Orders", "Products", "Stock", "Clients", "Nota Fiscal", "Backup"],
            icons=["house", "file-text", "box", "list-task", "layers", "receipt", "cloud-upload"],
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
# FUNÇÕES ADICIONAIS PARA ENVIO
#####################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """
    Converte um DataFrame em PDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Adicionar cabeçalhos
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()

    # Adicionar linhas de dados
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()

    # Obter a saída do PDF
    pdf_output = pdf.output(dest='S')

    return pdf_output

def upload_pdf_to_fileio(pdf_bytes: bytes) -> str:
    """
    Faz upload do PDF para File.io e retorna a URL pública.
    """
    try:
        response = requests.post(
            'https://file.io/',
            files={'file': ('stock_vs_orders_summary.pdf', pdf_bytes, 'application/pdf')}
        )
        if response.status_code == 200:
            json_resp = response.json()
            if json_resp['success']:
                return json_resp['link']
            else:
                st.error("Falha no upload do arquivo.")
                return ""
        else:
            st.error("Erro ao conectar com o serviço de upload.")
            return ""
    except Exception as e:
        st.error(f"Erro ao fazer upload do arquivo: {e}")
        return ""

#####################
# BACKUP PAGE - Added button to download all tables at once
def export_all_tables():
    st.header("Backup de Tabelas")
    st.write("Clique no botão abaixo para realizar o backup de todas as tabelas do sistema.")

    # Liste as tabelas que você deseja fazer backup
    tables = ["tb_pedido", "tb_products", "tb_clientes", "tb_estoque"]

    all_csv_data = {}
    for table in tables:
        try:
            query = f"SELECT * FROM {table};"
            conn = get_db_connection()
            df = pd.read_sql_query(query, conn)
            all_csv_data[table] = df.to_csv(index=False)
            conn.close()
        except Exception as e:
            st.error(f"Erro ao exportar a tabela {table}: {e}")

    # Combine all CSVs into a zip file
    zip_buffer = BytesIO()
    with ZipFile(zip_buffer, 'w') as zip_file:
        for table, csv_data in all_csv_data.items():
            zip_file.writestr(f"{table}.csv", csv_data)
    zip_buffer.seek(0)

    st.download_button(
        label="Download All Tables as ZIP",
        data=zip_buffer,
        file_name="all_tables_backup.zip",
        mime="application/zip"
    )

# FOOTER - Added copyright message
def apply_footer():
    st.markdown(
        """
        <footer style="font-size: 10px; text-align: center; color: #555;">
            © Copyright 2025 - kiko Technologies
        </footer>
        """, 
        unsafe_allow_html=True
    )

# INICIALIZAÇÃO - Adjusted to reflect the changes
def initialize_session_state():
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

def apply_custom_css():
    st.markdown(
        """
        <style>
        /* Ajustar fonte e cores */
        .css-1d391kg {  /* Classe para título */
            font-size: 2em;
            color: #1b4f72;
        }
        /* Tornar tabelas responsivas */
        .stDataFrame table {
            width: 100%;
            overflow-x: auto;
        }
        /* Ajustar botões */
        .css-1aumxhk {
            background-color: #1b4f72;
            color: white;
        }
        /* Responsividade para dispositivos móveis */
        @media only screen and (max-width: 600px) {
            .css-1d391kg {
                font-size: 1.5em;
            }
            /* Outros ajustes específicos */
        }
        </style>
        """,
        unsafe_allow_html=True
    )

if __name__ == "__main__":
    apply_custom_css()
    initialize_session_state()

    if not st.session_state.logged_in:
        login_page()
    else:
        selected_page = sidebar_navigation()

        if 'current_page' not in st.session_state:
            st.session_state.current_page = selected_page
        elif selected_page != st.session_state.current_page:
            refresh_data()
            st.session_state.current_page = selected_page
            if selected_page == "Home":
                st.session_state.home_page_initialized = False

        # Roteamento de Páginas
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
            export_all_tables()

        apply_footer()

        with st.sidebar:
            if st.button("Logout"):
                keys_to_reset = ['home_page_initialized']
                for key in keys_to_reset:
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.logged_in = False
                st.success("Desconectado com sucesso!")
                st.experimental_rerun()
