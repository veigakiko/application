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
#                                   UTILIDADES
###############################################################################
def format_currency(value: float) -> str:
    """
    Formata um valor como moeda brasileira (ex: 1234.56 -> 'R$ 1.234,56').
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    towrite.seek(0)
    st.download_button(label=label, data=towrite, file_name=filename,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")


def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")


def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    import io
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    st.download_button(label=label, data=buffer.getvalue(),
                       file_name=filename, mime="application/octet-stream")


###############################################################################
#                      FUNÇÕES PARA PDF E UPLOAD (OPCIONAIS)
###############################################################################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """
    Converte um DataFrame em bytes de PDF usando FPDF.
    """
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()
    return pdf.output(dest='S')


def upload_pdf_to_fileio(pdf_bytes: bytes) -> str:
    """
    Faz upload de um arquivo PDF em file.io e retorna o link gerado, se bem-sucedido.
    """
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
                st.error("Falha no upload (file.io não retornou sucesso).")
                return ""
        else:
            st.error("Erro ao conectar com file.io.")
            return ""
    except Exception as e:
        st.error(f"Erro ao fazer upload: {e}")
        return ""


###############################################################################
#                               TWILIO (WHATSAPP)
###############################################################################
def send_whatsapp(recipient_number: str, media_url: str = None):
    """
    Envia WhatsApp via Twilio (dados em st.secrets["twilio"]).
    Exemplo de 'recipient_number': '5511999999999' (sem '+').
    """
    from twilio.rest import Client
    try:
        account_sid = st.secrets["twilio"]["account_sid"]
        auth_token = st.secrets["twilio"]["auth_token"]
        whatsapp_from = st.secrets["twilio"]["whatsapp_from"]

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
                body="Olá! Teste de mensagem via Twilio WhatsApp.",
                from_=whatsapp_from,
                to=f"whatsapp:+{recipient_number}"
            )
        st.success(f"WhatsApp enviado com sucesso! SID: {message.sid}")
    except Exception as e:
        st.error(f"Erro ao enviar WhatsApp: {e}")


###############################################################################
#                            CONEXÃO COM BANCO
###############################################################################
def get_db_connection():
    """
    Cria conexão com PostgreSQL a cada chamada, sem cache, para evitar
    'connection already closed' em reuso de conexão fechada.
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
        st.error(f"Não foi possível conectar ao banco: {e}")
        return None


def run_query(query: str, values=None, commit: bool = False):
    """
    Executa SQL abrindo e fechando conexão a cada chamada. 
    Evita reuso de conexão fechada.
    Se commit=True, faz INSERT/UPDATE/DELETE; caso contrário, SELECT.
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
    except Exception as e:
        # Só faz rollback se a conexão ainda estiver aberta
        if not conn.closed:
            conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return None
    finally:
        if not conn.closed:
            conn.close()


###############################################################################
#                         CARREGAMENTO DE DADOS (CACHE)
###############################################################################
@st.cache_data
def load_all_data():
    """
    Carrega dados do banco para uso em várias páginas. 
    Cada chamada a 'run_query' abre e fecha uma conexão independente.
    """
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
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
    return data


def refresh_data():
    """
    Limpa o cache de dados e recarrega.
    """
    load_all_data.clear()
    st.session_state.data = load_all_data()


###############################################################################
#                           PÁGINAS DO APLICATIVO
###############################################################################
def home_page():
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

    notification_placeholder = st.empty()
    client_count_query = """
        SELECT COUNT(DISTINCT "Cliente") 
        FROM public.tb_pedido
        WHERE status=%s
    """
    client_count = run_query(client_count_query, ('em aberto',))
    if client_count and client_count[0][0] > 0:
        notification_placeholder.success(f"Há {client_count[0][0]} clientes com pedidos em aberto!")
    else:
        notification_placeholder.info("Nenhum cliente com pedido em aberto no momento.")

    if st.session_state.get("username") == "admin":
        st.markdown("**Open Orders Summary**")
        open_orders_query = """
            SELECT "Cliente",SUM("total") AS Total
            FROM public.vw_pedido_produto
            WHERE status=%s
            GROUP BY "Cliente"
            ORDER BY "Cliente" DESC
        """
        open_orders_data = run_query(open_orders_query, ('em aberto',))
        if open_orders_data:
            df_open = pd.DataFrame(open_orders_data, columns=["Client","Total"])
            total_open = df_open["Total"].sum()
            df_open["Total_display"] = df_open["Total"].apply(format_currency)
            st.table(df_open[["Client","Total_display"]])
            st.markdown(f"**Total Geral (Open Orders):** {format_currency(total_open)}")
        else:
            st.info("Nenhum pedido em aberto encontrado.")

        st.markdown("**Stock vs. Orders Summary**")
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
                st.markdown(f"**Total Geral (Stock vs. Orders):** {total_val}")

                pdf_bytes = convert_df_to_pdf(df_svo)
                st.subheader("Baixar PDF 'Stock vs Orders'")
                st.download_button(
                    label="Baixar PDF",
                    data=pdf_bytes,
                    file_name="stock_vs_orders_summary.pdf",
                    mime="application/pdf"
                )

                st.subheader("Enviar esse PDF via WhatsApp")
                phone_number = st.text_input("Número (ex: 5511999999999)")
                if st.button("Upload e Enviar"):
                    link = upload_pdf_to_fileio(pdf_bytes)
                    if link and phone_number:
                        send_whatsapp(phone_number, media_url=link)
                    else:
                        st.warning("Informe o número e tenha link válido.")
            else:
                st.info("View 'vw_stock_vs_orders_summary' sem dados ou inexistente.")
        except Exception as e:
            st.error(f"Erro ao gerar resumo Stock vs. Orders: {e}")


def orders_page():
    st.title("Orders")
    st.subheader("Registrar novo pedido")

    product_data = st.session_state.data.get("products", [])
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products"]

    with st.form(key='order_form'):
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo')
        customer_list = [""] + [row[0] for row in clientes] if clientes else []
        col1, col2, col3 = st.columns(3)
        with col1:
            customer_name = st.selectbox("Cliente", customer_list)
        with col2:
            product = st.selectbox("Produto", product_list)
        with col3:
            quantity = st.number_input("Quantidade", min_value=1, step=1)
        submit_button = st.form_submit_button("Registrar Pedido")

    if submit_button:
        if customer_name and product and quantity > 0:
            query_insert = """
                INSERT INTO public.tb_pedido("Cliente","Produto","Quantidade","Data",status)
                VALUES (%s,%s,%s,%s,'em aberto')
            """
            if run_query(query_insert, (customer_name, product, quantity, datetime.now()), commit=True):
                st.success("Pedido registrado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao registrar pedido.")
        else:
            st.warning("Preencha todos os campos.")

    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("Todos os Pedidos")
        cols = ["Cliente","Produto","Quantidade","Data","Status"]
        df_orders = pd.DataFrame(orders_data, columns=cols)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Baixar Pedidos CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar ou Deletar Pedido")
            df_orders["unique_key"] = df_orders.apply(
                lambda row: f"{row['Cliente']}|{row['Produto']}|{row['Data'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_orders["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Pedido", [""]+unique_keys)
            if selected_key:
                match = df_orders[df_orders["unique_key"] == selected_key]
                if len(match) > 1:
                    st.warning("Múltiplos registros com mesma chave.")
                else:
                    sel = match.iloc[0]
                    original_client = sel["Cliente"]
                    original_product = sel["Produto"]
                    original_qty = sel["Quantidade"]
                    original_date = sel["Data"]
                    original_status = sel["Status"]

                    with st.form(key='edit_order_form'):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            edit_prod = st.selectbox(
                                "Produto", product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))
                        with col3:
                            status_opts = [
                                "em aberto","Received - Debited","Received - Credit","Received - Pix","Received - Cash"
                            ]
                            if original_status in status_opts:
                                s_index = status_opts.index(original_status)
                            else:
                                s_index = 0
                            edit_status = st.selectbox("Status", status_opts, index=s_index)
                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_btn = st.form_submit_button("Atualizar Pedido")
                        with col_del:
                            delete_btn = st.form_submit_button("Deletar Pedido")

                    if delete_btn:
                        q_del = """
                            DELETE FROM public.tb_pedido
                            WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                        """
                        if run_query(q_del, (original_client, original_product, original_date), commit=True):
                            st.success("Pedido deletado!")
                            refresh_data()
                        else:
                            st.error("Falha ao deletar pedido.")

                    if update_btn:
                        q_upd = """
                            UPDATE public.tb_pedido
                            SET "Produto"=%s,"Quantidade"=%s,status=%s
                            WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                        """
                        if run_query(q_upd, (
                            edit_prod, edit_qty, edit_status,
                            original_client, original_product, original_date
                        ), commit=True):
                            st.success("Pedido atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar pedido.")
    else:
        st.info("Nenhum pedido encontrado.")


def products_page():
    st.title("Products")
    st.subheader("Adicionar novo produto")

    with st.form(key='product_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            supplier = st.text_input("Fornecedor")
        with col2:
            product = st.text_input("Produto")
        with col3:
            quantity = st.number_input("Quantidade", min_value=1, step=1)
        with col4:
            unit_value = st.number_input("Valor Unitário", min_value=0.0, step=0.01, format="%.2f")
        creation_date = st.date_input("Data de Criação", value=date.today())
        submit_prod = st.form_submit_button("Inserir Produto")

    if submit_prod:
        if supplier and product and quantity > 0 and unit_value >= 0:
            total_value = quantity * unit_value
            q_ins = """
                INSERT INTO public.tb_products
                (supplier,product,quantity,unit_value,total_value,creation_date)
                VALUES (%s,%s,%s,%s,%s,%s)
            """
            if run_query(q_ins, (supplier, product, quantity, unit_value, total_value, creation_date), commit=True):
                st.success("Produto adicionado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao adicionar produto.")
        else:
            st.warning("Preencha todos os campos.")

    products_data = st.session_state.data.get("products", [])
    if products_data:
        st.subheader("Todos os Produtos")
        cols = ["Supplier","Product","Quantity","Unit Value","Total Value","Creation Date"]
        df_prod = pd.DataFrame(products_data, columns=cols)
        st.dataframe(df_prod, use_container_width=True)
        download_df_as_csv(df_prod, "products.csv", label="Baixar Produtos CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar / Deletar Produto")
            df_prod["unique_key"] = df_prod.apply(
                lambda row: f"{row['Supplier']}|{row['Product']}|{row['Creation Date'].strftime('%Y-%m-%d')}",
                axis=1
            )
            unique_keys = df_prod["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Produto:", [""]+unique_keys)
            if selected_key:
                match = df_prod[df_prod["unique_key"] == selected_key]
                if len(match) > 1:
                    st.warning("Múltiplos produtos com a mesma chave.")
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
                            edit_supplier = st.text_input("Fornecedor", value=original_supplier)
                        with col2:
                            edit_product = st.text_input("Produto", value=original_product)
                        with col3:
                            edit_quantity = st.number_input(
                                "Quantidade", min_value=1, step=1, value=int(original_quantity)
                            )
                        with col4:
                            edit_unit_val = st.number_input(
                                "Valor Unitário", min_value=0.0, step=0.01, format="%.2f",
                                value=float(original_unit_value)
                            )
                        edit_creation_date = st.date_input("Data de Criação", value=original_creation_date)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_btn = st.form_submit_button("Atualizar Produto")
                        with col_del:
                            delete_btn = st.form_submit_button("Deletar Produto")

                    if update_btn:
                        edit_total_val = edit_quantity * edit_unit_val
                        q_upd = """
                            UPDATE public.tb_products
                            SET supplier=%s,product=%s,quantity=%s,unit_value=%s,
                                total_value=%s,creation_date=%s
                            WHERE supplier=%s AND product=%s AND creation_date=%s
                        """
                        if run_query(q_upd, (
                            edit_supplier, edit_product, edit_quantity, edit_unit_val, edit_total_val,
                            edit_creation_date, original_supplier, original_product, original_creation_date
                        ), commit=True):
                            st.success("Produto atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar produto.")

                    if delete_btn:
                        confirm = st.checkbox("Confirma a exclusão deste produto?")
                        if confirm:
                            q_del = """
                                DELETE FROM public.tb_products
                                WHERE supplier=%s AND product=%s AND creation_date=%s
                            """
                            if run_query(q_del, (
                                original_supplier, original_product, original_creation_date
                            ), commit=True):
                                st.success("Produto deletado!")
                                refresh_data()
                            else:
                                st.error("Falha ao deletar produto.")
    else:
        st.info("Nenhum produto encontrado.")


def stock_page():
    st.title("Stock")
    st.subheader("Registrar novo movimento de estoque")

    product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
    product_list = [row[0] for row in product_data] if product_data else ["No products"]

    with st.form(key='stock_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            product = st.selectbox("Produto", product_list)
        with col2:
            quantity = st.number_input("Quantidade", min_value=1, step=1)
        with col3:
            transaction = st.selectbox("Tipo de Transação", ["Entrada","Saída"])
        with col4:
            date_input = st.date_input("Data", value=datetime.now().date())
        submit_st = st.form_submit_button("Registrar")

    if submit_st:
        if product and quantity > 0:
            current_datetime = datetime.combine(date_input, datetime.min.time())
            q_ins = """
                INSERT INTO public.tb_estoque("Produto","Quantidade","Transação","Data")
                VALUES(%s,%s,%s,%s)
            """
            if run_query(q_ins, (product, quantity, transaction, current_datetime), commit=True):
                st.success("Movimentação de estoque registrada!")
                refresh_data()
            else:
                st.error("Falha ao registrar estoque.")
        else:
            st.warning("Selecione produto e quantidade > 0.")

    stock_data = st.session_state.data.get("stock", [])
    if stock_data:
        st.subheader("Movimentações de Estoque")
        cols = ["Produto","Quantidade","Transação","Data"]
        df_stock = pd.DataFrame(stock_data, columns=cols)
        st.dataframe(df_stock, use_container_width=True)
        download_df_as_csv(df_stock, "stock.csv", label="Baixar Stock CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar/Deletar Registro de Estoque")
            df_stock["unique_key"] = df_stock.apply(
                lambda row: f"{row['Produto']}|{row['Transação']}|{row['Data'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_stock["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Registro", [""]+unique_keys)
            if selected_key:
                match = df_stock[df_stock["unique_key"] == selected_key]
                if len(match) > 1:
                    st.warning("Múltiplos registros com mesma chave.")
                else:
                    sel = match.iloc[0]
                    original_product = sel["Produto"]
                    original_qty = sel["Quantidade"]
                    original_trans = sel["Transação"]
                    original_date = sel["Data"]

                    with st.form(key='edit_stock_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_prod = st.selectbox(
                                "Produto", product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))
                        with col3:
                            edit_trans = st.selectbox(
                                "Tipo", ["Entrada","Saída"],
                                index=["Entrada","Saída"].index(original_trans)
                                if original_trans in ["Entrada","Saída"] else 0
                            )
                        with col4:
                            edit_date = st.date_input("Data", value=original_date.date())

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_btn = st.form_submit_button("Atualizar")
                        with col_del:
                            delete_btn = st.form_submit_button("Deletar")

                    if update_btn:
                        new_dt = datetime.combine(edit_date, datetime.min.time())
                        q_upd = """
                            UPDATE public.tb_estoque
                            SET "Produto"=%s,"Quantidade"=%s,"Transação"=%s,"Data"=%s
                            WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                        """
                        if run_query(q_upd, (
                            edit_prod, edit_qty, edit_trans, new_dt,
                            original_product, original_trans, original_date
                        ), commit=True):
                            st.success("Estoque atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar estoque.")

                    if delete_btn:
                        q_del = """
                            DELETE FROM public.tb_estoque
                            WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                        """
                        if run_query(q_del, (original_product, original_trans, original_date), commit=True):
                            st.success("Registro deletado!")
                            refresh_data()
                        else:
                            st.error("Falha ao deletar registro.")
    else:
        st.info("Nenhuma movimentação de estoque encontrada.")


def clients_page():
    st.title("Clients")
    st.subheader("Registrar Novo Cliente")

    with st.form(key='client_form'):
        nome_completo = st.text_input("Nome Completo")
        submit_client = st.form_submit_button("Registrar Cliente")

    if submit_client:
        if nome_completo:
            data_nasc = date(2000,1,1)
            genero = "Other"
            telefone = "0000-0000"
            endereco = "Endereço padrão"
            unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
            email = f"{nome_completo.replace(' ','_').lower()}_{unique_id}@example.com"

            q_ins = """
                INSERT INTO public.tb_clientes(nome_completo,data_nascimento,genero,telefone,
                                               email,endereco,data_cadastro)
                VALUES(%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            """
            if run_query(q_ins, (nome_completo, data_nasc, genero, telefone, email, endereco), commit=True):
                st.success("Cliente registrado!")
                refresh_data()
            else:
                st.error("Falha ao registrar cliente.")
        else:
            st.warning("Informe o nome completo.")

    clients_data = run_query("SELECT nome_completo,email FROM public.tb_clientes ORDER BY data_cadastro DESC;")
    if clients_data:
        st.subheader("Todos os Clientes")
        cols = ["Full Name","Email"]
        df_clients = pd.DataFrame(clients_data, columns=cols)
        st.dataframe(df_clients[["Full Name"]], use_container_width=True)
        download_df_as_csv(df_clients, "clients.csv", label="Baixar Clients CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar / Deletar Cliente")
            client_display = [""] + [f"{row['Full Name']} ({row['Email']})" for _, row in df_clients.iterrows()]
            selected_display = st.selectbox("Selecione Cliente:", client_display)
            if selected_display:
                try:
                    original_name, original_email = selected_display.split(" (")
                    original_email = original_email.rstrip(")")
                except ValueError:
                    st.error("Seleção inválida.")
                    st.stop()

                sel_row = df_clients[df_clients["Email"] == original_email].iloc[0]
                with st.form(key='edit_client_form'):
                    edit_name = st.text_input("Nome Completo", value=sel_row["Full Name"])
                    col_upd, col_del = st.columns(2)
                    with col_upd:
                        update_btn = st.form_submit_button("Atualizar Cliente")
                    with col_del:
                        delete_btn = st.form_submit_button("Deletar Cliente")

                if update_btn:
                    if edit_name:
                        q_upd = """
                            UPDATE public.tb_clientes
                            SET nome_completo=%s
                            WHERE email=%s
                        """
                        if run_query(q_upd, (edit_name, original_email), commit=True):
                            st.success("Cliente atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar cliente.")
                    else:
                        st.warning("Informe o nome completo.")

                if delete_btn:
                    q_del = "DELETE FROM public.tb_clientes WHERE email=%s"
                    if run_query(q_del, (original_email,), commit=True):
                        st.success("Cliente deletado!")
                        refresh_data()
                        st.experimental_rerun()
                    else:
                        st.error("Falha ao deletar cliente.")
    else:
        st.info("Nenhum cliente encontrado.")


def process_payment(client, payment_status):
    query = """
        UPDATE public.tb_pedido
        SET status=%s,"Data"=CURRENT_TIMESTAMP
        WHERE "Cliente"=%s AND status='em aberto'
    """
    if run_query(query, (payment_status, client), commit=True):
        st.success(f"Status atualizado para: {payment_status}")
        refresh_data()
    else:
        st.error("Falha ao atualizar status.")


def generate_invoice_for_printer(df: pd.DataFrame):
    company = "Boituva Beach Club"
    address = "Avenida do Trabalhador 1879"
    city = "Boituva - SP 18552-100"
    cnpj = "05.365.434/0001-09"
    phone = "(13) 99154-5481"

    invoice = []
    invoice.append("==================================================")
    invoice.append("                      NOTA FISCAL                ")
    invoice.append("==================================================")
    invoice.append(f"Empresa: {company}")
    invoice.append(f"Endereço: {address}")
    invoice.append(f"Cidade: {city}")
    invoice.append(f"CNPJ: {cnpj}")
    invoice.append(f"Telefone: {phone}")
    invoice.append("--------------------------------------------------")
    invoice.append("DESCRIÇÃO             QTD     TOTAL")
    invoice.append("--------------------------------------------------")

    grouped_df = df.groupby('Produto').agg({'Quantidade':'sum','total':'sum'}).reset_index()
    total_general = 0
    for _, row in grouped_df.iterrows():
        description = f"{row['Produto'][:20]:<20}"
        quantity = f"{int(row['Quantidade']):>5}"
        total_item = row['total']
        total_general += total_item
        total_formatted = format_currency(total_item)
        invoice.append(f"{description} {quantity} {total_formatted}")

    invoice.append("--------------------------------------------------")
    invoice.append(f"{'TOTAL GERAL:':>30} {format_currency(total_general):>10}")
    invoice.append("==================================================")
    invoice.append("OBRIGADO PELA SUA PREFERÊNCIA!")
    invoice.append("==================================================")

    st.text("\n".join(invoice))


def invoice_page():
    st.title("Nota Fiscal")
    open_clients_query = 'SELECT DISTINCT "Cliente" FROM public.vw_pedido_produto WHERE status=%s'
    open_clients = run_query(open_clients_query, ('em aberto',))
    client_list = [row[0] for row in open_clients] if open_clients else []
    selected_client = st.selectbox("Selecione um Cliente", [""]+client_list)

    if selected_client:
        invoice_query = """
            SELECT "Produto","Quantidade","total"
            FROM public.vw_pedido_produto
            WHERE "Cliente"=%s AND status=%s
        """
        invoice_data = run_query(invoice_query, (selected_client, 'em aberto'))
        if invoice_data:
            df = pd.DataFrame(invoice_data, columns=["Produto","Quantidade","total"])
            generate_invoice_for_printer(df)

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("Debit"):
                    process_payment(selected_client, "Received - Debited")
            with col2:
                if st.button("Credit"):
                    process_payment(selected_client, "Received - Credit")
            with col3:
                if st.button("Pix"):
                    process_payment(selected_client, "Received - Pix")
            with col4:
                if st.button("Cash"):
                    process_payment(selected_client, "Received - Cash")
        else:
            st.info("Não há pedidos em aberto para esse cliente.")
    else:
        st.warning("Selecione um cliente.")


def menu_page():
    st.title("Cardápio")
    categories = run_query("SELECT DISTINCT categoria FROM public.tb_products ORDER BY categoria;")
    category_list = [row[0] for row in categories] if categories else []

    selected_category = st.selectbox("Selecione a Categoria", [""]+category_list)
    if selected_category:
        query = "SELECT product,description,price FROM public.tb_products WHERE categoria=%s;"
        products = run_query(query, (selected_category,))
        if products:
            for prod in products:
                st.subheader(prod[0])
                st.write(f"Descrição: {prod[1]}")
                st.write(f"Preço: {format_currency(prod[2])}")
        else:
            st.warning("Nenhum produto encontrado nessa categoria.")


def settings_page():
    st.title("Configurações e Ajustes")
    st.subheader("Ajustes de Conta")
    if 'username' in st.session_state:
        new_username = st.text_input("Nome de Usuário", st.session_state.username)
        if st.button("Salvar Nome"):
            st.session_state.username = new_username
            st.success("Nome atualizado!")

    st.subheader("Preferências do App")
    theme_choice = st.radio("Escolha o tema", ("Claro","Escuro"))
    if st.button("Salvar Preferências"):
        st.session_state.theme = theme_choice
        st.success("Preferências salvas!")


def loyalty_program_page():
    st.title("Programa de Fidelidade")
    st.subheader("Acumule pontos a cada compra!")
    if 'points' not in st.session_state:
        st.session_state.points = 0

    points_earned = st.number_input("Pontos a adicionar", min_value=0, step=1)
    if st.button("Adicionar Pontos"):
        st.session_state.points += points_earned
        st.success(f"Pontos adicionados! Total: {st.session_state.points}")

    if st.button("Resgatar Prêmio"):
        if st.session_state.points >= 100:
            st.session_state.points -= 100
            st.success("Prêmio resgatado!")
        else:
            st.error("Pontos insuficientes.")


def events_calendar_page():
    st.title("Calendário de Eventos")

    def fetch_events(start_d, end_d):
        return pd.DataFrame({
            "Nome do Evento": ["Torneio Beach Tennis","Aula Estratégia","Noite Integração"],
            "Data": [start_d + timedelta(days=i) for i in range(3)],
            "Descrição": [
                "Torneio aberto com premiação.",
                "Aula focada em técnicas avançadas.",
                "Encontro social do clube."
            ],
            "Inscrição Aberta": [True, True, False]
        })

    today = datetime.now().date()
    start_date = st.date_input("De:", today)
    end_date = st.date_input("Até:", today+timedelta(days=30))

    if start_date > end_date:
        st.error("Data inicial não pode ser maior que a final.")
    else:
        events = fetch_events(start_date, end_date)
        if not events.empty:
            for _, row in events.iterrows():
                st.subheader(f"{row['Nome do Evento']} ({row['Data'].strftime('%d/%m/%Y')})")
                st.write(f"Descrição: {row['Descrição']}")
                if row['Inscrição Aberta']:
                    if st.button(f"Inscrever-se: {row['Nome do Evento']}", key=row['Nome do Evento']):
                        st.success(f"Inscrito em {row['Nome do Evento']}!")
                else:
                    st.info("Inscrições encerradas.")
        else:
            st.info("Nenhum evento no período.")


###############################################################################
#                             BACKUP (ADMIN)
###############################################################################
def export_table_to_csv(table_name):
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql_query(f"SELECT * FROM {table_name};", conn)
            csv_data = df.to_csv(index=False)
            st.download_button(
                label=f"Baixar {table_name} CSV",
                data=csv_data,
                file_name=f"{table_name}.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Erro ao exportar {table_name}: {e}")
        finally:
            conn.close()


def backup_all_tables(tables):
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
                    label="Download All Tables as CSV",
                    data=csv_data,
                    file_name="all_tables_backup.csv",
                    mime="text/csv"
                )
            else:
                st.warning("Nenhum dado encontrado.")
        except Exception as e:
            st.error(f"Erro ao exportar todas as tabelas: {e}")
        finally:
            conn.close()


def perform_backup():
    st.header("Sistema de Backup")
    st.write("Clique para baixar backups das tabelas.")
    tables = ["tb_pedido","tb_products","tb_clientes","tb_estoque"]
    if st.button("Download All Tables"):
        backup_all_tables(tables)
    for t in tables:
        export_table_to_csv(t)


def admin_backup_section():
    if st.session_state.get("username") == "admin":
        perform_backup()
    else:
        st.warning("Acesso restrito para administradores.")


###############################################################################
#                                LOGIN PAGE
###############################################################################
def login_page():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 80px;
            padding-bottom: 80px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    logo_url = "https://res.cloudinary.com/lptennis/image/upload/v1657233475/kyz4k7fcptxt7x7mu9qu.jpg"
    try:
        resp = requests.get(logo_url)
        resp.raise_for_status()
        logo = Image.open(BytesIO(resp.content))
        st.image(logo, use_column_width=False)
    except requests.exceptions.RequestException:
        st.error("Falha ao carregar logo.")

    st.title("Beach Club - Login")
    with st.form(key='login_form'):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        subm = st.form_submit_button("Entrar")

    if subm:
        creds = st.secrets["credentials"]
        if username == creds["admin_username"] and password == creds["admin_password"]:
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.success("Login como administrador!")
        elif username == creds["caixa_username"] and password == creds["caixa_password"]:
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.success("Login como caixa!")
        else:
            st.error("Usuário ou senha incorretos.")


###############################################################################
#                            INICIALIZAÇÃO E MAIN
###############################################################################
def initialize_session_state():
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False


def apply_custom_css():
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
    with st.sidebar:
        st.title("Boituva Beach Club 🎾")
        selected = option_menu(
            "Menu Principal",
            [
                "Home","Orders","Products","Stock","Clients",
                "Nota Fiscal","Backup","Cardápio",
                "Configurações e Ajustes","Programa de Fidelidade",
                "Calendário de Eventos"
            ],
            icons=[
                "house","file-text","box","list-task","layers",
                "receipt","cloud-upload","list","gear","gift","calendar"
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


def main():
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
    elif selected_page == "Nota Fiscal":
        invoice_page()
    elif selected_page == "Backup":
        admin_backup_section()
    elif selected_page == "Cardápio":
        menu_page()
    elif selected_page == "Configurações e Ajustes":
        settings_page()
    elif selected_page == "Programa de Fidelidade":
        loyalty_program_page()
    elif selected_page == "Calendário de Eventos":
        events_calendar_page()

    with st.sidebar:
        if st.button("Logout"):
            for key in ["home_page_initialized"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.logged_in = False
            st.success("Desconectado com sucesso!")
            st.experimental_rerun()


if __name__ == "__main__":
    main()
