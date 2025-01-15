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
import calendar  # Para gerar o HTML do calendário

###############################################################################
#                                   UTILIDADES
###############################################################################
def format_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
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
    st.download_button(label=label, data=buffer.getvalue(), file_name=filename, mime="application/octet-stream")


###############################################################################
#                      FUNÇÕES PARA PDF E UPLOAD (OPCIONAIS)
###############################################################################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Cabeçalhos
    for column in df.columns:
        pdf.cell(40, 10, str(column), border=1)
    pdf.ln()

    # Linhas
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(40, 10, str(item), border=1)
        pdf.ln()

    return pdf.output(dest='S')


def upload_pdf_to_fileio(pdf_bytes: bytes) -> str:
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
    except:
        pass


###############################################################################
#                            CONEXÃO COM BANCO
###############################################################################
def get_db_connection():
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
    Executa uma query no banco, sem mostrar mensagens ao usuário em caso de falha.
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
#                         CARREGAMENTO DE DADOS (CACHE)
###############################################################################
@st.cache_data(show_spinner=False)  # não exibir spinner
def load_all_data():
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
    except:
        pass
    return data


def refresh_data():
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
        # Expander para agrupar relatórios administrativos
        with st.expander("Open Orders Summary"):
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
            except:
                st.info("Erro ao gerar resumo Stock vs. Orders.")

        # NOVO ITEM: Total Faturado
        with st.expander("Total Faturado"):
            faturado_query = """
                SELECT date("Data") as dt, SUM("total") as total_dia
                FROM public.vw_pedido_produto
                WHERE status IN ('Received - Debited','Received - Credit','Received - Pix','Received - Cash')
                GROUP BY date("Data")
                ORDER BY date("Data")
            """
            faturado_data = run_query(faturado_query)
            if faturado_data:
                df_fat = pd.DataFrame(faturado_data, columns=["Data","Total do Dia"])
                df_fat["Total do Dia"] = df_fat["Total do Dia"].apply(format_currency)
                st.table(df_fat)
            else:
                st.info("Nenhum dado de faturamento encontrado.")


def orders_page():
    st.title("Gerenciar Pedidos")
    # Criamos abas para separar "Novo Pedido" e "Listagem de Pedidos"
    tabs = st.tabs(["Novo Pedido", "Listagem de Pedidos"])

    # ======================= ABA: Novo Pedido =======================
    with tabs[0]:
        st.subheader("Novo Pedido")
        product_data = st.session_state.data.get("products", [])
        product_list = [""] + [row[1] for row in product_data] if product_data else ["No products"]

        with st.form(key='order_form'):
            # Recuperando clientes de tabela tb_clientes
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
                run_query(query_insert, (customer_name, product, quantity, datetime.now()), commit=True)
                st.success("Pedido registrado com sucesso!")
                refresh_data()
            else:
                st.warning("Preencha todos os campos.")

    # ======================= ABA: Listagem de Pedidos =======================
    with tabs[1]:
        st.subheader("Listagem de Pedidos")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            cols = ["Cliente","Produto","Quantidade","Data","Status"]
            df_orders = pd.DataFrame(orders_data, columns=cols)
            st.dataframe(df_orders, use_container_width=True)
            download_df_as_csv(df_orders, "orders.csv", label="Baixar Pedidos CSV")

            # Só exibe form de edição se for admin
            if st.session_state.get("username") == "admin":
                st.markdown("### Editar ou Deletar Pedido")
                df_orders["unique_key"] = df_orders.apply(
                    lambda row: f"{row['Cliente']}|{row['Produto']}|{row['Data'].strftime('%Y-%m-%d %H:%M:%S')}",
                    axis=1
                )
                unique_keys = df_orders["unique_key"].unique().tolist()
                selected_key = st.selectbox("Selecione Pedido", [""] + unique_keys)

                if selected_key:
                    match = df_orders[df_orders["unique_key"] == selected_key]
                    if len(match) > 1:
                        st.warning("Múltiplos registros com a mesma chave.")
                    else:
                        sel = match.iloc[0]
                        original_client = sel["Cliente"]
                        original_product = sel["Produto"]
                        original_qty = sel["Quantidade"]
                        original_date = sel["Data"]
                        original_status = sel["Status"]

                        with st.form(key='edit_order_form'):
                            col1, col2, col3 = st.columns(3)
                            product_data = st.session_state.data.get("products", [])
                            product_list = [row[1] for row in product_data] if product_data else ["No products"]

                            with col1:
                                if original_product in product_list:
                                    prod_index = product_list.index(original_product)
                                else:
                                    prod_index = 0
                                edit_prod = st.selectbox("Produto", product_list, index=prod_index)
                            with col2:
                                edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))
                            with col3:
                                status_opts = [
                                    "em aberto", "Received - Debited", "Received - Credit",
                                    "Received - Pix", "Received - Cash"
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
                            run_query(q_del, (original_client, original_product, original_date), commit=True)
                            st.success("Pedido deletado!")
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
                            st.success("Pedido atualizado!")
                            refresh_data()
        else:
            st.info("Nenhum pedido encontrado.")


def products_page():
    st.title("Produtos")
    # Uso de tabs para separar "Novo Produto" e "Listagem de Produtos"
    tabs = st.tabs(["Novo Produto", "Listagem de Produtos"])

    # ======================= ABA: Novo Produto =======================
    with tabs[0]:
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
                run_query(q_ins, (supplier, product, quantity, unit_value, total_value, creation_date), commit=True)
                st.success("Produto adicionado com sucesso!")
                refresh_data()
            else:
                st.warning("Preencha todos os campos.")

    # ======================= ABA: Listagem de Produtos =======================
    with tabs[1]:
        st.subheader("Todos os Produtos")
        products_data = st.session_state.data.get("products", [])
        if products_data:
            cols = ["Supplier","Product","Quantity","Unit Value","Total Value","Creation Date"]
            df_prod = pd.DataFrame(products_data, columns=cols)
            st.dataframe(df_prod, use_container_width=True)
            download_df_as_csv(df_prod, "products.csv", label="Baixar Produtos CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Editar / Deletar Produto")
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
                            run_query(q_upd, (
                                edit_supplier, edit_product, edit_quantity, edit_unit_val, edit_total_val,
                                edit_creation_date, original_supplier, original_product, original_creation_date
                            ), commit=True)
                            st.success("Produto atualizado!")
                            refresh_data()

                        if delete_btn:
                            confirm = st.checkbox("Confirma a exclusão deste produto?")
                            if confirm:
                                q_del = """
                                    DELETE FROM public.tb_products
                                    WHERE supplier=%s AND product=%s AND creation_date=%s
                                """
                                run_query(q_del, (
                                    original_supplier, original_product, original_creation_date
                                ), commit=True)
                                st.success("Produto deletado!")
                                refresh_data()
        else:
            st.info("Nenhum produto encontrado.")


def stock_page():
    st.title("Estoque")
    tabs = st.tabs(["Nova Movimentação", "Movimentações"])

    # ======================= ABA: Nova Movimentação =======================
    with tabs[0]:
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
                run_query(q_ins, (product, quantity, transaction, current_datetime), commit=True)
                st.success("Movimentação de estoque registrada!")
                refresh_data()
            else:
                st.warning("Selecione produto e quantidade > 0.")

    # ======================= ABA: Movimentações =======================
    with tabs[1]:
        st.subheader("Movimentações de Estoque")
        stock_data = st.session_state.data.get("stock", [])
        if stock_data:
            cols = ["Produto","Quantidade","Transação","Data"]
            df_stock = pd.DataFrame(stock_data, columns=cols)
            st.dataframe(df_stock, use_container_width=True)
            download_df_as_csv(df_stock, "stock.csv", label="Baixar Stock CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Editar/Deletar Registro de Estoque")
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
                            product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
                            product_list = [row[0] for row in product_data] if product_data else ["No products"]

                            with col1:
                                if original_product in product_list:
                                    prod_index = product_list.index(original_product)
                                else:
                                    prod_index = 0
                                edit_prod = st.selectbox("Produto", product_list, index=prod_index)
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
                            run_query(q_upd, (
                                edit_prod, edit_qty, edit_trans, new_dt,
                                original_product, original_trans, original_date
                            ), commit=True)
                            st.success("Estoque atualizado!")
                            refresh_data()

                        if delete_btn:
                            q_del = """
                                DELETE FROM public.tb_estoque
                                WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                            """
                            run_query(q_del, (original_product, original_trans, original_date), commit=True)
                            st.success("Registro deletado!")
                            refresh_data()
        else:
            st.info("Nenhuma movimentação de estoque encontrada.")


def clients_page():
    st.title("Clientes")
    tabs = st.tabs(["Novo Cliente", "Listagem de Clientes"])

    # ======================= ABA: Novo Cliente =======================
    with tabs[0]:
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
                    INSERT INTO public.tb_clientes(
                        nome_completo, data_nascimento, genero, telefone,
                        email, endereco, data_cadastro
                    )
                    VALUES(%s,%s,%s,%s,%s,%s,CURRENT_TIMESTAMP)
                """
                run_query(q_ins, (nome_completo, data_nasc, genero, telefone, email, endereco), commit=True)
                st.success("Cliente registrado!")
                refresh_data()
            else:
                st.warning("Informe o nome completo.")

    # ======================= ABA: Listagem de Clientes =======================
    with tabs[1]:
        st.subheader("Todos os Clientes")
        clients_data = run_query("SELECT nome_completo,email FROM public.tb_clientes ORDER BY data_cadastro DESC;")
        if clients_data:
            cols = ["Full Name","Email"]
            df_clients = pd.DataFrame(clients_data, columns=cols)
            # Exibir apenas a coluna Full Name
            st.dataframe(df_clients[["Full Name"]], use_container_width=True)
            download_df_as_csv(df_clients[["Full Name"]], "clients.csv", label="Baixar Clients CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Editar / Deletar Cliente")
                client_display = [""] + [f"{row['Full Name']} ({row['Email']})"
                                         for _, row in df_clients.iterrows()]
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
                            run_query(q_upd, (edit_name, original_email), commit=True)
                            st.success("Cliente atualizado!")
                            refresh_data()
                        else:
                            st.warning("Informe o nome completo.")

                    if delete_btn:
                        q_del = "DELETE FROM public.tb_clientes WHERE email=%s"
                        run_query(q_del, (original_email,), commit=True)
                        st.success("Cliente deletado!")
                        refresh_data()
                        st.experimental_rerun()
        else:
            st.info("Nenhum cliente encontrado.")


###############################################################################
#                     FUNÇÕES AUXILIARES PARA NOTA FISCAL
###############################################################################
def process_payment(client, payment_status):
    query = """
        UPDATE public.tb_pedido
        SET status=%s,"Data"=CURRENT_TIMESTAMP
        WHERE "Cliente"=%s AND status='em aberto'
    """
    run_query(query, (payment_status, client), commit=True)


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

    # Garante que df["total"] seja numérico
    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
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


###############################################################################
#                          PÁGINA: NOTA FISCAL
###############################################################################
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

            # Converte para numeric
            df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
            total_sem_desconto = df["total"].sum()

            # Cupom fixo de exemplo
            cupons_validos = {
                "DESCONTO10": 0.10,
                "DESCONTO15": 0.15,
            }

            coupon_code = st.text_input("CUPOM (desconto opcional)")
            desconto_aplicado = 0.0
            if coupon_code in cupons_validos:
                desconto_aplicado = cupons_validos[coupon_code]
                st.success(f"Cupom {coupon_code} aplicado! Desconto de {desconto_aplicado*100:.0f}%")

            # Cálculo final
            total_sem_desconto = float(total_sem_desconto or 0)
            desconto_aplicado = float(desconto_aplicado or 0)
            total_com_desconto = total_sem_desconto * (1 - desconto_aplicado)

            # Gera a nota (ainda mostrando valores sem considerar item a item o desconto, mas no final exibimos total_com_desconto)
            generate_invoice_for_printer(df)

            st.write(f"**Total sem desconto:** {format_currency(total_sem_desconto)}")
            st.write(f"**Desconto:** {desconto_aplicado*100:.0f}%")
            st.write(f"**Total com desconto:** {format_currency(total_com_desconto)}")

            # Botões de pagamento
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


###############################################################################
#                           BACKUP (ADMIN)
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
        except:
            pass
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
        except:
            pass
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
#                           PÁGINA: CALENDÁRIO DE EVENTOS
###############################################################################
import streamlit as st
import calendar
from datetime import date, datetime
import pandas as pd

def events_calendar_page():
    st.title("Calendário de Eventos")

    # ---------------------------------------------------------
    # 1. Leitura dos eventos do DB
    # ---------------------------------------------------------
    query_select = """
        SELECT id, nome, descricao, data_evento, inscricao_aberta
        FROM public.tb_eventos
        ORDER BY data_evento;
    """
    events_data = run_query(query_select)  # returns list of tuples
    if not events_data:
        events_data = []  # se estiver vazio ou None, vira lista vazia

    # Converte para uma lista de dicionários (opcional) ou DataFrame
    # Aqui convertemos para lista de dict para facilitar
    eventos_db = []
    for row in events_data:
        # row é algo como (id, nome, descricao, data_evento, inscricao_aberta)
        eventos_db.append({
            "id": row[0],
            "nome": row[1],
            "descricao": row[2],
            "data": row[3],
            "inscricao_aberta": row[4],
        })

    # ---------------------------------------------------------
    # 2. Formulário para agendar novo evento
    # ---------------------------------------------------------
    with st.form(key="new_event"):
        st.subheader("Agendar Novo Evento")
        nome_evento = st.text_input("Nome do Evento")
        data_evento = st.date_input("Data do Evento", value=date.today())
        descricao_evento = st.text_area("Descrição do Evento")
        inscricao_aberta = st.checkbox("Inscrição Aberta?", value=True)

        agendar = st.form_submit_button("Agendar Evento")

    if agendar:
        if nome_evento.strip():
            query_insert = """
                INSERT INTO public.tb_eventos (nome, descricao, data_evento, inscricao_aberta)
                VALUES (%s, %s, %s, %s);
            """
            run_query(
                query_insert,
                (nome_evento.strip(), descricao_evento.strip(), data_evento, inscricao_aberta),
                commit=True
            )
            st.success("Evento agendado com sucesso!")
            st.experimental_rerun()  # Recarrega a página para atualizar listagem
        else:
            st.warning("Informe ao menos o nome do evento!")

    st.markdown("---")

    # ---------------------------------------------------------
    # 3. Exibir calendário do mês atual
    # ---------------------------------------------------------
    today = date.today()
    year = today.year
    month = today.month

    # Filtra eventos somente do mês/ano atual
    events_this_month = [
        ev for ev in eventos_db
        if ev["data"].year == year and ev["data"].month == month
    ]

    cal = calendar.HTMLCalendar(firstweekday=0)  # 0 = segunda-feira ou 6 = domingo, etc.
    html_calendar = cal.formatmonth(year, month)

    # Destaca os dias que têm evento
    for ev in events_this_month:
        event_day = ev["data"].day
        # Cria string de destaque com tooltip
        highlight_str = (
            f' style="background-color:yellow; font-weight:bold;" '
            f'title="{ev["nome"]}: {ev["descricao"]}"'
        )

        # Substitui para cada classe de dia (mon, tue, etc.)
        for cssclass in cal.cssclasses:
            original_tag = f'<td class="{cssclass}">{event_day}</td>'
            replaced_tag = f'<td class="{cssclass}"{highlight_str}>{event_day}</td>'
            html_calendar = html_calendar.replace(original_tag, replaced_tag)

    st.subheader(f"Calendário {today.strftime('%B de %Y')}")
    st.markdown(html_calendar, unsafe_allow_html=True)

    # Lista de eventos do mês
    if events_this_month:
        st.subheader("Eventos deste mês")
        df_month_events = pd.DataFrame(events_this_month)
        # Ajuste formato
        df_month_events["data"] = df_month_events["data"].astype(str)
        df_month_events.rename(columns={
            "nome": "Nome do Evento",
            "descricao": "Descrição",
            "data": "Data",
            "inscricao_aberta": "Inscrição Aberta"
        }, inplace=True)
        st.dataframe(df_month_events, use_container_width=True)
    else:
        st.info("Nenhum evento agendado para este mês.")

    st.markdown("---")

    # ---------------------------------------------------------
    # 4. Excluir Eventos
    # ---------------------------------------------------------
    st.subheader("Excluir Eventos Registrados")
    
    # Monta lista de identificação única: "<id> - Nome (YYYY-MM-DD)"
    def event_key(ev):
        return f"{ev['id']} - {ev['nome']} ({ev['data'].strftime('%Y-%m-%d')})"

    all_keys = [event_key(ev) for ev in eventos_db]
    selected_event_key = st.selectbox("Selecione um evento para excluir", [""] + all_keys)

    if st.button("Excluir Evento Selecionado"):
        if selected_event_key == "":
            st.warning("Selecione um evento para excluir.")
        else:
            # Extrai o ID do prefixo "<id> - ..."
            try:
                event_id_str = selected_event_key.split(" - ")[0]
                event_id = int(event_id_str)
            except:
                st.error("Formato inesperado ao extrair ID do evento.")
                return

            # Com o ID, removemos do banco
            query_delete = "DELETE FROM public.tb_eventos WHERE id=%s;"
            run_query(query_delete, (event_id,), commit=True)
            st.success(f"Evento ID={event_id} excluído com sucesso!")
            st.experimental_rerun()



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
    except:
        pass

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
            st.session_state.login_time = datetime.now()
            st.success("Login como administrador!")
            st.experimental_rerun()
        elif username == creds["caixa_username"] and password == creds["caixa_password"]:
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.session_state.login_time = datetime.now()
            st.success("Login como caixa!")
            st.experimental_rerun()
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
        # Novo texto acima do menu
        if 'login_time' in st.session_state:
            st.write(
                f"{st.session_state.username} logado as {st.session_state.login_time.strftime('%Hh%Mmin')}"
            )

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


def menu_page():
    st.title("Cardápio")

    product_data = run_query("""
        SELECT supplier, product, quantity, unit_value, total_value, creation_date, image_url
        FROM public.tb_products
        ORDER BY creation_date DESC
    """)
    if not product_data:
        st.warning("Nenhum produto encontrado no cardápio.")
        return

    df_products = pd.DataFrame(
        product_data,
        columns=["Supplier", "Product", "Quantity", "Unit Value", "Total Value", "Creation Date", "image_url"]
    )
    df_products["Preço"] = df_products["Unit Value"].apply(format_currency)

    tabs = st.tabs(["Ver Cardápio", "Gerenciar Imagens"])

    with tabs[0]:
        st.subheader("Itens Disponíveis")
        for idx, row in df_products.iterrows():
            product_name = row["Product"]
            price_text   = row["Preço"]
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
                st.write(f"Preço: {price_text}")

            st.markdown("---")

    with tabs[1]:
        st.subheader("Fazer upload/editar imagem de cada produto")

        product_names = df_products["Product"].unique().tolist()
        chosen_product = st.selectbox("Selecione o produto", options=[""] + product_names)

        if chosen_product:
            df_sel = df_products[df_products["Product"] == chosen_product].head(1)
            if not df_sel.empty:
                current_image = df_sel.iloc[0]["image_url"] or ""
            else:
                current_image = ""

            st.write("Imagem atual:")
            if current_image:
                try:
                    st.image(current_image, width=200)
                except:
                    st.image("https://via.placeholder.com/200", width=200)
            else:
                st.image("https://via.placeholder.com/200", width=200)

            uploaded_file = st.file_uploader("Carregar nova imagem do produto (PNG/JPG)", type=["png", "jpg", "jpeg"])

            if st.button("Salvar Imagem"):
                if not uploaded_file:
                    st.warning("Selecione um arquivo antes de salvar.")
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
                    st.success("Imagem atualizada com sucesso!")
                    refresh_data()
                    st.experimental_rerun()


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

    # 1) Carrega e filtra dados da view
    query = """
        SELECT "Cliente", total_geral
        FROM public.vw_cliente_sum_total
        WHERE total_geral > 100
          AND "Cliente" <> 'Professor Vinicius Bech Club Boituva'
    """
    data = run_query(query)
    if data:
        # 2) Converte em DataFrame e exibe
        df = pd.DataFrame(data, columns=["Cliente","Total Geral"])
        st.subheader("Clientes com Total Geral > 100")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum cliente com total_geral acima de 100 (ou com Professor Vinicius filtrado).")

    st.markdown("---")

    # 3) Lógica de pontos existente
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



###############################################################################
#                                     MAIN
###############################################################################
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
