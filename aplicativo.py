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

###############################################################################
#                               UTILIDADES
###############################################################################
def format_currency(value: float) -> str:
    """Formata um valor float para o formato de moeda brasileira."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """Permite o download de um DataFrame como CSV."""
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")

def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    """Permite o download de um DataFrame como JSON."""
    json_data = df.to_json(orient='records', lines=False)  # Ajustado para JSON padrão
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
    st.download_button(
        label=label,
        data=buffer.getvalue(),
        file_name=filename,
        mime="application/octet-stream"
    )

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
        pdf.cell(60, 10, str(column), border=1)
    pdf.ln()

    # Linhas
    for _, row in df.iterrows():
        for item in row:
            pdf.cell(60, 10, str(item), border=1)
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
    except Exception as e:
        st.error(f"Falha na conexão com o banco de dados: {e}")
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
    except Exception as e:
        st.error(f"Erro ao executar query: {e}")
        return None
    finally:
        if conn and not conn.closed:
            conn.close()
    return None

###############################################################################
#                         CARREGAMENTO DE DADOS (CACHE)
###############################################################################
@st.cache_data(show_spinner=False)
def load_all_data():
    """Carrega todos os dados necessários do banco de dados e armazena no session_state."""
    data = {}
    try:
        data["orders"] = run_query(
            'SELECT "Cliente","Produto","Quantidade","Data",status FROM public.tb_pedido ORDER BY "Data" DESC'
        ) or []
        data["products"] = run_query(
            'SELECT supplier, product, quantity, unit_value, custo_unitario, total_value, creation_date FROM public.tb_products ORDER BY creation_date DESC'
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
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
    return data

def refresh_data():
    """Atualiza os dados armazenados no session_state."""
    load_all_data.clear()
    st.session_state.data = load_all_data()

@st.cache_data(show_spinner=False)
def get_latest_settings():
    """
    Retorna o último registro (maior id) da tabela tb_settings
    Formato: (id, company, address, cnpj_cpf, email, telephone, contract_number, created_at)
    Se não houver registro, retorna None.
    """
    query = """
        SELECT id, company, address, cnpj_cpf, email, telephone, contract_number, created_at
        FROM public.tb_settings
        ORDER BY id DESC
        LIMIT 1
    """
    result = run_query(query)
    if result:
        return result[0]  # a single row
    return None

###############################################################################
#                           PÁGINAS DO APLICATIVO
###############################################################################
def home_page():
    """Página inicial do aplicativo."""
    # Verifica se temos um registro em last_settings no session_state
    last_settings = st.session_state.get("last_settings", None)

    if last_settings:
        company_value = last_settings[1]  # Column: company
        address_value = last_settings[2]  # Column: address
        telephone_value = last_settings[5]  # Column: telephone

        # 1) Center the page title
        st.markdown(f"<h1 style='text-align:center;'>{company_value}</h1>", unsafe_allow_html=True)

        # 2) Include a line after the telephone
        st.markdown(
            f"""
            <p style='font-size:14px; text-align:center; margin-top:-10px;'>
                <strong>Address:</strong> {address_value}<br>
                <strong>Telephone:</strong> {telephone_value}
            </p>
            <hr>
            """,
            unsafe_allow_html=True
        )
    else:
        # Fallback se não houver registro em tb_settings
        st.markdown("<h1 style='text-align:center;'>Home</h1>", unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Calendário e eventos
    # -----------------------------------------------------------------------
    current_date = date.today()
    ano_atual = current_date.year
    mes_atual = current_date.month

    events_query = """
        SELECT nome, descricao, data_evento 
        FROM public.tb_eventos 
        WHERE EXTRACT(YEAR FROM data_evento) = %s AND EXTRACT(MONTH FROM data_evento) = %s
        ORDER BY data_evento
    """
    events_data = run_query(events_query, (ano_atual, mes_atual))

    col_calendar, col_events = st.columns([1, 1], gap="large")

    with col_calendar:
        if events_data:
            import calendar
            cal = calendar.HTMLCalendar(firstweekday=0)
            html_calendario = cal.formatmonth(ano_atual, mes_atual)

            for ev in events_data:
                nome, descricao, data_evento = ev
                dia = data_evento.day
                highlight_str = (
                    f' style="background-color:#1b4f72; color:white; font-weight:bold;" '
                    f'title="{nome}: {descricao}"'
                )
                for day_class in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
                    target = f'<td class="{day_class}">{dia}</td>'
                    replacement = f'<td class="{day_class}"{highlight_str}>{dia}</td>'
                    html_calendario = html_calendario.replace(target, replacement)

            st.markdown(
                """
                <style>
                table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                }
                th {
                    background-color: #1b4f72;
                    color: white;
                    padding: 5px;
                }
                td {
                    width: 14.28%;
                    height: 45px;
                    text-align: center;
                    vertical-align: top;
                    border: 1px solid #ddd;
                }
                @media only screen and (max-width: 600px) {
                    table {
                        font-size: 10px;
                    }
                    td {
                        height: 35px;
                    }
                }
                </style>
                """,
                unsafe_allow_html=True
            )
            st.markdown(html_calendario, unsafe_allow_html=True)
        else:
            st.info("Nenhum evento registrado para este mês.")

    with col_events:
        st.markdown("### Lista de Eventos")
        if events_data:
            events_sorted = sorted(events_data, key=lambda x: x[2].day)
            for ev in events_sorted:
                nome, descricao, data_evento = ev
                dia = data_evento.day
                st.write(f"**{dia}** - {nome}: {descricao}")
        else:
            st.write("Nenhum evento para este mês.")

    st.markdown("---")

    # Seções adicionais para usuários 'admin'
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
                df_open = df_open[["Client", "Total_display"]].reset_index(drop=True)

                styled_df_open = df_open.style.set_table_styles([
                    {'selector': 'th', 'props': [('background-color', '#ff4c4c'), ('color', 'white'), ('padding', '8px')]},
                    {'selector': 'td', 'props': [('padding', '8px'), ('text-align', 'right')]}
                ])
                st.write(styled_df_open)
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
                    df_display["Total_in_Stock"] = df_display["Total_in_Stock"].apply(lambda x: f"{x:,}")
                    df_display = df_display.reset_index(drop=True)

                    styled_df_svo = df_display.style.set_table_styles([
                        {'selector': 'th', 'props': [('background-color', '#ff4c4c'), ('color', 'white'), ('padding', '8px')]},
                        {'selector': 'td', 'props': [('padding', '8px'), ('text-align', 'right')]}
                    ])
                    st.write(styled_df_svo)
                    total_val = df_svo["Total_in_Stock"].sum()
                    st.markdown(f"**Total Geral (Stock vs. Orders):** {total_val:,}")
                else:
                    st.info("View 'vw_stock_vs_orders_summary' sem dados ou inexistente.")
            except Exception as e:
                st.info(f"Erro ao gerar resumo Stock vs. Orders: {e}")

        with st.expander("Profit per day"):
            try:
                query_lucro = """
                    SELECT "Data","Soma_Valor_total","Soma_Custo_total","Soma_Lucro_Liquido"
                    FROM public.vw_lucro_dia
                    ORDER BY "Data" DESC
                """
                data_lucro = run_query(query_lucro)
                if data_lucro:
                    df_lucro = pd.DataFrame(
                        data_lucro,
                        columns=["Data","Soma_Valor_total","Soma_Custo_total","Soma_Lucro_Liquido"]
                    )
                    df_lucro["Soma_Valor_total"] = pd.to_numeric(df_lucro["Soma_Valor_total"], errors="coerce").fillna(0)
                    df_lucro["Soma_Custo_total"] = pd.to_numeric(df_lucro["Soma_Custo_total"], errors="coerce").fillna(0)
                    df_lucro["Soma_Lucro_Liquido"] = pd.to_numeric(df_lucro["Soma_Lucro_Liquido"], errors="coerce").fillna(0)

                    df_lucro.columns = ["Data", "Valor total", "Custo total", "Lucro líquido"]
                    df_lucro["Valor total"] = df_lucro["Valor total"].apply(format_currency)
                    df_lucro["Custo total"] = df_lucro["Custo total"].apply(format_currency)
                    df_lucro["Lucro líquido"] = df_lucro["Lucro líquido"].apply(format_currency)

                    styled_df_lucro = df_lucro.style.set_table_styles([
                        {'selector': 'th', 'props': [('background-color', '#ff4c4c'), ('color', 'white'), ('padding', '8px')]},
                        {'selector': 'td', 'props': [('padding', '8px'), ('text-align', 'right')]}
                    ])
                    st.write(styled_df_lucro)
                else:
                    st.info("Nenhum dado encontrado em vw_lucro_dia.")
            except Exception as e:
                st.error(f"Erro ao exibir dados de lucro: {e}")

def orders_page():
    """Página para gerenciar pedidos."""
    st.title("Gerenciar Pedidos")
    tabs = st.tabs(["Novo Pedido", "Listagem de Pedidos"])

    with tabs[0]:
        st.subheader("Novo Pedido")
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
                success = run_query(query_insert, (customer_name, product, quantity, datetime.now()), commit=True)
                if success:
                    st.toast("Pedido registrado com sucesso!")
                    refresh_data()
                else:
                    st.error("Falha ao registrar pedido.")
            else:
                st.warning("Preencha todos os campos.")

        st.subheader("Últimos 5 Pedidos Registrados")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            df_recent_orders = pd.DataFrame(orders_data, columns=["Cliente", "Produto", "Quantidade", "Data", "Status"])
            df_recent_orders = df_recent_orders.head(5)
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
            st.write(df_recent_orders.reset_index(drop=True).style.set_table_styles([
                {'selector': 'th', 'props': [('background-color', '#ff4c4c'), ('color', 'white'), ('padding', '4px')]},
                {'selector': 'td', 'props': [('padding', '4px'), ('text-align', 'left')]}
            ]))
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("Nenhum pedido encontrado.")

    with tabs[1]:
        st.subheader("Listagem de Pedidos")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            cols = ["Cliente", "Produto", "Quantidade", "Data", "Status"]
            df_orders = pd.DataFrame(orders_data, columns=cols)
            st.dataframe(df_orders, use_container_width=True)
            download_df_as_csv(df_orders, "orders.csv", label="Baixar Pedidos CSV")

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
                            with col1:
                                product_data = st.session_state.data.get("products", [])
                                product_list = [row[1] for row in product_data] if product_data else ["No products"]
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
                            success = run_query(q_del, (original_client, original_product, original_date), commit=True)
                            if success:
                                st.toast("Pedido deletado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao deletar pedido.")

                        if update_btn:
                            q_upd = """
                                UPDATE public.tb_pedido
                                SET "Produto"=%s, "Quantidade"=%s, status=%s
                                WHERE "Cliente"=%s AND "Produto"=%s AND "Data"=%s
                            """
                            success = run_query(q_upd, (
                                edit_prod, edit_qty, edit_status,
                                original_client, original_product, original_date
                            ), commit=True)
                            if success:
                                st.toast("Pedido atualizado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao atualizar pedido.")
        else:
            st.info("Nenhum pedido encontrado.")

def products_page():
    """Página para gerenciar produtos."""
    st.title("Produtos")
    tabs = st.tabs(["Novo Produto", "Listagem de Produtos"])

    with tabs[0]:
        st.subheader("Novo Produto")
        with st.form(key='product_form'):
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                supplier = st.text_input("Fornecedor")
            with col2:
                product = st.text_input("Produto")
            with col3:
                quantity = st.number_input("Quantidade", min_value=1, step=1)
            with col4:
                unit_value = st.number_input("Valor Unitário", min_value=0.0, step=0.01, format="%.2f")
            with col5:
                custo_unitario = st.number_input("Custo Unitário", min_value=0.0, step=0.01, format="%.2f")
            creation_date = st.date_input("Data de Criação", value=date.today())
            submit_prod = st.form_submit_button("Inserir Produto")

        if submit_prod:
            if supplier and product and quantity > 0 and unit_value >= 0 and custo_unitario >= 0:
                total_value = quantity * unit_value
                q_ins = """
                    INSERT INTO public.tb_products
                    (supplier, product, quantity, unit_value, custo_unitario, total_value, creation_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                success = run_query(q_ins, (supplier, product, quantity, unit_value, custo_unitario, total_value, creation_date), commit=True)
                if success:
                    st.toast("Produto adicionado com sucesso!")
                    refresh_data()
                else:
                    st.error("Falha ao adicionar produto.")
            else:
                st.warning("Preencha todos os campos corretamente.")

    with tabs[1]:
        st.subheader("Todos os Produtos")
        products_data = st.session_state.data.get("products", [])
        if products_data:
            cols = ["Supplier", "Product", "Quantity", "Unit Value", "Custo Unitário", "Total Value", "Creation Date"]
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
                        original_custo_unitario = sel["Custo Unitário"]
                        original_creation_date = sel["Creation Date"]

                        with st.form(key='edit_product_form'):
                            col1, col2, col3, col4, col5 = st.columns(5)
                            with col1:
                                edit_supplier = st.text_input("Fornecedor", value=original_supplier)
                            with col2:
                                edit_product = st.text_input("Produto", value=original_product)
                            with col3:
                                edit_quantity = st.number_input("Quantidade", min_value=1, step=1, value=int(original_quantity))
                            with col4:
                                edit_unit_val = st.number_input(
                                    "Valor Unitário", min_value=0.0, step=0.01, format="%.2f",
                                    value=float(original_unit_value)
                                )
                            with col5:
                                edit_custo_unitario = st.number_input(
                                    "Custo Unitário", min_value=0.0, step=0.01, format="%.2f",
                                    value=float(original_custo_unitario)
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
                                    custo_unitario=%s, total_value=%s, creation_date=%s
                                WHERE supplier=%s AND product=%s AND creation_date=%s
                            """
                            success = run_query(q_upd, (
                                edit_supplier, edit_product, edit_quantity, edit_unit_val,
                                edit_custo_unitario, edit_total_val, edit_creation_date,
                                original_supplier, original_product, original_creation_date
                            ), commit=True)
                            if success:
                                st.toast("Produto atualizado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao atualizar produto.")

                        if delete_btn:
                            q_del = """
                                DELETE FROM public.tb_products
                                WHERE supplier=%s AND product=%s AND creation_date=%s
                            """
                            success = run_query(q_del, (
                                original_supplier, original_product, original_creation_date
                            ), commit=True)
                            if success:
                                st.toast("Produto deletado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao deletar produto.")
        else:
            st.info("Nenhum produto encontrado.")

def stock_page():
    """Página para gerenciar estoque."""
    st.title("Estoque")
    tabs = st.tabs(["Nova Movimentação", "Movimentações"])

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
                success = run_query(q_ins, (product, quantity, transaction, current_datetime), commit=True)
                if success:
                    st.toast("Movimentação de estoque registrada com sucesso!")
                    refresh_data()
                else:
                    st.error("Falha ao registrar movimentação de estoque.")
            else:
                st.warning("Selecione produto e quantidade > 0.")

        st.subheader("Stock vs. Orders Summary (por total_in_stock DESC)")
        query_svo = """
            SELECT product, stock_quantity, orders_quantity, total_in_stock
            FROM public.vw_stock_vs_orders_summary
            ORDER BY total_in_stock DESC
        """
        data_svo = run_query(query_svo)
        if data_svo:
            df_svo = pd.DataFrame(
                data_svo,
                columns=["Product", "Stock_Quantity", "Orders_Quantity", "Total_in_Stock"]
            )
            st.dataframe(df_svo, use_container_width=True)
        else:
            st.info("Nenhum dado encontrado em vw_stock_vs_orders_summary.")

    with tabs[1]:
        st.subheader("Movimentações de Estoque")
        stock_data = st.session_state.data.get("stock", [])
        if stock_data:
            cols = ["Produto", "Quantidade", "Transação", "Data"]
            df_stock = pd.DataFrame(stock_data, columns=cols)
            df_stock["Data"] = pd.to_datetime(df_stock["Data"]).dt.strftime("%Y-%m-%d %H:%M:%S")
            st.dataframe(df_stock, use_container_width=True)
            download_df_as_csv(df_stock, "stock.csv", label="Baixar Stock CSV")

            if st.session_state.get("username") == "admin":
                st.markdown("### Editar/Deletar Registro de Estoque")
                df_stock["unique_key"] = df_stock.apply(
                    lambda row: f"{row['Produto']}|{row['Transação']}|{row['Data']}",
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
                            with col1:
                                product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
                                product_list = [row[0] for row in product_data] if product_data else ["No products"]
                                idx_prod = product_list.index(original_product) if original_product in product_list else 0
                                edit_prod = st.selectbox("Produto", product_list, index=idx_prod)
                            with col2:
                                edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))
                            with col3:
                                trans_opts = ["Entrada", "Saída"]
                                idx_tr = trans_opts.index(original_trans) if original_trans in trans_opts else 0
                                edit_trans = st.selectbox("Tipo", trans_opts, index=idx_tr)
                            with col4:
                                edit_date = st.date_input("Data", value=datetime.strptime(original_date, "%Y-%m-%d %H:%M:%S").date())

                            col_upd, col_del = st.columns(2)
                            with col_upd:
                                update_btn = st.form_submit_button("Atualizar")
                            with col_del:
                                delete_btn = st.form_submit_button("Deletar")

                        if update_btn:
                            new_dt = datetime.combine(edit_date, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
                            q_upd = """
                                UPDATE public.tb_estoque
                                SET "Produto"=%s, "Quantidade"=%s, "Transação"=%s, "Data"=%s
                                WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                            """
                            success = run_query(q_upd, (
                                edit_prod, edit_qty, edit_trans, new_dt,
                                original_product, original_trans, original_date
                            ), commit=True)
                            if success:
                                st.toast("Estoque atualizado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao atualizar estoque.")

                        if delete_btn:
                            q_del = """
                                DELETE FROM public.tb_estoque
                                WHERE "Produto"=%s AND "Transação"=%s AND "Data"=%s
                            """
                            success = run_query(q_del, (original_product, original_trans, original_date), commit=True)
                            if success:
                                st.toast("Registro deletado com sucesso!")
                                refresh_data()
                            else:
                                st.error("Falha ao deletar registro.")
        else:
            st.info("Nenhuma movimentação de estoque encontrada.")

def clients_page():
    """Página para gerenciar clientes."""
    st.title("Clientes")
    tabs = st.tabs(["Novo Cliente", "Listagem de Clientes"])

    with tabs[0]:
        st.subheader("Registrar Novo Cliente")
        with st.form(key='client_form'):
            nome_completo = st.text_input("Nome Completo")
            submit_client = st.form_submit_button("Registrar Cliente")

        if submit_client:
            if nome_completo:
                try:
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
                    success = run_query(q_ins, (nome_completo, data_nasc, genero, telefone, email, endereco), commit=True)
                    if success:
                        st.toast("Cliente registrado com sucesso!")
                        refresh_data()
                    else:
                        st.error("Falha ao registrar cliente.")
                except Exception as e:
                    st.error(f"Erro ao registrar cliente: {e}")
            else:
                st.warning("Informe o nome completo.")

    with tabs[1]:
        st.subheader("Todos os Clientes")
        try:
            clients_data = run_query("SELECT nome_completo, email FROM public.tb_clientes ORDER BY data_cadastro DESC;")
            if clients_data:
                cols = ["Full Name", "Email"]
                df_clients = pd.DataFrame(clients_data, columns=cols)
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
                                success = run_query(q_upd, (edit_name, original_email), commit=True)
                                if success:
                                    st.toast("Cliente atualizado com sucesso!")
                                    refresh_data()
                                else:
                                    st.error("Falha ao atualizar cliente.")

                        if delete_btn:
                            try:
                                q_del = "DELETE FROM public.tb_clientes WHERE email=%s"
                                success = run_query(q_del, (original_email,), commit=True)
                                if success:
                                    st.toast("Cliente deletado com sucesso!")
                                    refresh_data()
                                    st.experimental_rerun()
                                else:
                                    st.error("Falha ao deletar cliente.")
                            except Exception as e:
                                st.error(f"Erro ao deletar cliente: {e}")
            else:
                st.info("Nenhum cliente encontrado.")
        except Exception as e:
            st.error(f"Erro ao carregar clientes: {e}")

###############################################################################
#          FUNÇÕES NECESSÁRIAS PARA A PÁGINA CASH (INVOICE E PAGAMENTO)
###############################################################################
def process_payment(client: str, payment_status: str) -> None:
    """
    Atualiza o status dos pedidos 'em aberto' para um status de pagamento.
    Exemplo: 'Received - Debited', 'Received - Credit', etc.
    """
    query = """
        UPDATE public.tb_pedido
        SET status=%s, "Data"=CURRENT_TIMESTAMP
        WHERE "Cliente"=%s AND status='em aberto'
    """
    success = run_query(query, (payment_status, client), commit=True)
    if success:
        method = payment_status.split('-')[-1].strip()
        st.toast(f"Pagamento via {method} processado com sucesso!")
    else:
        st.error("Falha ao processar pagamento.")

def generate_invoice_for_printer(df: pd.DataFrame) -> None:
    """
    Gera uma representação textual da nota fiscal para 'impressão'.
    Altere se quiser uma abordagem PDF ou layout diferente.
    """
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

    df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
    grouped_df = df.groupby("Produto").agg({"Quantidade": "sum", "total": "sum"}).reset_index()
    total_general = 0
    for _, row in grouped_df.iterrows():
        description = f"{row['Produto'][:20]:<20}"
        quantity = f"{int(row['Quantidade']):>5}"
        total_item = row["total"]
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
#                          CÓDIGO DA PÁGINA CASH
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

            df["total"] = pd.to_numeric(df["total"], errors="coerce").fillna(0)
            total_sem_desconto = df["total"].sum()

            cupons_validos = {
                "10": 0.10,  "15": 0.15,  "20": 0.20,  "25": 0.25,
                "30": 0.30,  "35": 0.35,  "40": 0.40,  "45": 0.45,
                "50": 0.50,  "55": 0.55,  "60": 0.60,  "65": 0.65,
                "70": 0.70,  "75": 0.75,  "80": 0.80,  "85": 0.85,
                "90": 0.90,  "95": 0.95,  "100": 1.00,
            }
            coupon_code = st.text_input("CUPOM (desconto opcional)")
            desconto_aplicado = 0.0
            if coupon_code in cupons_validos:
                desconto_aplicado = cupons_validos[coupon_code]
                st.toast(f"Cupom {coupon_code} aplicado! Desconto de {desconto_aplicado*100:.0f}%")

            total_sem_desconto = float(total_sem_desconto or 0)
            desconto_aplicado = float(desconto_aplicado or 0)
            total_com_desconto = total_sem_desconto * (1 - desconto_aplicado)

            # Gera e exibe invoice textual
            generate_invoice_for_printer(df)

            st.write(f"**Total sem desconto:** {format_currency(total_sem_desconto)}")
            st.write(f"**Desconto:** {desconto_aplicado*100:.0f}%")
            st.write(f"**Total com desconto:** {format_currency(total_com_desconto)}")

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
#                         PÁGINA DE ANALYTICS
###############################################################################
def analytics_page():
    """Página de Analytics para visualização de dados detalhados."""
    st.title("Analytics")
    st.subheader("Detalhes dos Pedidos")

    # Query para buscar os dados da view vw_pedido_produto_details
    query = """
        SELECT "Data", "Cliente", "Produto", "Quantidade", "Valor", "Custo_Unitario", 
               "Valor_total", "Custo_total", "Lucro_Liquido", "Fornecedor", "Status"
        FROM public.vw_pedido_produto_details;
    """
    data = run_query(query)

    if data:
        df = pd.DataFrame(data, columns=[
            "Data", "Cliente", "Produto", "Quantidade", "Valor", "Custo_Unitario",
            "Valor_total", "Custo_total", "Lucro_Liquido", "Fornecedor", "Status"
        ])

        # Dropdown para selecionar o cliente
        clientes = df["Cliente"].unique().tolist()
        cliente_selecionado = st.selectbox("Selecione um Cliente", [""] + clientes)

        if cliente_selecionado:
            df_filtrado = df[df["Cliente"] == cliente_selecionado]
        else:
            df_filtrado = df

        st.dataframe(df_filtrado, use_container_width=True)
        download_df_as_csv(df_filtrado, "analytics.csv", label="Baixar Dados Analytics")

        st.subheader("Filtrar por Intervalo de Datas")
        df_filtrado["Data"] = pd.to_datetime(df_filtrado["Data"])

        min_date = df_filtrado["Data"].min().date() if not df_filtrado.empty else None
        max_date = df_filtrado["Data"].max().date() if not df_filtrado.empty else None

        if min_date is None or max_date is None:
            st.error("Não há dados disponíveis para exibir.")
            return

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Data Inicial", min_date, min_value=min_date, max_value=max_date)
        with col2:
            end_date = st.date_input("Data Final", max_date, min_value=min_date, max_value=max_date)

        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)
        df_filtrado = df_filtrado[(df_filtrado["Data"] >= start_date) & (df_filtrado["Data"] <= end_date)]

        st.subheader("Total de Vendas e Lucro Líquido por Dia")
        df_daily = df_filtrado.groupby("Data").agg({
            "Valor_total": "sum",
            "Lucro_Liquido": "sum"
        }).reset_index()
        df_daily = df_daily.sort_values("Data")
        df_daily["Data_formatada"] = df_daily["Data"].dt.strftime("%d/%m/%Y")

        df_daily["Valor_total_formatado"] = df_daily["Valor_total"].apply(
            lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        df_daily["Lucro_Liquido_formatado"] = df_daily["Lucro_Liquido"].apply(
            lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        df_long = df_daily.melt(
            id_vars=["Data", "Data_formatada"],
            value_vars=["Valor_total", "Lucro_Liquido"],
            var_name="Métrica",
            value_name="Valor"
        )

        df_long["Valor_formatado"] = df_long["Valor"].apply(
            lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )

        df_long["Métrica"] = pd.Categorical(
            df_long["Métrica"], categories=["Valor_total", "Lucro_Liquido"], ordered=True
        )

        bars = alt.Chart(df_long).mark_bar(opacity=0.7).encode(
            x=alt.X("Data_formatada:N", title="Data", sort=alt.SortField("Data")),
            y=alt.Y("Valor:Q", title="Valor (R$)"),
            color=alt.Color("Métrica:N", title="Métrica", scale=alt.Scale(
                domain=["Valor_total", "Lucro_Liquido"],
                range=["gray", "#bcbd22"]
            )),
            order=alt.Order("Métrica:N", sort="ascending"),
            tooltip=["Data_formatada", "Métrica", "Valor_formatado"]
        ).properties(
            width=800,
            height=400
        )

        text_valor_total = alt.Chart(df_long[df_long["Métrica"] == "Valor_total"]).mark_text(
            align="center",
            baseline="bottom",
            dy=-10,
            color="white",
            fontSize=12
        ).encode(
            x="Data_formatada:N",
            y="Valor:Q",
            text="Valor_formatado:N"
        )

        text_lucro_liquido = alt.Chart(df_long[df_long["Métrica"] == "Lucro_Liquido"]).mark_text(
            align="center",
            baseline="top",
            dy=10,
            color="white",
            fontSize=12
        ).encode(
            x="Data_formatada:N",
            y="Valor:Q",
            text="Valor_formatado:N"
        )

        chart = (bars + text_valor_total + text_lucro_liquido).interactive()
        st.altair_chart(chart, use_container_width=True)

        st.subheader("Totais no Intervalo Selecionado")
        soma_valor_total = df_filtrado["Valor_total"].sum()
        soma_lucro_liquido = df_filtrado["Lucro_Liquido"].sum()

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Soma Valor Total", format_currency(soma_valor_total))
        with col2:
            st.metric("Soma Lucro Líquido", format_currency(soma_lucro_liquido))

        st.subheader("Produtos Mais Lucrativos")
        query_produtos = """
            SELECT "Produto", "Total_Quantidade", "Total_Valor", "Total_Lucro"
            FROM public.vw_vendas_produto;
        """
        data_produtos = run_query(query_produtos)
        if data_produtos:
            df_produtos = pd.DataFrame(data_produtos, columns=[
                "Produto", "Total_Quantidade", "Total_Valor", "Total_Lucro"
            ])
            df_produtos = df_produtos.sort_values("Total_Lucro", ascending=False)
            df_produtos_top5 = df_produtos.head(5)
            df_produtos_top5["Total_Lucro_formatado"] = df_produtos_top5["Total_Lucro"].apply(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            )

            chart_produtos = alt.Chart(df_produtos_top5).mark_bar(color="gray").encode(
                x=alt.X("Total_Lucro:Q", title="Lucro Total (R$)"),
                y=alt.Y("Produto:N", title="Produto", sort="-x"),
                tooltip=["Produto", "Total_Lucro_formatado"]
            ).properties(
                width=800,
                height=400,
                title="Top 5 Produtos Mais Lucrativos"
            ).interactive()

            st.altair_chart(chart_produtos, use_container_width=True)
        else:
            st.info("Nenhum dado encontrado na view vw_vendas_produto.")
    else:
        st.info("Nenhum dado encontrado na view vw_pedido_produto_details.")

def events_calendar_page():
    """Página para gerenciar o calendário de eventos."""
    st.title("Calendário de Eventos")

    def get_events_from_db():
        query = """
            SELECT id, nome, descricao, data_evento, inscricao_aberta, data_criacao
            FROM public.tb_eventos
            ORDER BY data_evento;
        """
        rows = run_query(query)
        return rows if rows else []

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
            success = run_query(q_insert, (nome_evento, descricao_evento, data_evento, inscricao_aberta), commit=True)
            if success:
                st.toast("Evento cadastrado com sucesso!")
                st.experimental_rerun()
            else:
                st.error("Falha ao cadastrar evento.")
        else:
            st.warning("Informe ao menos o nome do evento.")

    st.markdown("---")

    current_date = date.today()
    ano_padrao = current_date.year
    mes_padrao = current_date.month

    col_ano, col_mes = st.columns(2)
    with col_ano:
        ano_selecionado = st.selectbox(
            "Selecione o Ano",
            list(range(ano_padrao - 2, ano_padrao + 3)),
            index=2
        )
    with col_mes:
        meses_nomes = [calendar.month_name[i] for i in range(1, 13)]
        mes_selecionado = st.selectbox(
            "Selecione o Mês",
            options=list(range(1, 13)),
            format_func=lambda x: meses_nomes[x-1],
            index=mes_padrao - 1
        )

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

    st.subheader("Visualização do Calendário")
    cal = calendar.HTMLCalendar(firstweekday=0)
    html_calendario = cal.formatmonth(ano_selecionado, mes_selecionado)

    for ev in df_filtrado.itertuples():
        dia = ev.data_evento.day
        highlight_str = (
            f' style="background-color:#1b4f72; color:white; font-weight:bold;" '
            f'title="{ev.nome}: {ev.descricao}"'
        )
        for day_class in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]:
            target = f'<td class="{day_class}">{dia}</td>'
            replacement = f'<td class="{day_class}"{highlight_str}>{dia}</td>'
            html_calendario = html_calendario.replace(target, replacement)

    st.markdown(
        """
        <style>
        table {
            width: 80%;
            margin-left: auto;
            margin-right: auto;
            border-collapse: collapse;
            font-size: 12px;
        }
        th {
            background-color: #1b4f72;
            color: white;
            padding: 5px;
        }
        td {
            width: 14.28%;
            height: 60px;
            text-align: center;
            vertical-align: top;
            border: 1px solid #ddd;
        }
        @media only screen and (max-width: 600px) {
            table {
                width: 100%;
                font-size: 10px;
            }
            td {
                height: 40px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True
    )
    st.markdown(html_calendario, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

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
        df_display = df_display[["Data", "Descrição"]]

        styled_df_events = df_display.style.set_table_styles([
            {'selector': 'th', 'props': [('background-color', '#ff4c4c'), ('color', 'white'), ('padding', '8px')]},
            {'selector': 'td', 'props': [('padding', '8px'), ('text-align', 'left')]}
        ])
        st.write(styled_df_events)

    st.markdown("---")
    st.subheader("Editar / Excluir Eventos")

    df_events["evento_label"] = df_events.apply(
        lambda row: f'{row["id"]} - {row["nome"]} ({row["data_evento"].strftime("%Y-%m-%d")})',
        axis=1
    )
    events_list = [""] + df_events["evento_label"].tolist()
    selected_event = st.selectbox("Selecione um evento:", events_list)

    if selected_event:
        event_id_str = selected_event.split(" - ")[0]
        try:
            event_id = int(event_id_str)
        except ValueError:
            st.error("Falha ao interpretar ID do evento.")
            return

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
                        success = run_query(q_update, (new_nome, new_desc, new_data, new_insc, event_id), commit=True)
                        if success:
                            st.toast("Evento atualizado com sucesso!")
                            st.experimental_rerun()
                        else:
                            st.error("Falha ao atualizar evento.")
                    else:
                        st.warning("O campo Nome do Evento não pode ficar vazio.")

            with col_btn2:
                if st.button("Excluir Evento"):
                    q_delete = "DELETE FROM public.tb_eventos WHERE id=%s;"
                    success = run_query(q_delete, (event_id,), commit=True)
                    if success:
                        st.toast(f"Evento ID={event_id} excluído com sucesso!")
                        st.experimental_rerun()
                    else:
                        st.error("Falha ao excluir evento.")
    else:
        st.info("Selecione um evento para editar ou excluir.")

def loyalty_program_page():
    """Página do programa de fidelidade."""
    st.title("Programa de Fidelidade")

    query = 'SELECT "Cliente", total_geral FROM public.vw_cliente_sum_total;'
    data = run_query(query)
    if data:
        df = pd.DataFrame(data, columns=["Cliente", "Total Geral"])
        st.subheader("Clientes - Fidelidade")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Nenhum dado encontrado na view vw_cliente_sum_total.")

    st.markdown("---")
    st.subheader("Acumule pontos a cada compra!")
    if 'points' not in st.session_state:
        st.session_state.points = 0

    points_earned = st.number_input("Pontos a adicionar", min_value=0, step=1)
    if st.button("Adicionar Pontos"):
        st.session_state.points += points_earned
        st.toast(f"Pontos adicionados! Total: {st.session_state.points}")

    if st.button("Resgatar Prêmio"):
        if st.session_state.points >= 100:
            st.session_state.points -= 100
            st.toast("Prêmio resgatado com sucesso!")
        else:
            st.error("Pontos insuficientes.")

def settings_page():
    """Página de configurações para salvar/atualizar dados da empresa."""
    st.title("Settings")

    last_settings = st.session_state.get("last_settings", None)

    if last_settings:
        st.markdown(f"**Company:** {last_settings[1]}")
        st.markdown(f"**Address:** {last_settings[2]}")
        st.markdown(f"**CNPJ/CPF:** {last_settings[3]}")
        st.markdown(f"**Email:** {last_settings[4]}")
        st.markdown(f"**Telephone:** {last_settings[5]}")
        st.markdown(f"**Contract Number:** {last_settings[6]}")

    st.subheader("Configurações da Empresa")

    with st.form(key='settings_form'):
        company = st.text_input("Company", value=last_settings[1] if last_settings else "")
        address = st.text_input("Address", value=last_settings[2] if last_settings else "")
        cnpj_cpf = st.text_input("CNPJ/CPF", value=last_settings[3] if last_settings else "")
        email = st.text_input("Email", value=last_settings[4] if last_settings else "")
        telephone = st.text_input("Telephone", value=last_settings[5] if last_settings else "")
        contract_number = st.text_input("Contract Number", value=last_settings[6] if last_settings else "")

        submit_settings = st.form_submit_button("Update Registration")

    if submit_settings:
        if last_settings:
            q_upd = """
                UPDATE public.tb_settings
                SET company=%s, address=%s, cnpj_cpf=%s, email=%s,
                    telephone=%s, contract_number=%s, created_at=CURRENT_TIMESTAMP
                WHERE id=%s
            """
            success = run_query(
                q_upd,
                (company, address, cnpj_cpf, email, telephone, contract_number, last_settings[0]),
                commit=True
            )
            if success:
                st.success("Record updated successfully!")
                get_latest_settings.clear()
                st.session_state.last_settings = get_latest_settings()
            else:
                st.error("Failed to update record.")
        else:
            if company.strip():
                q_ins = """
                    INSERT INTO public.tb_settings
                        (company, address, cnpj_cpf, email, telephone, contract_number)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """
                success = run_query(q_ins, (company, address, cnpj_cpf, email, telephone, contract_number), commit=True)
                if success:
                    st.success("Record inserted successfully!")
                    get_latest_settings.clear()
                    st.session_state.last_settings = get_latest_settings()
                else:
                    st.error("Failed to save record.")
            else:
                st.warning("Please provide at least the Company name.")

###############################################################################
#                     INICIALIZAÇÃO E MAIN
###############################################################################
def initialize_session_state():
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'last_settings' not in st.session_state:
        st.session_state.last_settings = get_latest_settings()

def apply_custom_css():
    st.markdown(
        """
        <style>
        /* Estilo geral */
        .css-1d391kg {
            font-size: 2em;
            color: #ff4c4c;
        }
        .stDataFrame table {
            width: 100%;
            overflow-x: auto;
        }
        .css-1aumxhk {
            background-color: #ff4c4c;
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
        /* Botões */
        .btn {
            background-color: #ff4c4c !important;
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
            background-color: #cc0000 !important;
        }
        /* Placeholder estilizado */
        input::placeholder {
            color: #bbb;
            font-size: 0.875rem;
        }
        /* Remove espaço entre os input boxes do login */
        .css-1siy2j8 input {
            margin-bottom: 0 !important;
            padding-top: 4px;
            padding-bottom: 4px;
        }
        /* Tabela responsiva */
        @media only screen and (max-width: 600px) {
            table {
                font-size: 10px;
            }
            th, td {
                padding: 4px;
            }
        }
        </style>
        <div class='css-1v3fvcr'>© 2025 | Todos os direitos reservados | Boituva Beach Club</div>
        """,
        unsafe_allow_html=True
    )

def sidebar_navigation():
    with st.sidebar:
        selected = option_menu(
            "Bar Menu",
            [
                "Home", "Orders", "Products", "Stock", "Clients",
                "Cash", "Analytics", "Calendário de Eventos",
                "Settings"
            ],
            icons=[
                "house", "file-text", "box", "list-task", "layers",
                "receipt", "bar-chart", "calendar", "gear"
            ],
            menu_icon="cast",
            default_index=0,
            styles={
                "container": {"background-color": "#1b4f72"},
                "icon": {"color": "white", "font-size": "18px"},
                "nav-link": {
                    "font-size": "14px", "text-align": "left", "margin": "0px",
                    "color": "white", "--hover-color": "#184563"
                },
                "nav-link-selected": {"background-color": "#184563", "color": "white"},
            }
        )
        if 'login_time' in st.session_state:
            st.write(
                f"{st.session_state.username} logged in at {st.session_state.login_time.strftime('%H:%M')}"
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
    elif selected_page == "Analytics":
        analytics_page()
    elif selected_page == "Programa de Fidelidade":
        loyalty_program_page()
    elif selected_page == "Calendário de Eventos":
        events_calendar_page()
    elif selected_page == "Settings":
        settings_page()

    with st.sidebar:
        if st.button("Logout"):
            for key in ["home_page_initialized"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.session_state.logged_in = False
            st.toast("Desconectado com sucesso!")
            st.experimental_rerun()

def login_page():
    from PIL import Image
    import requests
    from io import BytesIO
    from datetime import datetime

    st.markdown(
        """
        <style>
        .block-container {
            max-width: 450px;
            margin: 0 auto;
            padding-top: 40px;
        }
        .css-18e3th9 {
            font-size: 1.75rem;
            font-weight: 600;
            text-align: center;
        }
        .btn {
            background-color: #ff4c4c !important; 
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
            background-color: #cc0000 !important; 
        }
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
        /* Reduz a distância entre os campos de texto (username e password) */
        .css-1siy2j8 {
            gap: 0.1rem !important; 
        }
        .css-1siy2j8 input {
            margin-bottom: 0 !important; 
            padding-top: 4px;
            padding-bottom: 4px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    logo_url = "https://via.placeholder.com/300x100?text=Boituva+Beach+Club"
    logo = None
    try:
        resp = requests.get(logo_url, timeout=5)
        if resp.status_code == 200:
            logo = Image.open(BytesIO(resp.content))
    except Exception:
        pass

    if logo:
        st.image(logo, use_column_width=True)

    st.markdown("<p style='text-align: center;'>🌴keep the beach vibes flowing!🎾</p>", unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        username_input = st.text_input("", placeholder="Username")
        password_input = st.text_input("", type="password", placeholder="Password")
        btn_login = st.form_submit_button("Log in")

    if btn_login:
        if not username_input or not password_input:
            st.error("Por favor, preencha todos os campos.")
        else:
            try:
                creds = st.secrets["credentials"]
                admin_user = creds["admin_username"]
                admin_pass = creds["admin_password"]
                caixa_user = creds["caixa_username"]
                caixa_pass = creds["caixa_password"]
            except KeyError:
                st.error("Credenciais não encontradas em st.secrets['credentials']. Verifique a configuração.")
                st.stop()

            import hmac

            def verify_credentials(input_user, input_pass, actual_user, actual_pass):
                return hmac.compare_digest(input_user, actual_user) and hmac.compare_digest(input_pass, actual_pass)

            if verify_credentials(username_input, password_input, admin_user, admin_pass):
                st.session_state.logged_in = True
                st.session_state.username = "admin"
                st.session_state.login_time = datetime.now()
                st.toast("Login bem-sucedido como ADMIN!")
                st.experimental_rerun()
            elif verify_credentials(username_input, password_input, caixa_user, caixa_pass):
                st.session_state.logged_in = True
                st.session_state.username = "caixa"
                st.session_state.login_time = datetime.now()
                st.toast("Login bem-sucedido como CAIXA!")
                st.experimental_rerun()
            else:
                st.error("Usuário ou senha incorretos.")

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
