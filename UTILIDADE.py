import streamlit as st
import psycopg2
from psycopg2 import OperationalError
from datetime import datetime
import pandas as pd
import requests
from io import BytesIO
from fpdf import FPDF

###############################################################################
#                              CONEXÃO COM O BANCO
###############################################################################
@st.cache_resource
def get_db_connection():
    """
    Cria conexão PostgreSQL usando dados em st.secrets["db"].
    Retorna None se falhar.
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
        st.error(f"Erro de conexão: {e}")
        return None

def run_query(query, values=None, commit=False):
    """
    Executa SQL no PostgreSQL.
    Se commit=True, faz INSERT/UPDATE/DELETE. Caso contrário, retorna SELECT.
    Evita rollback se a conexão já estiver fechada.
    """
    conn = get_db_connection()
    if not conn:
        return None  # Falha na conexão

    try:
        with conn.cursor() as cursor:
            cursor.execute(query, values or ())
            if commit:
                conn.commit()
                return True
            else:
                return cursor.fetchall()
    except Exception as e:
        # Evita rollback em conexão fechada
        if conn and not conn.closed:
            conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return None
    finally:
        conn.close()

###############################################################################
#                       FUNÇÕES DE PDF E DOWNLOAD (OPCIONAIS)
###############################################################################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """
    Converte um DataFrame para PDF (bytes) usando FPDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    # Cabeçalho
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()
    # Linhas
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()
    return pdf.output(dest="S")

def download_df_as_csv(df: pd.DataFrame, filename: str):
    """
    Cria botão para baixar DataFrame como CSV no Streamlit.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(
        label="Baixar CSV",
        data=csv_data,
        file_name=filename,
        mime="text/csv"
    )

###############################################################################
#                         FUNÇÃO PARA ENVIAR WHATSAPP
###############################################################################
def send_whatsapp(recipient_number: str, media_url: str = None):
    """
    Envia WhatsApp usando Twilio (dados em st.secrets["twilio"]).
    Se media_url for fornecida, envia PDF ou outro arquivo.
    Formato do recipient_number: "5511999999999" (sem +, iremos adicionar).
    """
    from twilio.rest import Client

    account_sid = st.secrets["twilio"]["account_sid"]
    auth_token = st.secrets["twilio"]["auth_token"]
    whatsapp_from = st.secrets["twilio"]["whatsapp_from"]

    try:
        client = Client(account_sid, auth_token)

        if media_url:
            message = client.messages.create(
                body="Segue o PDF solicitado!",
                from_=whatsapp_from,
                to=f"whatsapp:+{recipient_number}",
                media_url=[media_url]
            )
        else:
            message = client.messages.create(
                body="Olá! Esta é uma mensagem de teste.",
                from_=whatsapp_from,
                to=f"whatsapp:+{recipient_number}"
            )

        st.success(f"WhatsApp enviado com sucesso! SID: {message.sid}")
    except Exception as e:
        st.error(f"Erro ao enviar WhatsApp: {e}")

###############################################################################
#                       PÁGINAS (HOME, ORDERS) DE EXEMPLO
###############################################################################
def home_page():
    """
    Página inicial após login, com algum resumo de pedidos.
    """
    st.title("Página Home")
    st.write("Bem-vindo ao sistema!")

    st.subheader("Pedidos em Aberto")
    query = 'SELECT COUNT(*) FROM tb_pedido WHERE status=%s;'
    result = run_query(query, ('em aberto',))
    if result:
        count_open = result[0][0]
        st.info(f"Existem {count_open} pedidos em aberto.")
    else:
        st.warning("Não foi possível obter dados de pedidos em aberto.")

    # Exemplo: Botão para enviar WhatsApp sem arquivo
    st.subheader("Envie uma mensagem de teste no WhatsApp")
    phone_input = st.text_input("Número (somente dígitos c/ DDD, ex: 5511999999999):")
    if st.button("Enviar Mensagem"):
        if phone_input:
            send_whatsapp(phone_input, media_url=None)
        else:
            st.warning("Informe o número de destino.")

def orders_page():
    """
    Página de Pedidos simples (INSERT e SELECT).
    """
    st.title("Pedidos")

    # Form para inserir um novo pedido
    with st.form("new_order"):
        st.write("Novo Pedido")
        cliente = st.text_input("Cliente")
        produto = st.text_input("Produto")
        quantidade = st.number_input("Quantidade", min_value=1, step=1)
        submit_order = st.form_submit_button("Registrar Pedido")

    if submit_order:
        if cliente and produto and quantidade > 0:
            query = """
                INSERT INTO tb_pedido ("Cliente","Produto","Quantidade","Data","status")
                VALUES (%s,%s,%s,%s,%s)
            """
            success = run_query(query,
                                (cliente, produto, quantidade, datetime.now(), 'em aberto'),
                                commit=True)
            if success:
                st.success("Pedido registrado com sucesso!")
            else:
                st.error("Falha ao registrar o pedido.")
        else:
            st.warning("Preencha todos os campos.")

    # Exibir tabela de pedidos
    st.write("---")
    st.subheader("Lista de Pedidos")
    query_list = 'SELECT "Cliente","Produto","Quantidade","Data","status" FROM tb_pedido ORDER BY "Data" DESC'
    orders_data = run_query(query_list)
    if orders_data:
        cols = ["Cliente", "Produto", "Quantidade", "Data", "Status"]
        df_orders = pd.DataFrame(orders_data, columns=cols)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "pedidos.csv")

        # Exemplo de PDF e envio por WhatsApp
        st.write("Gerar PDF dos Pedidos")
        pdf_bytes = convert_df_to_pdf(df_orders)
        st.download_button(
            label="Baixar PDF",
            data=pdf_bytes,
            file_name="pedidos.pdf",
            mime="application/pdf"
        )

        # Se quiser enviar PDF via WhatsApp
        st.write("Envie esse PDF pelo WhatsApp (file.io)")
        phone_to = st.text_input("Número p/ WhatsApp (ex: 5511999999999)", key="pdf_send")
        if st.button("Upload PDF e Enviar"):
            # Faz upload do PDF para file.io
            try:
                response = requests.post(
                    "https://file.io",
                    files={"file": ("pedidos.pdf", pdf_bytes, "application/pdf")}
                )
                if response.status_code == 200:
                    resp_json = response.json()
                    if resp_json.get("success"):
                        link = resp_json.get("link")
                        # Envia via Twilio
                        send_whatsapp(phone_to, media_url=link)
                    else:
                        st.error("Falha no upload do arquivo (file.io).")
                else:
                    st.error("Erro ao conectar com file.io.")
            except Exception as e:
                st.error(f"Erro ao enviar PDF para file.io: {e}")
    else:
        st.warning("Nenhum pedido encontrado ou erro ao buscar dados.")

###############################################################################
#                               LOGIN E MAIN
###############################################################################
def login_page():
    """
    Página de Login. Usa as credenciais em st.secrets["credentials"].
    """
    st.title("Login")
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submitted = st.form_submit_button("Entrar")

    if submitted:
        creds = st.secrets["credentials"]
        # Admin
        if (username == creds["admin_username"] and
                password == creds["admin_password"]):
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.success("Login como ADMIN.")
        # Caixa
        elif (username == creds["caixa_username"] and
              password == creds["caixa_password"]):
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.success("Login como CAIXA.")
        else:
            st.error("Credenciais inválidas. Tente novamente.")


def main():
    st.set_page_config(page_title="Beach Tennis App", layout="wide")

    # Inicializa estado de login se não existir
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    # Se usuário não estiver logado, mostra página de login
    if not st.session_state.logged_in:
        login_page()
        return

    # Se logado, mostra menu lateral
    st.sidebar.title(f"Bem-vindo, {st.session_state.get('username')}")
    choice = st.sidebar.radio("Navegação", ["Home", "Orders"])

    if choice == "Home":
        home_page()
    elif choice == "Orders":
        orders_page()

    # Botão de logout
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.experimental_rerun()

if __name__ == "__main__":
    main()
