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
    Formata um valor em moeda brasileira (ex: 1234.56 -> 'R$ 1.234,56').
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Disponibiliza botão de download CSV para um DataFrame.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    """
    Disponibiliza botão de download Excel para um DataFrame.
    """
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


def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    """
    Disponibiliza botão de download JSON para um DataFrame.
    """
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")


def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    """
    Disponibiliza botão de download HTML para um DataFrame.
    """
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")


def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    """
    Disponibiliza botão de download Parquet para um DataFrame.
    """
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
    # Cabeçalhos
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()
    # Conteúdo
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()
    return pdf.output(dest='S')


def upload_pdf_to_fileio(pdf_bytes: bytes) -> str:
    """
    Faz upload de um PDF para file.io, retorna o link se sucesso.
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
                st.error("Falha ao fazer upload (file.io não retornou sucesso).")
                return ""
        else:
            st.error("Erro ao conectar com file.io.")
            return ""
    except Exception as e:
        st.error(f"Erro ao fazer upload do arquivo: {e}")
        return ""


###############################################################################
#                               TWILIO (WHATSAPP)
###############################################################################
def send_whatsapp(recipient_number: str, media_url: str = None):
    """
    Envia WhatsApp usando Twilio. 
    - recipient_number: string sem +, ex: '5511999999999'
    - media_url: se fornecido, envia mensagem com mídia (PDF ou imagem).
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
@st.cache_resource
def get_db_connection():
    """
    Cria conexão PostgreSQL usando st.secrets["db"].
    Retorna None se não conseguir conectar.
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
    Executa SQL. Se commit=True, faz INSERT/UPDATE/DELETE; senão, SELECT.
    Evita rollback caso a conexão esteja fechada.
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
        if conn and not conn.closed:
            conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return None
    finally:
        conn.close()


###############################################################################
#                         CARREGAMENTO DE DADOS (CACHE)
###############################################################################
@st.cache_data
def load_all_data():
    """
    Carrega dados principais do banco para exibir em várias páginas.
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
    Limpa cache e recarrega data.
    """
    load_all_data.clear()
    st.session_state.data = load_all_data()


###############################################################################
#                           PÁGINAS DO APLICATIVO
###############################################################################
def home_page():
    """
    Página Home. Exibe resumo de pedidos em aberto e, se admin, mostra 'Stock vs Orders'.
    """
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

    notification_placeholder = st.empty()
    client_count_query = """
        SELECT COUNT(DISTINCT "Cliente") AS client_count
        FROM public.tb_pedido
        WHERE status = %s;
    """
    client_count = run_query(client_count_query, ('em aberto',))
    if client_count and client_count[0][0] > 0:
        notification_placeholder.success(f"Há {client_count[0][0]} clientes com pedidos em aberto!")
    else:
        notification_placeholder.info("Nenhum cliente com pedido em aberto no momento.")

    # Se for admin, exibe mais informações
    if st.session_state.get("username") == "admin":
        st.markdown("**Open Orders Summary**")
        open_orders_query = """
            SELECT "Cliente", SUM("total") AS Total
            FROM public.vw_pedido_produto
            WHERE status = %s
            GROUP BY "Cliente"
            ORDER BY "Cliente" DESC
        """
        open_orders_data = run_query(open_orders_query, ('em aberto',))
        if open_orders_data:
            df_open_orders = pd.DataFrame(open_orders_data, columns=["Client", "Total"])
            total_open = df_open_orders["Total"].sum()
            df_open_orders["Total_display"] = df_open_orders["Total"].apply(format_currency)
            st.table(df_open_orders[["Client", "Total_display"]])
            st.markdown(f"**Total Geral (Open Orders):** {format_currency(total_open)}")
        else:
            st.info("Nenhum pedido em aberto encontrado.")

        st.markdown("**Stock vs. Orders Summary**")
        try:
            stock_vs_orders_query = """
                SELECT product, stock_quantity, orders_quantity, total_in_stock
                FROM public.vw_stock_vs_orders_summary
            """
            stock_vs_orders_data = run_query(stock_vs_orders_query)
            if stock_vs_orders_data:
                df_stock_vs_orders = pd.DataFrame(
                    stock_vs_orders_data,
                    columns=["Product","Stock_Quantity","Orders_Quantity","Total_in_Stock"]
                )
                df_stock_vs_orders.sort_values("Total_in_Stock", ascending=False, inplace=True)
                df_display = df_stock_vs_orders[["Product","Total_in_Stock"]]
                st.table(df_display)

                total_stock_value = int(df_stock_vs_orders["Total_in_Stock"].sum())
                st.markdown(f"**Total Geral (Stock vs. Orders):** {total_stock_value}")

                # Gerar PDF
                pdf_bytes = convert_df_to_pdf(df_stock_vs_orders)
                st.subheader("Baixar PDF 'Stock vs Orders'")
                st.download_button(
                    label="Baixar PDF",
                    data=pdf_bytes,
                    file_name="stock_vs_orders_summary.pdf",
                    mime="application/pdf"
                )

                # Exemplo de envio via WhatsApp
                st.subheader("Enviar esse PDF via WhatsApp")
                phone_number = st.text_input("Número (ex: 5511999999999)", key="pdf_whatsapp")
                if st.button("Upload e Enviar WhatsApp"):
                    link = upload_pdf_to_fileio(pdf_bytes)
                    if link and phone_number:
                        send_whatsapp(phone_number, media_url=link)
                    else:
                        st.warning("É preciso indicar o número e ter link válido do arquivo.")
            else:
                st.info("View 'vw_stock_vs_orders_summary' está vazia ou não existe.")
        except Exception as e:
            st.error(f"Erro ao gerar o resumo Stock vs. Orders: {e}")


def orders_page():
    """
    Página Orders: registra e gerencia pedidos.
    """
    st.title("Orders")
    st.subheader("Registrar novo pedido")

    product_data = st.session_state.data.get("products", [])
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products available"]

    with st.form(key='order_form'):
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo;')
        customer_list = [""] + [row[0] for row in clientes] if clientes else []
        col1, col2, col3 = st.columns(3)
        with col1:
            customer_name = st.selectbox("Cliente", customer_list, index=0)
        with col2:
            product = st.selectbox("Produto", product_list, index=0)
        with col3:
            quantity = st.number_input("Quantidade", min_value=1, step=1)
        submit_button = st.form_submit_button(label="Registrar Pedido")

    if submit_button:
        if customer_name and product and quantity > 0:
            query = """
            INSERT INTO public.tb_pedido ("Cliente","Produto","Quantidade","Data",status)
            VALUES (%s, %s, %s, %s, 'em aberto')
            """
            timestamp = datetime.now()
            success = run_query(query, (customer_name, product, quantity, timestamp), commit=True)
            if success:
                st.success("Pedido registrado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao registrar o pedido.")
        else:
            st.warning("Preencha todos os campos corretamente.")

    # Lista todos os pedidos
    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("Todos os Pedidos")
        columns = ["Cliente","Produto","Quantidade","Data","Status"]
        df_orders = pd.DataFrame(orders_data, columns=columns)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Baixar Pedidos CSV")

        # Se admin, permite editar/deletar
        if st.session_state.get("username") == "admin":
            st.subheader("Editar/Deletar Pedido Existente")
            df_orders["unique_key"] = df_orders.apply(
                lambda row: f"{row['Cliente']}|{row['Produto']}|{row['Data'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_orders["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Pedido", [""] + unique_keys)
            if selected_key:
                matching_rows = df_orders[df_orders["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Múltiplos pedidos com mesma key. Selecione outro.")
                else:
                    sel = matching_rows.iloc[0]
                    original_client = sel["Cliente"]
                    original_product = sel["Produto"]
                    original_quantity = sel["Quantidade"]
                    original_date = sel["Data"]
                    original_status = sel["Status"]

                    with st.form(key='edit_order_form'):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            edit_product = st.selectbox(
                                "Produto", product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input("Quantidade", min_value=1, step=1, value=int(original_quantity))
                        with col3:
                            edit_status_list = [
                                "em aberto","Received - Debited","Received - Credit","Received - Pix","Received - Cash"
                            ]
                            if original_status in edit_status_list:
                                edit_status_index = edit_status_list.index(original_status)
                            else:
                                edit_status_index = 0
                            edit_status = st.selectbox("Status", edit_status_list, index=edit_status_index)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Atualizar Pedido")
                        with col_del:
                            delete_button = st.form_submit_button(label="Deletar Pedido")

                    if delete_button:
                        delete_query = """
                        DELETE FROM public.tb_pedido
                        WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                        """
                        success = run_query(delete_query, (original_client, original_product, original_date), commit=True)
                        if success:
                            st.success("Pedido excluído com sucesso!")
                            refresh_data()
                        else:
                            st.error("Falha ao excluir pedido.")

                    if update_button:
                        update_query = """
                        UPDATE public.tb_pedido
                        SET "Produto"=%s,"Quantidade"=%s,status=%s
                        WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                        """
                        success = run_query(update_query, (
                            edit_product, edit_quantity, edit_status,
                            original_client, original_product, original_date
                        ), commit=True)
                        if success:
                            st.success("Pedido atualizado com sucesso!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar pedido.")
    else:
        st.info("Nenhum pedido encontrado.")


def products_page():
    """
    Página Products: cadastra/edita/deleta produtos (ADMIN).
    """
    st.title("Products")
    st.subheader("Adicionar novo produto")

    with st.form(key='product_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            supplier = st.text_input("Fornecedor", max_chars=100)
        with col2:
            product = st.text_input("Produto", max_chars=100)
        with col3:
            quantity = st.number_input("Quantidade", min_value=1, step=1)
        with col4:
            unit_value = st.number_input("Valor Unitário", min_value=0.0, step=0.01, format="%.2f")
        creation_date = st.date_input("Data de Criação", value=date.today())
        submit_product = st.form_submit_button(label="Inserir Produto")

    if submit_product:
        if supplier and product and quantity > 0 and unit_value >= 0:
            query = """
            INSERT INTO public.tb_products 
            (supplier,product,quantity,unit_value,total_value,creation_date)
            VALUES (%s,%s,%s,%s,%s,%s)
            """
            total_value = quantity * unit_value
            success = run_query(query, (supplier, product, quantity, unit_value, total_value, creation_date), commit=True)
            if success:
                st.success("Produto adicionado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao adicionar produto.")
        else:
            st.warning("Preencha todos os campos corretamente.")

    products_data = st.session_state.data.get("products", [])
    if products_data:
        st.subheader("Todos os Produtos")
        columns = ["Supplier","Product","Quantity","Unit Value","Total Value","Creation Date"]
        df_products = pd.DataFrame(products_data, columns=columns)
        st.dataframe(df_products, use_container_width=True)
        download_df_as_csv(df_products, "products.csv", label="Baixar Produtos CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar/Deletar Produto Existente")
            df_products["unique_key"] = df_products.apply(
                lambda row: f"{row['Supplier']}|{row['Product']}|{row['Creation Date'].strftime('%Y-%m-%d')}",
                axis=1
            )
            unique_keys = df_products["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Produto", [""] + unique_keys)
            if selected_key:
                matching_rows = df_products[df_products["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Múltiplos produtos com mesma chave.")
                else:
                    row_sel = matching_rows.iloc[0]
                    original_supplier = row_sel["Supplier"]
                    original_product = row_sel["Product"]
                    original_quantity = row_sel["Quantity"]
                    original_unit_value = row_sel["Unit Value"]
                    original_creation_date = row_sel["Creation Date"]

                    with st.form(key='edit_product_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_supplier = st.text_input("Fornecedor", value=original_supplier, max_chars=100)
                        with col2:
                            edit_product = st.text_input("Produto", value=original_product, max_chars=100)
                        with col3:
                            edit_quantity = st.number_input("Quantidade", min_value=1, step=1, value=int(original_quantity))
                        with col4:
                            edit_unit_value = st.number_input(
                                "Valor Unitário", min_value=0.0, step=0.01, format="%.2f",
                                value=float(original_unit_value)
                            )
                        edit_creation_date = st.date_input("Data de Criação", value=original_creation_date)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Atualizar Produto")
                        with col_del:
                            delete_button = st.form_submit_button(label="Deletar Produto")

                    if update_button:
                        edit_total_value = edit_quantity * edit_unit_value
                        update_query = """
                        UPDATE public.tb_products
                        SET supplier=%s,product=%s,quantity=%s,unit_value=%s,
                            total_value=%s,creation_date=%s
                        WHERE supplier=%s AND product=%s AND creation_date=%s
                        """
                        success = run_query(update_query, (
                            edit_supplier, edit_product, edit_quantity, edit_unit_value, edit_total_value,
                            edit_creation_date, original_supplier, original_product, original_creation_date
                        ), commit=True)
                        if success:
                            st.success("Produto atualizado com sucesso!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar produto.")

                    if delete_button:
                        confirm = st.checkbox("Tem certeza que deseja deletar este produto?")
                        if confirm:
                            delete_query = """
                            DELETE FROM public.tb_products
                            WHERE supplier=%s AND product=%s AND creation_date=%s
                            """
                            success = run_query(delete_query, (
                                original_supplier, original_product, original_creation_date
                            ), commit=True)
                            if success:
                                st.success("Produto deletado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao deletar produto.")
    else:
        st.info("Nenhum produto encontrado.")


def stock_page():
    """
    Página Stock: registrar entradas/saídas de estoque.
    """
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
        submit_stock = st.form_submit_button(label="Registrar")

    if submit_stock:
        if product and quantity > 0:
            current_datetime = datetime.combine(date_input, datetime.min.time())
            query = """
            INSERT INTO public.tb_estoque ("Produto","Quantidade","Transação","Data")
            VALUES (%s,%s,%s,%s)
            """
            success = run_query(query, (product, quantity, transaction, current_datetime), commit=True)
            if success:
                st.success("Movimentação de estoque registrada!")
                refresh_data()
            else:
                st.error("Falha ao registrar estoque.")
        else:
            st.warning("Selecione um produto e informe quantidade > 0.")

    stock_data = st.session_state.data.get("stock", [])
    if stock_data:
        st.subheader("Movimentações de Estoque")
        columns = ["Produto","Quantidade","Transação","Data"]
        df_stock = pd.DataFrame(stock_data, columns=columns)
        st.dataframe(df_stock, use_container_width=True)
        download_df_as_csv(df_stock, "stock.csv", label="Baixar Stock CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar/Deletar Registros de Estoque")
            df_stock["unique_key"] = df_stock.apply(
                lambda row: f"{row['Produto']}|{row['Transação']}|{row['Data'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_stock["unique_key"].unique().tolist()
            selected_key = st.selectbox("Selecione Registro:", [""] + unique_keys)
            if selected_key:
                matching_rows = df_stock[df_stock["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Múltiplos registros com a mesma key.")
                else:
                    sel = matching_rows.iloc[0]
                    original_product = sel["Produto"]
                    original_quantity = sel["Quantidade"]
                    original_transaction = sel["Transação"]
                    original_date = sel["Data"]

                    with st.form(key='edit_stock_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_product = st.selectbox(
                                "Produto", product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input("Quantidade", min_value=1, step=1, value=int(original_quantity))
                        with col3:
                            edit_transaction = st.selectbox(
                                "Tipo",
                                ["Entrada","Saída"],
                                index=["Entrada","Saída"].index(original_transaction)
                                if original_transaction in ["Entrada","Saída"] else 0
                            )
                        with col4:
                            edit_date = st.date_input("Data", value=original_date.date())

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Atualizar")
                        with col_del:
                            delete_button = st.form_submit_button(label="Deletar")

                    if update_button:
                        edit_datetime = datetime.combine(edit_date, datetime.min.time())
                        update_query = """
                        UPDATE public.tb_estoque
                        SET "Produto"=%s,"Quantidade"=%s,"Transação"=%s,"Data"=%s
                        WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                        """
                        success = run_query(update_query, (
                            edit_product, edit_quantity, edit_transaction, edit_datetime,
                            original_product, original_transaction, original_date
                        ), commit=True)
                        if success:
                            st.success("Estoque atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar estoque.")

                    if delete_button:
                        delete_query = """
                        DELETE FROM public.tb_estoque
                        WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                        """
                        success = run_query(delete_query, (
                            original_product, original_transaction, original_date
                        ), commit=True)
                        if success:
                            st.success("Registro de estoque deletado!")
                            refresh_data()
                        else:
                            st.error("Falha ao deletar registro.")
    else:
        st.info("Nenhuma movimentação de estoque encontrada.")


def clients_page():
    """
    Página Clients: cadastra e lista clientes (ADMIN pode editar/deletar).
    """
    st.title("Clients")
    st.subheader("Registrar Novo Cliente")

    with st.form(key='client_form'):
        nome_completo = st.text_input("Nome Completo", max_chars=100)
        submit_client = st.form_submit_button(label="Registrar Cliente")

    if submit_client:
        if nome_completo:
            data_nascimento = date(2000,1,1)
            genero = "Other"
            telefone = "0000-0000"
            endereco = "Endereço Padrão"
            unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
            email = f"{nome_completo.replace(' ','_').lower()}_{unique_id}@example.com"

            query = """
            INSERT INTO public.tb_clientes (nome_completo,data_nascimento,genero,telefone,
                                            email,endereco,data_cadastro)
            VALUES (%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
            """
            success = run_query(query, (nome_completo, data_nascimento, genero, telefone, email, endereco), commit=True)
            if success:
                st.success("Cliente registrado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao registrar cliente.")
        else:
            st.warning("Informe o Nome Completo.")

    clients_data = run_query("SELECT nome_completo,email FROM public.tb_clientes ORDER BY data_cadastro DESC;")
    if clients_data:
        st.subheader("Todos os Clientes")
        columns = ["Full Name","Email"]
        df_clients = pd.DataFrame(clients_data, columns=columns)
        st.dataframe(df_clients[["Full Name"]], use_container_width=True)
        download_df_as_csv(df_clients, "clients.csv", label="Baixar Clients CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Editar/Deletar Cliente Existente")
            client_display = [""] + [f"{row['Full Name']} ({row['Email']})" for _, row in df_clients.iterrows()]
            selected_display = st.selectbox("Selecione Cliente:", client_display)
            if selected_display:
                try:
                    original_name, original_email = selected_display.split(" (")
                    original_email = original_email.rstrip(")")
                except ValueError:
                    st.error("Seleção inválida.")
                    st.stop()

                selected_row = df_clients[df_clients["Email"] == original_email].iloc[0]
                with st.form(key='edit_client_form'):
                    edit_name = st.text_input("Nome Completo", value=selected_row["Full Name"], max_chars=100)
                    col_upd, col_del = st.columns(2)
                    with col_upd:
                        update_button = st.form_submit_button(label="Atualizar Cliente")
                    with col_del:
                        delete_button = st.form_submit_button(label="Deletar Cliente")

                if update_button:
                    if edit_name:
                        update_query = """
                        UPDATE public.tb_clientes
                        SET nome_completo=%s
                        WHERE email=%s
                        """
                        success = run_query(update_query, (edit_name, original_email), commit=True)
                        if success:
                            st.success("Cliente atualizado!")
                            refresh_data()
                        else:
                            st.error("Falha ao atualizar cliente.")
                    else:
                        st.warning("Informe o nome completo.")

                if delete_button:
                    delete_query = "DELETE FROM public.tb_clientes WHERE email=%s"
                    success = run_query(delete_query, (original_email,), commit=True)
                    if success:
                        st.success("Cliente deletado!")
                        refresh_data()
                        st.experimental_rerun()
                    else:
                        st.error("Falha ao deletar cliente.")
    else:
        st.info("Nenhum cliente encontrado.")


def process_payment(client, payment_status):
    """
    Atualiza status de pedidos em aberto para o método de pagamento informado.
    """
    query = """
    UPDATE public.tb_pedido
    SET status=%s,"Data"=CURRENT_TIMESTAMP
    WHERE "Cliente"=%s AND status='em aberto'
    """
    success = run_query(query, (payment_status, client), commit=True)
    if success:
        st.success(f"Status atualizado para {payment_status}")
        refresh_data()
    else:
        st.error("Falha ao atualizar status.")


def generate_invoice_for_printer(df: pd.DataFrame):
    """
    Gera um texto simulando uma Nota Fiscal.
    """
    company = "Boituva Beach Club"
    address = "Avenida do Trabalhador 1879"
    city = "Boituva - SP 18552-100"
    cnpj = "05.365.434/0001-09"
    phone = "(13) 99154-5481"

    invoice_note = []
    invoice_note.append("==================================================")
    invoice_note.append("                      NOTA FISCAL                ")
    invoice_note.append("==================================================")
    invoice_note.append(f"Empresa: {company}")
    invoice_note.append(f"Endereço: {address}")
    invoice_note.append(f"Cidade: {city}")
    invoice_note.append(f"CNPJ: {cnpj}")
    invoice_note.append(f"Telefone: {phone}")
    invoice_note.append("--------------------------------------------------")
    invoice_note.append("DESCRIÇÃO             QTD     TOTAL")
    invoice_note.append("--------------------------------------------------")

    grouped_df = df.groupby('Produto').agg({'Quantidade':'sum','total':'sum'}).reset_index()
    total_general = 0
    for _, row in grouped_df.iterrows():
        description = f"{row['Produto'][:20]:<20}"
        quantity = f"{int(row['Quantidade']):>5}"
        total_item = row['total']
        total_general += total_item
        total_formatted = format_currency(total_item)
        invoice_note.append(f"{description} {quantity} {total_formatted}")

    invoice_note.append("--------------------------------------------------")
    invoice_note.append(f"{'TOTAL GERAL:':>30} {format_currency(total_general):>10}")
    invoice_note.append("==================================================")
    invoice_note.append("OBRIGADO PELA SUA PREFERÊNCIA!")
    invoice_note.append("==================================================")

    st.text("\n".join(invoice_note))


def invoice_page():
    """
    Página de Nota Fiscal: seleciona cliente com pedido em aberto, gera nota e recebe pagamento.
    """
    st.title("Nota Fiscal")
    open_clients_query = 'SELECT DISTINCT "Cliente" FROM public.vw_pedido_produto WHERE status=%s'
    open_clients = run_query(open_clients_query, ('em aberto',))
    client_list = [row[0] for row in open_clients] if open_clients else []
    selected_client = st.selectbox("Selecione um Cliente", [""] + client_list)

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
    """
    Página de Cardápio: exibe produtos de uma dada categoria.
    """
    st.title("Cardápio")
    categories = run_query("SELECT DISTINCT categoria FROM public.tb_products ORDER BY categoria;")
    category_list = [row[0] for row in categories] if categories else []

    selected_category = st.selectbox("Selecione a Categoria", [""] + category_list)
    if selected_category:
        query = "SELECT product,description,price FROM public.tb_products WHERE categoria=%s;"
        products = run_query(query, (selected_category,))
        if products:
            for prod in products:
                st.subheader(prod[0])
                st.write(f"Descrição: {prod[1]}")
                st.write(f"Preço: {format_currency(prod[2])}")
        else:
            st.warning("Nenhum produto encontrado na categoria.")


def settings_page():
    """
    Página de Configurações: altera nome de usuário, muda tema.
    """
    st.title("Configurações e Ajustes")
    st.subheader("Ajustes de Conta")

    if 'username' in st.session_state:
        new_username = st.text_input("Alterar nome de usuário", st.session_state.username)
        if st.button("Salvar Nome de Usuário"):
            st.session_state.username = new_username
            st.success("Nome de usuário atualizado!")

    st.subheader("Preferências do Aplicativo")
    theme_choice = st.radio("Escolha o tema", ("Claro","Escuro"))
    if st.button("Salvar Preferências"):
        st.session_state.theme = theme_choice
        st.success("Preferências salvas!")


def loyalty_program_page():
    """
    Página de Programa de Fidelidade: acumula e resgata pontos.
    """
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
            st.error("Pontos insuficientes para resgate.")


def events_calendar_page():
    """
    Página de Calendário de Eventos (exemplo fictício).
    """
    st.title("Calendário de Eventos")

    def fetch_events(start_date, end_date):
        return pd.DataFrame({
            "Nome do Evento": ["Torneio de Beach Tennis", "Aula de Estratégia de Jogo", "Noite de Integração"],
            "Data": [start_date + timedelta(days=i) for i in range(3)],
            "Descrição": [
                "Torneio aberto com premiação para os três primeiros colocados.",
                "Aula com foco em técnicas avançadas de jogo.",
                "Encontro social para membros do clube."
            ],
            "Inscrição Aberta": [True, True, False]
        })

    today = datetime.now().date()
    start_date = st.date_input("De:", today)
    end_date = st.date_input("Até:", today + timedelta(days=30))

    if start_date > end_date:
        st.error("Data inicial não pode ser posterior à final.")
    else:
        events = fetch_events(start_date, end_date)
        if not events.empty:
            for _, row in events.iterrows():
                st.subheader(f"{row['Nome do Evento']} ({row['Data'].strftime('%d/%m/%Y')})")
                st.write(f"Descrição: {row['Descrição']}")
                if row['Inscrição Aberta']:
                    if st.button(f"Inscrever-se: {row['Nome do Evento']}", key=row['Nome do Evento']):
                        st.success(f"Inscrição confirmada para {row['Nome do Evento']}!")
                else:
                    st.info("Inscrições encerradas.")
        else:
            st.info("Nenhum evento programado nesse período.")


###############################################################################
#                             BACKUP (ADMIN)
###############################################################################
def export_table_to_csv(table_name):
    """
    Exporta o conteúdo de uma tabela para CSV via botão de download.
    """
    conn = get_db_connection()
    if conn:
        try:
            query = f"SELECT * FROM {table_name};"
            df = pd.read_sql_query(query, conn)
            csv_data = df.to_csv(index=False)
            st.download_button(
                label=f"Baixar {table_name} em CSV",
                data=csv_data,
                file_name=f"{table_name}.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Erro ao exportar {table_name}: {e}")
        finally:
            conn.close()


def backup_all_tables(tables):
    """
    Concatena dados de múltiplas tabelas e oferece único download CSV.
    """
    conn = get_db_connection()
    if conn:
        try:
            all_frames = []
            for table in tables:
                df = pd.read_sql_query(f"SELECT * FROM {table};", conn)
                df["table_name"] = table
                all_frames.append(df)
            if all_frames:
                combined_csv = pd.concat(all_frames, ignore_index=True)
                csv_data = combined_csv.to_csv(index=False)
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
    """
    Exibe página de backup, com opções para cada tabela.
    """
    st.header("Sistema de Backup")
    st.write("Clique para baixar backups das tabelas.")
    tables = ["tb_pedido","tb_products","tb_clientes","tb_estoque"]

    if st.button("Download All Tables"):
        backup_all_tables(tables)

    for table in tables:
        export_table_to_csv(table)


def admin_backup_section():
    """
    Se usuario for admin, exibe a página de backup, senão avisa.
    """
    if st.session_state.get("username") == "admin":
        perform_backup()
    else:
        st.warning("Acesso restrito a administradores.")


###############################################################################
#                                LOGIN PAGE
###############################################################################
def login_page():
    """
    Página de Login: compara usuário e senha com st.secrets["credentials"].
    """
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 60px;
            padding-bottom: 60px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    logo_url = "https://res.cloudinary.com/lptennis/image/upload/v1657233475/kyz4k7fcptxt7x7mu9qu.jpg"
    try:
        response = requests.get(logo_url)
        response.raise_for_status()
        logo = Image.open(BytesIO(response.content))
        st.image(logo, use_column_width=False)
    except requests.exceptions.RequestException:
        st.error("Falha ao carregar logotipo.")

    st.title("Beach Club - Login")
    with st.form(key='login_form'):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_login = st.form_submit_button(label="Entrar")

    if submit_login:
        credentials = st.secrets["credentials"]
        admin_username = credentials["admin_username"]
        admin_password = credentials["admin_password"]
        caixa_username = credentials["caixa_username"]
        caixa_password = credentials["caixa_password"]

        if username == admin_username and password == admin_password:
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.success("Login como administrador!")
        elif username == caixa_username and password == caixa_password:
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.success("Login como caixa!")
        else:
            st.error("Usuário ou senha incorretos.")


###############################################################################
#                           INICIALIZAÇÃO E MAIN
###############################################################################
def initialize_session_state():
    """
    Inicializa variáveis se não existirem.
    """
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False


def apply_custom_css():
    """
    Aplica estilos customizados à aplicação.
    """
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
    """
    Renderiza menu lateral (option_menu) e retorna página selecionada.
    """
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
                "receipt","cloud-upload","list","gear",
                "gift","calendar"
            ],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"background-color": "#1b4f72"},
                "icon": {"color": "white","font-size":"18px"},
                "nav-link": {
                    "font-size": "14px",
                    "text-align": "left",
                    "margin": "0px",
                    "color": "white",
                    "--hover-color": "#145a7c"
                },
                "nav-link-selected": {"background-color": "#145a7c","color":"white"},
            }
        )
    return selected


def main():
    """
    Função principal do app. Gera a navegação, login e páginas.
    """
    apply_custom_css()
    initialize_session_state()

    if not st.session_state.logged_in:
        # Usuário não logado: vai para a página de login
        login_page()
    else:
        # Usuário logado: mostra menu lateral
        selected_page = sidebar_navigation()

        # Se mudou de página, recarrega dados do cache
        if 'current_page' not in st.session_state:
            st.session_state.current_page = selected_page
        elif selected_page != st.session_state.current_page:
            refresh_data()
            st.session_state.current_page = selected_page

        # Roteamento
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

        # Botão de Logout
        with st.sidebar:
            if st.button("Logout"):
                for key in ["home_page_initialized"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.logged_in = False
                st.success("Desconectado com sucesso!")
                st.experimental_rerun()


# Se quiser que o app seja executado automaticamente ao rodar:
if __name__ == "__main__":
    main()
