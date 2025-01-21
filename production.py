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
import mitosheet  # Importação do MitoSheet
from mitosheet.streamlit.v1 import spreadsheet
from mitosheet.streamlit.v1.spreadsheet import _get_mito_backend

# Configuração da página para layout wide
st.set_page_config(layout="wide")

#############################################################################
#                                   UTILIDADES
###############################################################################
def format_currency(value: float) -> str:
    """Formata um valor float para o formato de moeda brasileira."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """Permite o download de um DataFrame como CSV."""
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    """Permite o download de um DataFrame como Excel."""
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


def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    """Permite o download de um DataFrame como JSON."""
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")


def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    """Permite o download de um DataFrame como HTML."""
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")


def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    """Permite o download de um DataFrame como Parquet."""
    import io
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)
    st.download_button(label=label, data=buffer.getvalue(), file_name=filename, mime="application/octet-stream")


###############################################################################
#                      FUNÇÕES PARA PDF E UPLOAD (OPCIONAIS)
###############################################################################
def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """Converte um DataFrame para PDF usando FPDF."""
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
    """Faz upload de um PDF para o file.io e retorna o link."""
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
    """Estabelece conexão com o banco de dados PostgreSQL usando as credenciais do Streamlit Secrets."""
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
    Executa uma query no banco de dados.
    - query: String contendo a query SQL.
    - values: Valores para parametrização da query.
    - commit: Se True, realiza commit após a execução.
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
@st.cache_data(show_spinner=False)  # Não exibir spinner
def load_all_data():
    """Carrega todos os dados necessários do banco de dados e armazena no session_state."""
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
            SELECT date("Data") as dt, SUM("total") as total_dia
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
    """Atualiza os dados armazenados no session_state."""
    load_all_data.clear()
    st.session_state.data = load_all_data()


###############################################################################
#                           PÁGINAS DO APLICATIVO
###############################################################################
def home_page():
    """Página inicial do aplicativo."""
    st.title("Boituva Beach Club")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

    # Adicionando Calendar View acima de Open Orders Summary
    st.subheader("Eventos do Mês Atual")
    current_date = date.today()
    ano_atual = current_date.year
    mes_atual = current_date.month

    # Obter eventos do banco de dados para o mês atual
    events_query = """
        SELECT nome, descricao, data_evento 
        FROM public.tb_eventos 
        WHERE EXTRACT(YEAR FROM data_evento) = %s AND EXTRACT(MONTH FROM data_evento) = %s
        ORDER BY data_evento
    """
    events_data = run_query(events_query, (ano_atual, mes_atual))
    if events_data:
        # Gerar o calendário HTML com dias de eventos destacados
        cal = calendar.HTMLCalendar(firstweekday=0)
        html_calendario = cal.formatmonth(ano_atual, mes_atual)

        # Destacar dias com eventos em azul
        for _, ev in events_data:
            dia = ev[2].day  # ev[2] corresponde a "data_evento"
            # Ajustar a cor de fundo para azul e o texto para branco
            highlight_str = (
                f' style="background-color:blue; color:white; font-weight:bold;" '
                f'title="{ev[0]}: {ev[1]}"'
            )
            # Substituir as tags <td class="...">dia</td> correspondentes ao dia
            for day_class in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                html_calendario = html_calendario.replace(
                    f'<td class="{day_class}">{dia}</td>',
                    f'<td class="{day_class}"{highlight_str}>{dia}</td>'
                )

        # Adicionar CSS para estilizar o calendário
        st.markdown(
            """
            <style>
            table {
                width: 100%;
                border-collapse: collapse;
            }
            th {
                background-color: #1b4f72;
                color: white;
                padding: 5px;
            }
            td {
                width: 14.28%;
                height: 80px;
                text-align: center;
                vertical-align: top;
                border: 1px solid #ddd;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.markdown(html_calendario, unsafe_allow_html=True)
    else:
        st.info("Nenhum evento registrado para este mês.")

    # Placeholder para notificações futuras (se necessário)
    notification_placeholder = st.empty()

    # Exemplo de uso adicional: Exibir sumário de pedidos abertos se admin
    if st.session_state.get("username") == "admin":
        with st.expander("Open Orders Summary"):
            open_orders_query = """
                SELECT "Cliente", SUM("total") AS Total
                FROM public.vw_pedido_produto
                WHERE status=%s
                GROUP BY "Cliente"
                ORDER BY "Cliente" DESC
            """
            open_orders_data = run_query(open_orders_query, ('em aberto',))
            if open_orders_data:
                df_open = pd.DataFrame(open_orders_data, columns=["Client", "Total"])
                total_open = df_open["Total"].sum()
                df_open["Total_display"] = df_open["Total"].apply(format_currency)
                st.table(df_open[["Client", "Total_display"]])
                st.markdown(f"**Total Geral (Open Orders):** {format_currency(total_open)}")
            else:
                st.info("Nenhum pedido em aberto encontrado.")

        with st.expander("Stock vs. Orders Summary"):
            try:
                stock_vs_orders_query = """
                    SELECT product, stock_quantity, orders_quantity, total_in_stock
                    FROM public.vw_stock_vs_orders_summary
                """
                stock_vs_orders_data = run_query(stock_vs_orders_query)
                if stock_vs_orders_data:
                    df_svo = pd.DataFrame(
                        stock_vs_orders_data,
                        columns=["Product", "Stock_Quantity", "Orders_Quantity", "Total_in_Stock"]
                    )
                    df_svo.sort_values("Total_in_Stock", ascending=False, inplace=True)
                    df_display = df_svo[["Product", "Total_in_Stock"]]
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
                            st.success("PDF enviado via WhatsApp com sucesso!")
                        else:
                            st.warning("Informe o número e certifique-se de que o upload foi bem-sucedido.")
                else:
                    st.info("View 'vw_stock_vs_orders_summary' sem dados ou inexistente.")
            except:
                st.info("Erro ao gerar resumo Stock vs. Orders.")

        # NOVO ITEM: Total Faturado
        with st.expander("Amount Invoiced"):
            faturado_query = """
                SELECT date("Data") as dt, SUM("total") as total_dia
                FROM public.vw_pedido_produto
                WHERE status IN ('Received - Debited','Received - Credit','Received - Pix','Received - Cash')
                GROUP BY date("Data")
                ORDER BY date("Data")
            """
            faturado_data = run_query(faturado_query)
            if faturado_data:
                df_fat = pd.DataFrame(faturado_data, columns=["Data", "Total do Dia"])
                df_fat["Total do Dia"] = df_fat["Total do Dia"].apply(format_currency)
                st.table(df_fat)
            else:
                st.info("Nenhum dado de faturamento encontrado.")


def orders_page():
    """Página para gerenciar pedidos."""
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

        # Adicionando tabela com os últimos 5 pedidos abaixo do formulário com texto reduzido
        st.subheader("Últimos 5 Pedidos Registrados")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            df_recent_orders = pd.DataFrame(orders_data, columns=["Cliente", "Produto", "Quantidade", "Data", "Status"])
            df_recent_orders = df_recent_orders.head(5)
            # Aplicando CSS para reduzir o tamanho do texto
            st.markdown(
                """
                <style>
                .small-font {
                    font-size:10px;
                }
                </style>
                """,
                unsafe_allow_html=True
            )
            st.markdown('<div class="small-font">', unsafe_allow_html=True)
            st.table(df_recent_orders)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Nenhum pedido encontrado.")

    # ======================= ABA: Listagem de Pedidos =======================
    with tabs[1]:
        st.subheader("Listagem de Pedidos")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            cols = ["Cliente", "Produto", "Quantidade", "Data", "Status"]
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
                                edit_prod = st.selectbox("Produto", product_list, index=product_list.index(original_product) if original_product in product_list else 0)
                            with col2:
                                edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))
                            with col3:
                                status_opts = [
                                    "em aberto", "Received - Debited", "Received - Credit",
                                    "Received - Pix", "Received - Cash"
                                ]
                                edit_status = st.selectbox("Status", status_opts, index=status_opts.index(original_status) if original_status in status_opts else 0)

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
                                SET "Produto"=%s, "Quantidade"=%s, status=%s
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
    """Página para gerenciar produtos."""
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
                    (supplier, product, quantity, unit_value, total_value, creation_date)
                    VALUES (%s, %s, %s, %s, %s, %s)
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
            cols = ["Supplier", "Product", "Quantity", "Unit Value", "Total Value", "Creation Date"]
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
                selected_key = st.selectbox("Selecione Produto:", [""] + unique_keys)
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
                                SET supplier=%s, product=%s, quantity=%s, unit_value=%s,
                                    total_value=%s, creation_date=%s
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
    """Página para gerenciar estoque."""
    st.title("Estoque")
    tabs = st.tabs(["Nova Movimentação", "Movimentações"])

    # ======================= ABA: Nova Movimentação =======================
    with tabs[0]:
        st.subheader("Registrar nova movimentação de estoque")
        product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
        product_list = [row[0] for row in product_data] if product_data else ["No products"]

        with st.form(key='stock_form'):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                product = st.selectbox("Produto", product_list)
            with col2:
                quantity = st.number_input("Quantidade", min_value=1, step=1)
            with col3:
                transaction = st.selectbox("Tipo de Transação", ["Entrada", "Saída"])
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
            cols = ["Produto", "Quantidade", "Transação", "Data"]
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
                selected_key = st.selectbox("Selecione Registro", [""] + unique_keys)
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
                                    "Tipo", ["Entrada", "Saída"],
                                    index=["Entrada", "Saída"].index(original_trans)
                                    if original_trans in ["Entrada", "Saída"] else 0
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
                                SET "Produto"=%s, "Quantidade"=%s, "Transação"=%s, "Data"=%s
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
    """Página para gerenciar clientes."""
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
                data_nasc = date(2000, 1, 1)
                genero = "Other"
                telefone = "0000-0000"
                endereco = "Endereço padrão"
                unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
                email = f"{nome_completo.replace(' ', '_').lower()}_{unique_id}@example.com"

                q_ins = """
                    INSERT INTO public.tb_clientes(
                        nome_completo, data_nascimento, genero, telefone,
                        email, endereco, data_cadastro
                    )
                    VALUES(%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """
                run_query(q_ins, (nome_completo, data_nasc, genero, telefone, email, endereco), commit=True)
                st.success("Cliente registrado!")
                refresh_data()
            else:
                st.warning("Informe o nome completo.")

    # ======================= ABA: Listagem de Clientes =======================
    with tabs[1]:
        st.subheader("Todos os Clientes")
        clients_data = run_query("SELECT nome_completo, email FROM public.tb_clientes ORDER BY data_cadastro DESC;")
        if clients_data:
            cols = ["Full Name", "Email"]
            df_clients = pd.DataFrame(clients_data, columns=cols)
            # Exibir apenas a coluna Full Name
            st.dataframe(df_clients[["Full Name"]], use_container_width=True)
            download_df_as_csv(df_clients[["Full Name"]], "clients.csv", label="Baixar Clients CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Editar / Deletar Cliente")
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
    """Processa o pagamento atualizando o status do pedido."""
    query = """
        UPDATE public.tb_pedido
        SET status=%s, "Data"=CURRENT_TIMESTAMP
        WHERE "Cliente"=%s AND status='em aberto'
    """
    run_query(query, (payment_status, client), commit=True)


def generate_invoice_for_printer(df: pd.DataFrame):
    """Gera uma representação textual da nota fiscal para impressão."""
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
    grouped_df = df.groupby('Produto').agg({'Quantidade': 'sum', 'total': 'sum'}).reset_index()
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
#                          PÁGINA: NOTA FISCAL -> CASH
###############################################################################
def cash_page():
    """Página para gerar e gerenciar notas fiscais."""
    st.title("Cash")
    open_clients_query = 'SELECT DISTINCT "Cliente" FROM public.vw_pedido_produto WHERE status=%s'
    open_clients = run_query(open_clients_query, ('em aberto',))
    client_list = [row[0] for row in open_clients] if open_clients else []
    selected_client = st.selectbox("Selecione um Cliente", [""] + client_list)

    if selected_client:
        invoice_query = """
            SELECT "Produto", "Quantidade", "total"
            FROM public.vw_pedido_produto
            WHERE "Cliente"=%s AND status=%s
        """
        invoice_data = run_query(invoice_query, (selected_client, 'em aberto'))
        if invoice_data:
            df = pd.DataFrame(invoice_data, columns=["Produto", "Quantidade", "total"])

            # Converte para numeric
            df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
            total_sem_desconto = df["total"].sum()

            # Cupom fixo de exemplo
            cupons_validos = {
                "10": 0.10,
                "15": 0.15,
                "20": 0.20,
                "25": 0.25,
                "30": 0.30,
                "35": 0.35,
                "40": 0.40,
                "45": 0.45,
                "50": 0.50,
                "55": 0.55,
                "60": 0.60,
                "65": 0.65,
                "70": 0.70,
                "75": 0.75,
                "80": 0.80,
                "85": 0.85,
                "90": 0.90,
                "95": 0.95,
                "100": 1.00,
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
                    st.success("Pagamento via Débito processado!")
            with col2:
                if st.button("Credit"):
                    process_payment(selected_client, "Received - Credit")
                    st.success("Pagamento via Crédito processado!")
            with col3:
                if st.button("Pix"):
                    process_payment(selected_client, "Received - Pix")
                    st.success("Pagamento via Pix processado!")
            with col4:
                if st.button("Cash"):
                    process_payment(selected_client, "Received - Cash")
                    st.success("Pagamento via Dinheiro processado!")
        else:
            st.info("Não há pedidos em aberto para esse cliente.")
    else:
        st.warning("Selecione um cliente.")


###############################################################################
#                     NOVA PÁGINA: CALENDÁRIO DE EVENTOS
###############################################################################
def events_calendar_page():
    """Página para gerenciar o calendário de eventos."""
    st.title("Calendário de Eventos")

    # ----------------------------------------------------------------------------
    # 1) Helper: Ler eventos do banco
    # ----------------------------------------------------------------------------
    def get_events_from_db():
        """
        Retorna lista de tuplas (id, nome, descricao, data_evento, inscricao_aberta, data_criacao)
        ordenadas pela data_evento.
        """
        query = """
            SELECT id, nome, descricao, data_evento, inscricao_aberta, data_criacao
            FROM public.tb_eventos
            ORDER BY data_evento;
        """
        rows = run_query(query)  # Ajuste conforme suas funções de DB
        return rows if rows else []

    # ----------------------------------------------------------------------------
    # 2) Cadastro de novo evento
    # ----------------------------------------------------------------------------
    st.subheader("Agendar Novo Evento")
    with st.form(key="new_event_form"):
        col1, col2 = st.columns(2)
        with col1:
            nome_evento = st.text_input("Nome do Evento")
            data_evento = st.date_input("Data do Evento", value=date.today())
        with col2:
            inscricao_aberta = st.checkbox("Inscrição Aberta?", value=True)
            descricao_evento = st.text_area("Descrição do Evento")
        btn_cadastrar = st.form_submit_button("Agendar")

    if btn_cadastrar:
        if nome_evento.strip():
            q_insert = """
                INSERT INTO public.tb_eventos
                    (nome, descricao, data_evento, inscricao_aberta, data_criacao)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """
            run_query(q_insert, (nome_evento, descricao_evento, data_evento, inscricao_aberta), commit=True)
            st.success("Evento cadastrado com sucesso!")
            st.experimental_rerun()
        else:
            st.warning("Informe ao menos o nome do evento.")

    st.markdown("---")

    # ----------------------------------------------------------------------------
    # 3) Filtros de Mês/Ano
    # ----------------------------------------------------------------------------
    current_date = date.today()
    ano_padrao = current_date.year
    mes_padrao = current_date.month

    col_ano, col_mes = st.columns(2)
    with col_ano:
        ano_selecionado = st.selectbox(
            "Selecione o Ano",
            list(range(ano_padrao - 2, ano_padrao + 3)),  # Ex: de 2 anos atrás até 2 anos à frente
            index=2  # por padrão, seleciona o ano atual
        )
    with col_mes:
        meses_nomes = [calendar.month_name[i] for i in range(1, 13)]
        mes_selecionado = st.selectbox(
            "Selecione o Mês",
            options=list(range(1, 13)),
            format_func=lambda x: meses_nomes[x-1],
            index=mes_padrao - 1
        )

    # ----------------------------------------------------------------------------
    # 4) Ler dados e filtrar
    # ----------------------------------------------------------------------------
    event_rows = get_events_from_db()
    if not event_rows:
        st.info("Nenhum evento cadastrado.")
        return

    df_events = pd.DataFrame(
        event_rows,
        columns=["id", "nome", "descricao", "data_evento", "inscricao_aberta", "data_criacao"]
    )
    df_events["data_evento"] = pd.to_datetime(df_events["data_evento"], errors="coerce")

    df_filtrado = df_events[
        (df_events["data_evento"].dt.year == ano_selecionado) &
        (df_events["data_evento"].dt.month == mes_selecionado)
    ].copy()

    # ----------------------------------------------------------------------------
    # 5) Montar o calendário
    # ----------------------------------------------------------------------------
    st.subheader("Visualização do Calendário")

    cal = calendar.HTMLCalendar(firstweekday=0)
    html_calendario = cal.formatmonth(ano_selecionado, mes_selecionado)

    # Destacar dias com eventos
    for _, ev in df_filtrado.iterrows():
        dia = ev["data_evento"].day
        # Ajustar a cor de fundo para azul e o texto para branco
        highlight_str = (
            f' style="background-color:blue; color:white; font-weight:bold;" '
            f'title="{ev["nome"]}: {ev["descricao"]}"'
        )
        # Substituir as tags <td class="mon">dia</td>, <td class="tue">dia</td>, etc.
        for day_class in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            html_calendario = html_calendario.replace(
                f'<td class="{day_class}">{dia}</td>',
                f'<td class="{day_class}"{highlight_str}>{dia}</td>'
            )

    # Adicionar CSS para estilizar o calendário
    st.markdown(
        """
        <style>
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background-color: #1b4f72;
            color: white;
            padding: 5px;
        }
        td {
            width: 14.28%;
            height: 80px;
            text-align: center;
            vertical-align: top;
            border: 1px solid #ddd;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    st.markdown(html_calendario, unsafe_allow_html=True)

    # ----------------------------------------------------------------------------
    # 6) Listagem dos eventos no mês selecionado
    # ----------------------------------------------------------------------------
    st.subheader(f"Eventos de {calendar.month_name[mes_selecionado]} / {ano_selecionado}")
    if len(df_filtrado) == 0:
        st.info("Nenhum evento neste mês.")
    else:
        df_display = df_filtrado.copy()
        df_display["data_evento"] = df_display["data_evento"].dt.strftime("%Y-%m-%d")
        df_display.rename(columns={
            "id": "ID",
            "nome": "Nome do Evento",
            "descricao": "Descrição",
            "data_evento": "Data",
            "inscricao_aberta": "Inscrição Aberta",
            "data_criacao": "Data Criação"
        }, inplace=True)
        st.dataframe(df_display, use_container_width=True)

    st.markdown("---")

    # ----------------------------------------------------------------------------
    # 7) Edição e Exclusão de Eventos (sem confirmação extra)
    # ----------------------------------------------------------------------------
    st.subheader("Editar / Excluir Eventos")

    df_events["evento_label"] = df_events.apply(
        lambda row: f'{row["id"]} - {row["nome"]} ({row["data_evento"].strftime("%Y-%m-%d")})',
        axis=1
    )
    events_list = [""] + df_events["evento_label"].tolist()
    selected_event = st.selectbox("Selecione um evento:", events_list)

    if selected_event:
        # Extrair ID do formato "123 - Evento X (2025-01-01)"
        event_id_str = selected_event.split(" - ")[0]
        try:
            event_id = int(event_id_str)
        except ValueError:
            st.error("Falha ao interpretar ID do evento.")
            return

        # Carrega dados do evento selecionado
        ev_row = df_events[df_events["id"] == event_id].iloc[0]
        original_nome = ev_row["nome"]
        original_desc = ev_row["descricao"]
        original_data = ev_row["data_evento"]
        original_insc = ev_row["inscricao_aberta"]

        with st.expander("Editar Evento", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                new_nome = st.text_input("Nome do Evento", value=original_nome)
                new_data = st.date_input("Data do Evento", value=original_data.date())
            with col2:
                new_insc = st.checkbox("Inscrição Aberta?", value=original_insc)
                new_desc = st.text_area("Descrição do Evento", value=original_desc)

            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Atualizar Evento"):
                    if new_nome.strip():
                        q_update = """
                            UPDATE public.tb_eventos
                            SET nome=%s, descricao=%s, data_evento=%s, inscricao_aberta=%s
                            WHERE id=%s
                        """
                        run_query(q_update, (new_nome, new_desc, new_data, new_insc, event_id), commit=True)
                        st.success("Evento atualizado com sucesso!")
                        st.experimental_rerun()
                    else:
                        st.warning("O campo Nome do Evento não pode ficar vazio.")

            with col_btn2:
                # Exclusão imediata sem checkbox de confirmação
                if st.button("Excluir Evento"):
                    q_delete = "DELETE FROM public.tb_eventos WHERE id=%s;"
                    run_query(q_delete, (event_id,), commit=True)
                    st.success(f"Evento ID={event_id} excluído!")
                    st.experimental_rerun()
    else:
        st.info("Selecione um evento para editar ou excluir.")


def loyalty_program_page():
    """Página do programa de fidelidade."""
    st.title("Programa de Fidelidade")

    # 1) Carregar dados da view vw_cliente_sum_total
    query = 'SELECT "Cliente", total_geral FROM public.vw_cliente_sum_total;'
    data = run_query(query)  # Assume que run_query retorna lista de tuplas

    # 2) Exibir em dataframe
    if data:
        df = pd.DataFrame(data, columns=["Cliente", "Total Geral"])
        st.subheader("Clientes - Fidelidade")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado na view vw_cliente_sum_total.")

    st.markdown("---")

    # 3) (Opcional) Se desejar manter a lógica de acumular pontos localmente,
    # basta deixar o bloco abaixo. Caso não precise, remova.

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
#                     INICIALIZAÇÃO E MAIN
###############################################################################
def initialize_session_state():
    """Inicializa variáveis no session_state do Streamlit."""
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False


def apply_custom_css():
    """Aplica CSS customizado para melhorar a aparência do aplicativo."""
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
        <div class='css-1v3fvcr'>© 2025 | Todos os direitos reservados | Boituva Beach Club</div>
        """,
        unsafe_allow_html=True
    )


def sidebar_navigation():
    """Configura a barra lateral de navegação."""
    with st.sidebar:
        # Novo texto acima do menu

        selected = option_menu(
            "Beach Menu",
            [
                "Home", "Orders", "Products", "Stock", "Clients",
                "Cash",
                "Programa de Fidelidade", "Calendário de Eventos"
            ],
            icons=[
                "house", "file-text", "box", "list-task", "layers",
                "receipt",
                "gift", "calendar"
            ],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"background-color": "#1b4f72"},
                "icon": {"color": "white", "font-size": "18px"},
                "nav-link": {
                    "font-size": "14px", "text-align": "left", "margin": "0px",
                    "color": "white", "--hover-color": "#145a7c"
                },
                "nav-link-selected": {"background-color": "#145a7c", "color": "white"},
            }
        )
        if 'login_time' in st.session_state:
            st.write(
                f"{st.session_state.username} logado às {st.session_state.login_time.strftime('%Hh%Mmin')}"
            )
    return selected


###############################################################################
#                     PÁGINAS REMOVIDAS
###############################################################################
# A página "Cardápio" foi removida completamente, incluindo sua função e referências.


###############################################################################
#                     INICIALIZAÇÃO E MAIN
###############################################################################
def main():
    """Função principal que controla a execução do aplicativo."""
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
    elif selected_page == "Cash":
        cash_page()
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


###############################################################################
#                            LOGIN PAGE
###############################################################################
def login_page():
    """Página de login do aplicativo."""
    from PIL import Image
    import requests
    from io import BytesIO
    from datetime import datetime

    # ---------------------------------------------------------------------
    # 1) CSS Customizado para melhorar aparência
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Centraliza o container */
        .block-container {
            max-width: 450px;
            margin: 0 auto;
            padding-top: 40px;
        }
        /* Título maior e em negrito */
        .css-18e3th9 {
            font-size: 1.75rem;
            font-weight: 600;
            text-align: center;
        }
        /* Botão customizado */
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
        /* Mensagem de rodapé */
        .footer {
            position: fixed;
            left: 0; 
            bottom: 0; 
            width: 100%;
            text-align: center;
            font-size: 12px;
            color: #999;
        }
        /* Placeholder estilizado */
        input::placeholder {
            color: #bbb;
            font-size: 0.875rem;
        }
        /* Remove espaço entre os input boxes */
        .css-1siy2j8 input {
            margin-bottom: 0 !important; /* Sem margem entre os campos */
            padding-top: 5px;
            padding-bottom: 5px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # ---------------------------------------------------------------------
    # 2) Carregar logo
    # ---------------------------------------------------------------------
    logo_url = "https://via.placeholder.com/300x100?text=Boituva+Beach+Club"  # URL direto para a imagem
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
    # 3) Formulário de login
    # ---------------------------------------------------------------------
    with st.form("login_form", clear_on_submit=False):
        st.markdown("<p style='text-align: center;'>🌴keep the beach vibes flowing!🎾</p>", unsafe_allow_html=True)

        # Campos de entrada
        username_input = st.text_input("", placeholder="Username")
        password_input = st.text_input("", type="password", placeholder="Password")

        # Botão de login
        btn_login = st.form_submit_button("Log in")

        # Botão de login com Google (fora do formulário) - REMOVIDO
        # st.markdown(
        #     """
        #     <button class='gmail-login'>Log in with Google</button>
        #     """,
        #     unsafe_allow_html=True
        # )

    # ---------------------------------------------------------------------
    # 4) Ação: Login
    # ---------------------------------------------------------------------
    if btn_login:
        if not username_input or not password_input:
            st.error("Por favor, preencha todos os campos.")
        else:
            try:
                # Credenciais de exemplo
                creds = st.secrets["credentials"]
                admin_user = creds["admin_username"]
                admin_pass = creds["admin_password"]
                caixa_user = creds["caixa_username"]
                caixa_pass = creds["caixa_password"]
            except KeyError:
                st.error("Credenciais não encontradas em st.secrets['credentials']. Verifique a configuração.")
                st.stop()

            # Verificação de login
            if username_input == admin_user and password_input == admin_pass:
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.login_time = datetime.now()
                st.success("Login bem-sucedido como ADMIN!")
                st.experimental_rerun()

            elif username_input == caixa_user and password_input == caixa_pass:
                st.session_state.logged_in = True
                st.session_state.username = "caixa"
                st.session_state.login_time = datetime.now()
                st.success("Login bem-sucedido como CAIXA!")
                st.experimental_rerun()

            else:
                st.error("Usuário ou senha incorretos.")

    # ---------------------------------------------------------------------
    # 5) Rodapé / Footer
    # ---------------------------------------------------------------------
    st.markdown(
        """
        <div class='footer'>
            © 2025 | Todos os direitos reservados | Boituva Beach Club
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
