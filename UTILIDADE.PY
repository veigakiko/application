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
# UTILIDADES / HELPERS
###############################################################################
def format_currency(value: float) -> str:
    """
    Formata um valor numérico no padrão de moeda brasileiro.
    Exemplo: 1234.56 -> 'R$ 1.234,56'
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Exibe um botão no Streamlit para download do DataFrame como arquivo CSV.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    """
    Exibe um botão no Streamlit para download do DataFrame como arquivo Excel.
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
    Exibe um botão no Streamlit para download do DataFrame como arquivo JSON.
    """
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")


def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    """
    Exibe um botão no Streamlit para download do DataFrame como arquivo HTML.
    """
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")


def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    """
    Exibe um botão no Streamlit para download do DataFrame como arquivo Parquet.
    """
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


def convert_df_to_pdf(df: pd.DataFrame) -> bytes:
    """
    Converte um DataFrame em bytes de PDF usando a biblioteca FPDF.
    Retorna o conteúdo binário do PDF.
    """
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
    """
    Faz upload de um arquivo PDF (bytes) para o serviço file.io e
    retorna a URL gerada para download.
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
                st.error("Falha no upload do arquivo (file.io não retornou sucesso).")
                return ""
        else:
            st.error("Erro ao conectar com o serviço file.io.")
            return ""
    except Exception as e:
        st.error(f"Erro ao fazer upload do arquivo: {e}")
        return ""


###############################################################################
# CONEXÃO E CONSULTAS AO BANCO
###############################################################################
@st.cache_resource
def get_db_connection():
    """
    Cria uma conexão com o banco PostgreSQL a partir dos secrets fornecidos.
    A conexão é cacheada para evitar abertura repetida.
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


def run_query(query: str, values=None, commit: bool = False):
    """
    Executa uma consulta SQL. Se commit=True, o comando é comitado (INSERT/UPDATE/DELETE).
    Caso contrário, retorna os resultados da consulta (SELECT).
    """
    conn = get_db_connection()
    if conn is None:
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
        conn.rollback()
        st.error(f"Erro ao executar a consulta: {e}")
        return None
    finally:
        conn.close()


###############################################################################
# CARREGAMENTO E REFRESH DE DADOS (COM CACHING)
###############################################################################
@st.cache_data
def load_all_data():
    """
    Carrega todos os dados necessários do banco para a aplicação
    e retorna em um dicionário. Utiliza cache para evitar leituras frequentes.
    """
    data = {}
    try:
        orders_query = (
            'SELECT "Cliente", "Produto", "Quantidade", "Data", status '
            'FROM public.tb_pedido ORDER BY "Data" DESC'
        )
        products_query = (
            'SELECT supplier, product, quantity, unit_value, total_value, creation_date '
            'FROM public.tb_products ORDER BY creation_date DESC'
        )
        clients_query = (
            'SELECT DISTINCT "Cliente" '
            'FROM public.tb_pedido ORDER BY "Cliente"'
        )
        stock_query = (
            'SELECT "Produto", "Quantidade", "Transação", "Data" '
            'FROM public.tb_estoque ORDER BY "Data" DESC'
        )

        data["orders"] = run_query(orders_query) or []
        data["products"] = run_query(products_query) or []
        data["clients"] = run_query(clients_query) or []
        data["stock"] = run_query(stock_query) or []
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
    return data


def refresh_data():
    """
    Limpa o cache de dados e recarrega tudo, atualizando o st.session_state.data.
    """
    load_all_data.clear()
    st.session_state.data = load_all_data()


###############################################################################
# FUNÇÕES DE PÁGINAS
###############################################################################
def events_calendar_page():
    """
    Página que exibe um calendário de eventos fictícios,
    permitindo inscrição em cada evento dentro de um range de datas.
    """
    st.title("Calendário de Eventos")

    def fetch_events(start_date, end_date):
        # Eventos estáticos de exemplo
        return pd.DataFrame({
            "Nome do Evento": ["Torneio de Beach Tennis", "Aula de Estratégia de Jogo", "Noite de Integração"],
            "Data": [start_date + timedelta(days=i) for i in range(3)],
            "Descrição": [
                "Torneio aberto com premiação para os três primeiros colocados.",
                "Aula com foco em técnicas avançadas de jogo.",
                "Um encontro social para todos os membros do clube."
            ],
            "Inscrição Aberta": [True, True, False]
        })

    today = datetime.now().date()
    start_date = st.date_input("De:", today)
    end_date = st.date_input("Até:", today + timedelta(days=30))

    if start_date > end_date:
        st.error("A data de início deve ser anterior à data de término.")
    else:
        events_df = fetch_events(start_date, end_date)
        if not events_df.empty:
            for _, row in events_df.iterrows():
                st.subheader(f"{row['Nome do Evento']} ({row['Data'].strftime('%d/%m/%Y')})")
                st.write(f"Descrição: {row['Descrição']}")
                if row['Inscrição Aberta']:
                    if st.button(f"Inscrever-se em {row['Nome do Evento']}", key=row['Nome do Evento']):
                        st.success(f"Inscrição confirmada para {row['Nome do Evento']}!")
                else:
                    st.info("Inscrições encerradas para este evento.")
        else:
            st.write("Não há eventos programados para este período.")


def menu_page():
    """
    Página de Cardápio: carrega as categorias e exibe produtos por categoria.
    """
    st.title("Cardápio")
    categories = run_query("SELECT DISTINCT categoria FROM public.tb_products ORDER BY categoria")
    category_list = [row[0] for row in categories] if categories else []

    selected_category = st.selectbox("Selecione a Categoria", [""] + category_list)
    if selected_category:
        query = """
            SELECT product, description, price 
            FROM public.tb_products 
            WHERE categoria = %s
        """
        products = run_query(query, (selected_category,))
        if products:
            for product in products:
                st.subheader(product[0])
                st.write(f"Descrição: {product[1]}")
                st.write(f"Preço: {format_currency(product[2])}")
        else:
            st.warning("Nenhum produto encontrado para esta categoria.")


def settings_page():
    """
    Página de Configurações e Ajustes de conta e preferências de aplicativo.
    """
    st.title("Configurações e Ajustes")
    st.subheader("Ajustes de Conta")

    if 'username' in st.session_state:
        new_username = st.text_input("Alterar nome de usuário", st.session_state.username)
        if st.button("Salvar Nome de Usuário"):
            st.session_state.username = new_username
            st.success("Nome de usuário atualizado!")

    st.subheader("Preferências do Aplicativo")
    theme_choice = st.radio("Escolha o tema do aplicativo", ('Claro', 'Escuro'))
    if st.button("Salvar Preferências"):
        st.session_state.theme = theme_choice
        st.success("Preferências salvas!")


def loyalty_program_page():
    """
    Página para programa de fidelidade, com sistema simples de pontos e resgates.
    """
    st.title("Programa de Fidelidade")
    st.subheader("Acumule pontos a cada compra!")

    if 'points' not in st.session_state:
        st.session_state.points = 0

    points_earned = st.number_input("Pontos a adicionar", min_value=0, step=1)
    if st.button("Adicionar Pontos"):
        st.session_state.points += points_earned
        st.success(f"Pontos adicionados com sucesso! Total de pontos: {st.session_state.points}")

    if st.button("Resgatar Prêmio"):
        if st.session_state.points >= 100:
            st.session_state.points -= 100
            st.success("Prêmio resgatado com sucesso!")
        else:
            st.error("Pontos insuficientes para resgate.")


def home_page():
    """
    Página Home que exibe dados gerais, notificações sobre pedidos em aberto
    e, para administradores, estatísticas de pedidos e de estoque vs pedidos.
    """
    st.title("🎾 Boituva Beach Club 🎾")
    st.write("📍 Av. Do Trabalhador, 1879 — 🏆 5° Open BBC")

    notification_placeholder = st.empty()
    client_count_query = """
        SELECT COUNT(DISTINCT "Cliente") AS client_count
        FROM public.tb_pedido
        WHERE status = %s
    """
    client_count = run_query(client_count_query, ('em aberto',))

    if client_count and client_count[0][0] > 0:
        notification_placeholder.success(f"Há {client_count[0][0]} clientes com pedidos em aberto!")
    else:
        notification_placeholder.info("Nenhum cliente com pedido em aberto no momento.")

    # Somente administrador vê o resumo de pedidos em aberto e o sumário de estoque
    if st.session_state.get("username") == "admin":
        st.markdown("**Open Orders Summary**")
        open_orders_query = """
            SELECT "Cliente", SUM("total") as Total
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
                    columns=["Product", "Stock_Quantity", "Orders_Quantity", "Total_in_Stock"]
                )
                df_stock_vs_orders.sort_values("Total_in_Stock", ascending=False, inplace=True)
                df_display = df_stock_vs_orders[["Product", "Total_in_Stock"]]

                st.table(df_display)
                total_stock_value = int(df_stock_vs_orders["Total_in_Stock"].sum())
                st.markdown(f"**Total Geral (Stock vs. Orders):** {total_stock_value}")

                # Exemplo de geração de PDF (pode ser adaptado)
                pdf_bytes = convert_df_to_pdf(df_stock_vs_orders)
                st.subheader("Opções de PDF (Exportar)")
                st.download_button(
                    label="Baixar PDF",
                    data=pdf_bytes,
                    file_name="stock_vs_orders_summary.pdf",
                    mime="application/pdf"
                )
            else:
                st.info("Não há dados na view vw_stock_vs_orders_summary.")
        except Exception as e:
            st.error(f"Erro ao gerar o resumo Stock vs. Orders: {e}")


def orders_page():
    """
    Página de pedidos: permite registrar novos pedidos e, caso seja administrador,
    editar e deletar pedidos existentes.
    """
    st.title("Orders")
    st.subheader("Registrar novo pedido")

    product_data = st.session_state.data.get("products", [])
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products available"]

    with st.form(key='order_form'):
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo')
        customer_list = [""] + [row[0] for row in clientes] if clientes else []

        col1, col2, col3 = st.columns(3)
        with col1:
            customer_name = st.selectbox("Customer Name", customer_list, index=0)
        with col2:
            product = st.selectbox("Product", product_list, index=0)
        with col3:
            quantity = st.number_input("Quantity", min_value=1, step=1)

        submit_button = st.form_submit_button(label="Register Order")

    if submit_button:
        if customer_name and product and quantity > 0:
            query = """
                INSERT INTO public.tb_pedido ("Cliente", "Produto", "Quantidade", "Data", status)
                VALUES (%s, %s, %s, %s, 'em aberto')
            """
            timestamp = datetime.now()
            success = run_query(query, (customer_name, product, quantity, timestamp), commit=True)
            if success:
                st.success("Order registrado com sucesso!")
                refresh_data()
            else:
                st.error("Falha ao registrar o pedido.")
        else:
            st.warning("Por favor, preencha todos os campos corretamente.")

    # Exibe todos os pedidos na tabela
    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("All Orders")
        columns = ["Client", "Product", "Quantity", "Date", "Status"]
        df_orders = pd.DataFrame(orders_data, columns=columns)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Download Orders CSV")

        # Se for admin, permite edição e exclusão
        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Order")

            # Cria uma chave única para cada linha
            df_orders["unique_key"] = df_orders.apply(
                lambda row: f"{row['Client']}|{row['Product']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_orders["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select an order to edit/delete:", [""] + unique_keys)

            if selected_key:
                matching_rows = df_orders[df_orders["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple orders found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_client = selected_row["Client"]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_date = selected_row["Date"]
                    original_status = selected_row["Status"]

                    with st.form(key='edit_order_form'):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            edit_product = st.selectbox(
                                "Product",
                                product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input(
                                "Quantity",
                                min_value=1,
                                step=1,
                                value=int(original_quantity)
                            )
                        with col3:
                            edit_status_list = [
                                "em aberto",
                                "Received - Debited",
                                "Received - Credit",
                                "Received - Pix",
                                "Received - Cash"
                            ]
                            if original_status in edit_status_list:
                                edit_status_index = edit_status_list.index(original_status)
                            else:
                                edit_status_index = 0
                            edit_status = st.selectbox("Status", edit_status_list, index=edit_status_index)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_
