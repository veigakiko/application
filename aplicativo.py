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
    json_data = df.to_json(orient='records', lines=False)
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
#                               PÁGINAS
###############################################################################

def home_page():
    """Página inicial do aplicativo."""
    last_settings = st.session_state.get("last_settings", None)

    if last_settings:
        company_value = last_settings[1]  
        address_value = last_settings[2]  
        telephone_value = last_settings[5]

        st.markdown(f"<h1 style='text-align:center;'>{company_value}</h1>", unsafe_allow_html=True)
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
        st.markdown("<h1 style='text-align:center;'>Home</h1>", unsafe_allow_html=True)

    # Exemplo de calendário e eventos: (Adapte conforme seu código real)
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

def orders_page():
    """Página para gerenciar pedidos."""
    st.title("Gerenciar Pedidos")
    tabs = st.tabs(["Novo Pedido", "Listagem de Pedidos"])

    # ------------------------------------------------------------------
    # Aba 0: Novo Pedido
    # ------------------------------------------------------------------
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
                    VALUES (%s, %s, %s, %s, 'em aberto')
                """
                success = run_query(query_insert, (customer_name, product, quantity, datetime.now()), commit=True)
                if success:
                    st.toast("Pedido registrado com sucesso!")
                    refresh_data()
                    st.experimental_rerun()
                else:
                    st.error("Falha ao registrar pedido.")
            else:
                st.warning("Preencha todos os campos.")

        st.subheader("Últimos 5 Pedidos Registrados")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            df_recent_orders = pd.DataFrame(
                orders_data, columns=["Cliente", "Produto", "Quantidade", "Data", "Status"]
            ).head(5)
            st.write(df_recent_orders)
        else:
            st.info("Nenhum pedido encontrado.")

    # ------------------------------------------------------------------
    # Aba 1: Listagem de Pedidos
    # ------------------------------------------------------------------
    with tabs[1]:
        st.subheader("Listagem de Pedidos")
        orders_data = st.session_state.data.get("orders", [])
        if orders_data:
            cols = ["Cliente", "Produto", "Quantidade", "Data", "Status"]
            df_orders = pd.DataFrame(orders_data, columns=cols)
            st.dataframe(df_orders, use_container_width=True)
            download_df_as_csv(df_orders, "orders.csv", label="Baixar Pedidos CSV")

            # Editar ou Deletar se admin
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
                                idx_prod = product_list.index(original_product) if original_product in product_list else 0
                                edit_prod = st.selectbox("Produto", product_list, index=idx_prod)

                            with col2:
                                edit_qty = st.number_input("Quantidade", min_value=1, step=1, value=int(original_qty))

                            with col3:
                                status_opts = [
                                    "em aberto", "Received - Debited", "Received - Credit",
                                    "Received - Pix", "Received - Cash"
                                ]
                                if original_status in status_opts:
                                    idx_st = status_opts.index(original_status)
                                else:
                                    idx_st = 0
                                edit_status = st.selectbox("Status", status_opts, index=idx_st)

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
                                st.experimental_rerun()
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
                                st.experimental_rerun()
                            else:
                                st.error("Falha ao atualizar pedido.")
        else:
            st.info("Nenhum pedido encontrado.")

def process_payment(client: str, payment_status: str):
    """
    Atualiza o status dos pedidos em aberto e força refresh + rerun
    para que a página 'orders' exiba o novo status.
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
        refresh_data()
        st.experimental_rerun()
    else:
        st.error("Falha ao processar pagamento.")

def generate_invoice_for_printer(df: pd.DataFrame):
    """
    Mostra uma 'nota fiscal' textual. Você pode adaptar para gerar PDF.
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

            total_com_desconto = total_sem_desconto * (1 - desconto_aplicado)

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

def analytics_page():
    """Página de Analytics para visualização de dados detalhados."""
    st.title("Analytics")
    st.subheader("Detalhes dos Pedidos")

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

        cliente_selecionado = st.selectbox(
            "Selecione um Cliente", [""] + df["Cliente"].unique().tolist()
        )
        if cliente_selecionado:
            df_filtrado = df[df["Cliente"] == cliente_selecionado]
        else:
            df_filtrado = df

        st.dataframe(df_filtrado, use_container_width=True)
        download_df_as_csv(df_filtrado, "analytics.csv", label="Baixar Dados Analytics")

        st.subheader("Filtrar por Intervalo de Datas")
        df_filtrado["Data"] = pd.to_datetime(df_filtrado["Data"])

        if not df_filtrado.empty:
            min_date = df_filtrado["Data"].min().date()
            max_date = df_filtrado["Data"].max().date()
        else:
            st.warning("Nenhum dado para filtrar.")
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
        ).properties(width=800, height=400)

        text_valor_total = alt.Chart(df_long[df_long["Métrica"] == "Valor_total"]).mark_text(
            align="center",
            baseline="bottom",
            dy=-10,
            color="white",
            fontSize=12
        ).encode(x="Data_formatada:N", y="Valor:Q", text="Valor_formatado:N")

        text_lucro_liquido = alt.Chart(df_long[df_long["Métrica"] == "Lucro_Liquido"]).mark_text(
            align="center",
            baseline="top",
            dy=10,
            color="white",
            fontSize=12
        ).encode(x="Data_formatada:N", y="Valor:Q", text="Valor_formatado:N")

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
            ).properties(width=800, height=400, title="Top 5 Produtos Mais Lucrativos").interactive()

            st.altair_chart(chart_produtos, use_container_width=True)
        else:
            st.info("Nenhum dado encontrado na view vw_vendas_produto.")
    else:
        st.info("Nenhum dado encontrado na view vw_pedido_produto_details.")

def events_calendar_page():
    """Página para gerenciar o calendário de eventos."""
    st.title("Calendário de Eventos")
    # Implemente com base no seu snippet de eventos

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
        input::placeholder {
            color: #bbb;
            font-size: 0.875rem;
        }
        .css-1siy2j8 input {
            margin-bottom: 0 !important;
            padding-top: 4px;
            padding-bottom: 4px;
        }
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
                f"{st.session_state.username} logged in at "
                f"{st.session_state.login_time.strftime('%H:%M')}"
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
    """Página de login do aplicativo."""
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
        input::placeholder {
            color: #bbb;
            font-size: 0.875rem;
        }
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
