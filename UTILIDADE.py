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
    Formata um valor numérico como moeda brasileira.
    Exemplo: 1234.56 -> 'R$ 1.234,56'
    """
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def download_df_as_csv(df: pd.DataFrame, filename: str, label: str = "Baixar CSV"):
    """
    Disponibiliza um botão de download em CSV para um DataFrame no Streamlit.
    """
    csv_data = df.to_csv(index=False)
    st.download_button(label=label, data=csv_data, file_name=filename, mime="text/csv")


def download_df_as_excel(df: pd.DataFrame, filename: str, label: str = "Baixar Excel"):
    """
    Disponibiliza um botão de download em Excel para um DataFrame no Streamlit.
    """
    towrite = BytesIO()
    with pd.ExcelWriter(towrite, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    towrite.seek(0)
    st.download_button(label=label, data=towrite, file_name=filename,
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def download_df_as_json(df: pd.DataFrame, filename: str, label: str = "Baixar JSON"):
    """
    Disponibiliza um botão de download em JSON para um DataFrame no Streamlit.
    """
    json_data = df.to_json(orient='records', lines=True)
    st.download_button(label=label, data=json_data, file_name=filename, mime="application/json")


def download_df_as_html(df: pd.DataFrame, filename: str, label: str = "Baixar HTML"):
    """
    Disponibiliza um botão de download em HTML para um DataFrame no Streamlit.
    """
    html_data = df.to_html(index=False)
    st.download_button(label=label, data=html_data, file_name=filename, mime="text/html")


def download_df_as_parquet(df: pd.DataFrame, filename: str, label: str = "Baixar Parquet"):
    """
    Disponibiliza um botão de download em Parquet para um DataFrame no Streamlit.
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
    Converte um DataFrame para bytes de PDF usando FPDF.
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
    Faz upload de um arquivo PDF em file.io e retorna o link gerado, caso bem-sucedido.
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
            st.error("Erro ao conectar com o serviço de upload (file.io).")
            return ""
    except Exception as e:
        st.error(f"Erro ao fazer upload do arquivo: {e}")
        return ""


###############################################################################
#                            CONEXÃO COM BANCO
###############################################################################
@st.cache_resource
def get_db_connection():
    """
    Cria uma conexão com o PostgreSQL usando st.secrets["db"].
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
    except OperationalError:
        st.error("Não foi possível conectar ao banco de dados. Por favor, tente novamente mais tarde.")
        return None


def run_query(query, values=None, commit: bool = False):
    """
    Executa uma query SQL. Se commit=True, faz INSERT/UPDATE/DELETE. 
    Caso contrário, retorna o resultado de SELECT.
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
#                         CARREGAMENTO DE DADOS (CACHE)
###############################################################################
@st.cache_data
def load_all_data():
    """
    Carrega dados principais do banco, caso existam. Retorna dict com 'orders', 'products',
    'clients' e 'stock'.
    """
    data = {}
    try:
        data["orders"] = run_query(
            'SELECT "Cliente", "Produto", "Quantidade", "Data", status FROM public.tb_pedido ORDER BY "Data" DESC'
        ) or []
        data["products"] = run_query(
            'SELECT supplier, product, quantity, unit_value, total_value, creation_date FROM public.tb_products ORDER BY creation_date DESC'
        ) or []
        data["clients"] = run_query(
            'SELECT DISTINCT "Cliente" FROM public.tb_pedido ORDER BY "Cliente"'
        ) or []
        data["stock"] = run_query(
            'SELECT "Produto", "Quantidade", "Transação", "Data" FROM public.tb_estoque ORDER BY "Data" DESC'
        ) or []
    except Exception as e:
        st.error(f"Erro ao carregar os dados: {e}")
    return data


def refresh_data():
    """
    Força a limpeza do cache e recarrega os dados do banco.
    """
    load_all_data.clear()
    st.session_state.data = load_all_data()


###############################################################################
#                           PÁGINAS DA APLICAÇÃO
###############################################################################
def events_calendar_page():
    """
    Página de Calendário de Eventos (exemplo fictício).
    """
    st.title("Calendário de Eventos")

    def fetch_events(start_date, end_date):
        # Exemplo estático
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
        events = fetch_events(start_date, end_date)
        if not events.empty:
            for _, row in events.iterrows():
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
    Página de Cardápio.
    Carrega categorias de produtos (coluna 'categoria' na tb_products).
    """
    st.title("Cardápio")

    categories = run_query("SELECT DISTINCT categoria FROM public.tb_products ORDER BY categoria;")
    category_list = [row[0] for row in categories] if categories else []

    selected_category = st.selectbox("Selecione a Categoria", [""] + category_list)
    if selected_category:
        query = "SELECT product, description, price FROM public.tb_products WHERE categoria = %s;"
        products = run_query(query, (selected_category,))
        if products:
            for prod in products:
                st.subheader(prod[0])
                st.write(f"Descrição: {prod[1]}")
                st.write(f"Preço: {format_currency(prod[2])}")
        else:
            st.warning("Nenhum produto encontrado para esta categoria.")


def settings_page():
    """
    Página de Configurações e Ajustes.
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
    Página de Programa de Fidelidade simples.
    Usuário acumula pontos e pode resgatar.
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
    Página inicial (Home).
    Exibe resumo de pedidos em aberto, se usuário for admin.
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

    if st.session_state.get("username") == "admin":
        st.markdown("**Open Orders Summary**")
        open_orders_query = """
            SELECT "Cliente", SUM("total") AS Total
            FROM public.vw_pedido_produto
            WHERE status = %s
            GROUP BY "Cliente"
            ORDER BY "Cliente" DESC;
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

                # Exemplo de PDF
                pdf_bytes = convert_df_to_pdf(df_stock_vs_orders)
                st.subheader("Baixar PDF")
                st.download_button(
                    label="Baixar 'Stock vs Orders' em PDF",
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
    Página para registrar e gerenciar pedidos.
    Administradores podem editar e deletar.
    """
    st.title("Orders")
    st.subheader("Register a new order")

    product_data = st.session_state.data.get("products", [])
    product_list = [""] + [row[1] for row in product_data] if product_data else ["No products available"]

    with st.form(key='order_form'):
        clientes = run_query('SELECT nome_completo FROM public.tb_clientes ORDER BY nome_completo;')
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
            VALUES (%s, %s, %s, %s, 'em aberto');
            """
            timestamp = datetime.now()
            success = run_query(query, (customer_name, product, quantity, timestamp), commit=True)
            if success:
                st.success("Order registered successfully!")
                refresh_data()
            else:
                st.error("Failed to register the order.")
        else:
            st.warning("Please fill in all fields correctly.")

    orders_data = st.session_state.data.get("orders", [])
    if orders_data:
        st.subheader("All Orders")
        columns = ["Client", "Product", "Quantity", "Date", "Status"]
        df_orders = pd.DataFrame(orders_data, columns=columns)
        st.dataframe(df_orders, use_container_width=True)
        download_df_as_csv(df_orders, "orders.csv", label="Download Orders CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Order")
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
                            edit_quantity = st.number_input("Quantity", min_value=1, step=1, value=int(original_quantity))
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
                            update_button = st.form_submit_button(label="Update Order")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Order")

                    if delete_button:
                        delete_query = """
                        DELETE FROM public.tb_pedido
                        WHERE "Cliente" = %s AND "Produto" = %s AND "Data" = %s;
                        """
                        success = run_query(delete_query, (original_client, original_product, original_date), commit=True)
                        if success:
                            st.success("Order deleted successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to delete the order.")

                    if update_button:
                        update_query = """
                        UPDATE public.tb_pedido
                        SET "Produto" = %s, "Quantidade" = %s, status = %s
                        WHERE "Cliente" = %s AND "Produto" = %s AND "Data" = %s;
                        """
                        success = run_query(update_query, (
                            edit_product, edit_quantity, edit_status,
                            original_client, original_product, original_date
                        ), commit=True)
                        if success:
                            st.success("Order updated successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to update the order.")
    else:
        st.info("No orders found.")


def products_page():
    """
    Página de Produtos. Administradores podem inserir/editar/deletar.
    """
    st.title("Products")
    st.subheader("Add a new product")

    with st.form(key='product_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            supplier = st.text_input("Supplier", max_chars=100)
        with col2:
            product = st.text_input("Product", max_chars=100)
        with col3:
            quantity = st.number_input("Quantity", min_value=1, step=1)
        with col4:
            unit_value = st.number_input("Unit Value", min_value=0.0, step=0.01, format="%.2f")
        creation_date = st.date_input("Creation Date", value=date.today())
        submit_product = st.form_submit_button(label="Insert Product")

    if submit_product:
        if supplier and product and quantity > 0 and unit_value >= 0:
            query = """
            INSERT INTO public.tb_products (supplier, product, quantity, unit_value, total_value, creation_date)
            VALUES (%s, %s, %s, %s, %s, %s);
            """
            total_value = quantity * unit_value
            success = run_query(query, (supplier, product, quantity, unit_value, total_value, creation_date), commit=True)
            if success:
                st.success("Product added successfully!")
                refresh_data()
            else:
                st.error("Failed to add the product.")
        else:
            st.warning("Please fill in all fields correctly.")

    products_data = st.session_state.data.get("products", [])
    if products_data:
        st.subheader("All Products")
        columns = ["Supplier", "Product", "Quantity", "Unit Value", "Total Value", "Creation Date"]
        df_products = pd.DataFrame(products_data, columns=columns)
        st.dataframe(df_products, use_container_width=True)
        download_df_as_csv(df_products, "products.csv", label="Download Products CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Product")
            df_products["unique_key"] = df_products.apply(
                lambda row: f"{row['Supplier']}|{row['Product']}|{row['Creation Date'].strftime('%Y-%m-%d')}",
                axis=1
            )
            unique_keys = df_products["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select a product to edit/delete:", [""] + unique_keys)
            if selected_key:
                matching_rows = df_products[df_products["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple products found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_supplier = selected_row["Supplier"]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_unit_value = selected_row["Unit Value"]
                    original_creation_date = selected_row["Creation Date"]

                    with st.form(key='edit_product_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_supplier = st.text_input("Supplier", value=original_supplier, max_chars=100)
                        with col2:
                            edit_product = st.text_input("Product", value=original_product, max_chars=100)
                        with col3:
                            edit_quantity = st.number_input("Quantity", min_value=1, step=1,
                                                           value=int(original_quantity))
                        with col4:
                            edit_unit_value = st.number_input(
                                "Unit Value",
                                min_value=0.0,
                                step=0.01,
                                format="%.2f",
                                value=float(original_unit_value)
                            )
                        edit_creation_date = st.date_input("Creation Date", value=original_creation_date)

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Update Product")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Product")

                    if update_button:
                        edit_total_value = edit_quantity * edit_unit_value
                        update_query = """
                        UPDATE public.tb_products
                        SET supplier = %s,
                            product = %s,
                            quantity = %s,
                            unit_value = %s,
                            total_value = %s,
                            creation_date = %s
                        WHERE supplier = %s 
                          AND product = %s 
                          AND creation_date = %s;
                        """
                        success = run_query(update_query, (
                            edit_supplier, edit_product, edit_quantity, edit_unit_value, edit_total_value,
                            edit_creation_date, original_supplier, original_product, original_creation_date
                        ), commit=True)
                        if success:
                            st.success("Product updated successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to update the product.")

                    if delete_button:
                        confirm = st.checkbox("Are you sure you want to delete this product?")
                        if confirm:
                            delete_query = """
                            DELETE FROM public.tb_products
                            WHERE supplier = %s AND product = %s AND creation_date = %s;
                            """
                            success = run_query(delete_query, (original_supplier, original_product, original_creation_date),
                                                commit=True)
                            if success:
                                st.success("Product deleted successfully!")
                                refresh_data()
                            else:
                                st.error("Failed to delete the product.")
    else:
        st.info("No products found.")


def stock_page():
    """
    Página para registrar e visualizar entradas/saídas de estoque.
    """
    st.title("Stock")
    st.subheader("Add a new stock record")
    st.write(
        """
        Esta página foi projetada para registrar **apenas entradas ou saídas de produtos** 
        no estoque de forma organizada.
        """
    )

    product_data = run_query("SELECT product FROM public.tb_products ORDER BY product;")
    product_list = [row[0] for row in product_data] if product_data else ["No products available"]

    with st.form(key='stock_form'):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            product = st.selectbox("Product", product_list)
        with col2:
            quantity = st.number_input("Quantity", min_value=1, step=1)
        with col3:
            transaction = st.selectbox("Transaction Type", ["Entrada", "Saída"])
        with col4:
            date_input = st.date_input("Date", value=datetime.now().date())
        submit_stock = st.form_submit_button(label="Register")

    if submit_stock:
        if product and quantity > 0:
            current_datetime = datetime.combine(date_input, datetime.min.time())
            query = """
            INSERT INTO public.tb_estoque ("Produto", "Quantidade", "Transação", "Data")
            VALUES (%s, %s, %s, %s);
            """
            success = run_query(query, (product, quantity, transaction, current_datetime), commit=True)
            if success:
                st.success("Stock record added successfully!")
                refresh_data()
            else:
                st.error("Failed to add stock record.")
        else:
            st.warning("Please select a product and enter a quantity > 0.")

    stock_data = st.session_state.data.get("stock", [])
    if stock_data:
        st.subheader("All Stock Records")
        columns = ["Product", "Quantity", "Transaction", "Date"]
        df_stock = pd.DataFrame(stock_data, columns=columns)
        st.dataframe(df_stock, use_container_width=True)
        download_df_as_csv(df_stock, "stock.csv", label="Download Stock CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Stock Record")
            df_stock["unique_key"] = df_stock.apply(
                lambda row: f"{row['Product']}|{row['Transaction']}|{row['Date'].strftime('%Y-%m-%d %H:%M:%S')}",
                axis=1
            )
            unique_keys = df_stock["unique_key"].unique().tolist()
            selected_key = st.selectbox("Select a stock record to edit/delete:", [""] + unique_keys)
            if selected_key:
                matching_rows = df_stock[df_stock["unique_key"] == selected_key]
                if len(matching_rows) > 1:
                    st.warning("Multiple stock records found with the same key. Please refine your selection.")
                else:
                    selected_row = matching_rows.iloc[0]
                    original_product = selected_row["Product"]
                    original_quantity = selected_row["Quantity"]
                    original_transaction = selected_row["Transaction"]
                    original_date = selected_row["Date"]

                    with st.form(key='edit_stock_form'):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            edit_product = st.selectbox(
                                "Product",
                                product_list,
                                index=product_list.index(original_product) if original_product in product_list else 0
                            )
                        with col2:
                            edit_quantity = st.number_input("Quantity", min_value=1, step=1,
                                                           value=int(original_quantity))
                        with col3:
                            edit_transaction = st.selectbox(
                                "Transaction Type",
                                ["Entrada", "Saída"],
                                index=["Entrada", "Saída"].index(original_transaction)
                                if original_transaction in ["Entrada", "Saída"] else 0
                            )
                        with col4:
                            edit_date = st.date_input("Date", value=original_date.date())

                        col_upd, col_del = st.columns(2)
                        with col_upd:
                            update_button = st.form_submit_button(label="Update Stock Record")
                        with col_del:
                            delete_button = st.form_submit_button(label="Delete Stock Record")

                    if update_button:
                        edit_datetime = datetime.combine(edit_date, datetime.min.time())
                        update_query = """
                        UPDATE public.tb_estoque
                        SET "Produto" = %s, "Quantidade" = %s, "Transação" = %s, "Data" = %s
                        WHERE "Produto" = %s AND "Transação" = %s AND "Data" = %s;
                        """
                        success = run_query(update_query, (
                            edit_product, edit_quantity, edit_transaction, edit_datetime,
                            original_product, original_transaction, original_date
                        ), commit=True)
                        if success:
                            st.success("Stock record updated successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to update the stock record.")

                    if delete_button:
                        delete_query = """
                        DELETE FROM public.tb_estoque
                        WHERE "Produto" = %s AND "Transação" = %s AND "Data" = %s;
                        """
                        success = run_query(delete_query, (
                            original_product, original_transaction, original_date
                        ), commit=True)
                        if success:
                            st.success("Stock record deleted successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to delete the stock record.")
    else:
        st.info("No stock records found.")


def clients_page():
    """
    Página de Clientes. Pode cadastrar novo cliente, listar, editar ou excluir (admin).
    """
    st.title("Clients")
    st.subheader("Register a New Client")

    with st.form(key='client_form'):
        nome_completo = st.text_input("Full Name", max_chars=100)
        submit_client = st.form_submit_button(label="Register New Client")

    if submit_client:
        if nome_completo:
            data_nascimento = date(2000, 1, 1)
            genero = "Other"
            telefone = "0000-0000"
            endereco = "Endereço padrão"
            unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
            email = f"{nome_completo.replace(' ', '_').lower()}_{unique_id}@example.com"

            query = """
            INSERT INTO public.tb_clientes (nome_completo, data_nascimento, genero, telefone, 
                                            email, endereco, data_cadastro)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
            """
            success = run_query(query, (nome_completo, data_nascimento, genero, telefone, email, endereco), commit=True)
            if success:
                st.success("Client registered successfully!")
                refresh_data()
            else:
                st.error("Failed to register the client.")
        else:
            st.warning("Please fill in the Full Name field.")

    clients_data = run_query(
        "SELECT nome_completo, email FROM public.tb_clientes ORDER BY data_cadastro DESC;"
    )
    if clients_data:
        st.subheader("All Clients")
        columns = ["Full Name", "Email"]
        df_clients = pd.DataFrame(clients_data, columns=columns)
        st.dataframe(df_clients[["Full Name"]], use_container_width=True)
        download_df_as_csv(df_clients, "clients.csv", label="Download Clients CSV")

        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Client")
            client_display = [""] + [f"{row['Full Name']} ({row['Email']})" for _, row in df_clients.iterrows()]
            selected_display = st.selectbox("Select a client to edit/delete:", client_display)

            if selected_display:
                try:
                    original_name, original_email = selected_display.split(" (")
                    original_email = original_email.rstrip(")")
                except ValueError:
                    st.error("Seleção inválida. Por favor, selecione um cliente corretamente.")
                    st.stop()

                selected_client_row = df_clients[df_clients["Email"] == original_email].iloc[0]
                with st.form(key='edit_client_form'):
                    col1, col2 = st.columns(2)
                    with col1:
                        edit_name = st.text_input("Full Name", value=selected_client_row["Full Name"], max_chars=100)
                    col_upd, col_del = st.columns(2)
                    with col_upd:
                        update_button = st.form_submit_button(label="Update Client")
                    with col_del:
                        delete_button = st.form_submit_button(label="Delete Client")

                if update_button:
                    if edit_name:
                        update_query = """
                        UPDATE public.tb_clientes
                        SET nome_completo = %s
                        WHERE email = %s;
                        """
                        success = run_query(update_query, (edit_name, original_email), commit=True)
                        if success:
                            st.success("Client updated successfully!")
                            refresh_data()
                        else:
                            st.error("Failed to update the client.")
                    else:
                        st.warning("Please fill in the Full Name field.")

                if delete_button:
                    delete_query = "DELETE FROM public.tb_clientes WHERE email = %s;"
                    success = run_query(delete_query, (original_email,), commit=True)
                    if success:
                        refresh_data()
                        st.experimental_rerun()
                    else:
                        st.error("Failed to delete the client.")
    else:
        st.info("No clients found.")


def generate_invoice_for_printer(df: pd.DataFrame):
    """
    Gera um texto de 'nota fiscal' (exemplo) para exibir ou imprimir.
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

    grouped_df = df.groupby('Produto').agg({'Quantidade': 'sum', 'total': 'sum'}).reset_index()
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


def process_payment(client, payment_status):
    """
    Processa pagamento atualizando status de pedidos em aberto para 
    o método de pagamento informado.
    """
    query = """
        UPDATE public.tb_pedido
        SET status = %s, "Data" = CURRENT_TIMESTAMP
        WHERE "Cliente" = %s AND status = 'em aberto';
    """
    success = run_query(query, (payment_status, client), commit=True)
    if success:
        st.success(f"Status atualizado para: {payment_status}")
        refresh_data()
    else:
        st.error("Erro ao atualizar o status.")


def invoice_page():
    """
    Página de 'Nota Fiscal', onde o usuário seleciona um cliente com pedidos em aberto 
    e realiza pagamento.
    """
    st.title("Nota Fiscal")

    open_clients_query = 'SELECT DISTINCT "Cliente" FROM public.vw_pedido_produto WHERE status = %s;'
    open_clients = run_query(open_clients_query, ('em aberto',))
    client_list = [row[0] for row in open_clients] if open_clients else []
    selected_client = st.selectbox("Selecione um Cliente", [""] + client_list)

    if selected_client:
        invoice_query = (
            'SELECT "Produto", "Quantidade", "total" '
            'FROM public.vw_pedido_produto '
            'WHERE "Cliente" = %s AND status = %s;'
        )
        invoice_data = run_query(invoice_query, (selected_client, 'em aberto'))
        if invoice_data:
            df = pd.DataFrame(invoice_data, columns=["Produto", "Quantidade", "total"])
            generate_invoice_for_printer(df)

            # Botões de pagamento
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                if st.button("Debit", key="debit_button"):
                    process_payment(selected_client, "Received - Debited")
            with col2:
                if st.button("Credit", key="credit_button"):
                    process_payment(selected_client, "Received - Credit")
            with col3:
                if st.button("Pix", key="pix_button"):
                    process_payment(selected_client, "Received - Pix")
            with col4:
                if st.button("Cash", key="cash_button"):
                    process_payment(selected_client, "Received - Cash")
        else:
            st.info("Não há pedidos em aberto para o cliente selecionado.")
    else:
        st.warning("Por favor, selecione um cliente.")


###############################################################################
#                                 BACKUP PAGE
###############################################################################
def export_table_to_csv(table_name):
    """
    Exporta o conteúdo de uma tabela para CSV via um botão de download.
    """
    conn = get_db_connection()
    if conn:
        try:
            query = f"SELECT * FROM {table_name};"
            df = pd.read_sql_query(query, conn)
            csv = df.to_csv(index=False)
            st.download_button(
                label=f"Baixar {table_name} como CSV",
                data=csv,
                file_name=f"{table_name}.csv",
                mime="text/csv",
            )
        except Exception as e:
            st.error(f"Erro ao exportar a tabela {table_name}: {e}")
        finally:
            conn.close()


def backup_all_tables(tables):
    """
    Concatena dados de múltiplas tabelas e oferece um único download de CSV para todas.
    """
    conn = get_db_connection()
    if conn:
        try:
            all_frames = []
            for table in tables:
                query = f"SELECT * FROM {table};"
                df = pd.read_sql_query(query, conn)
                df["table_name"] = table
                all_frames.append(df)
            if all_frames:
                combined_csv = pd.concat(all_frames, ignore_index=True)
                csv = combined_csv.to_csv(index=False)
                st.download_button(
                    label="Download All Tables as CSV",
                    data=csv,
                    file_name="all_tables_backup.csv",
                    mime="text/csv",
                )
            else:
                st.warning("No data found for any tables.")
        except Exception as e:
            st.error(f"Erro ao exportar todas as tabelas: {e}")
        finally:
            conn.close()


def perform_backup():
    """
    Exibe a página de backup com botões para cada tabela e para todas.
    """
    st.header("Sistema de Backup")
    st.write("Clique nos botões abaixo para realizar backups das tabelas.")
    tables = ["tb_pedido", "tb_products", "tb_clientes", "tb_estoque"]

    if st.button("Download All Tables"):
        backup_all_tables(tables)

    for table in tables:
        export_table_to_csv(table)


def admin_backup_section():
    """
    Verifica se usuário é admin e exibe a seção de backup, senão exibe aviso.
    """
    if st.session_state.get("username") == "admin":
        perform_backup()
    else:
        st.warning("Acesso restrito para administradores.")


###############################################################################
#                              LOGIN PAGE
###############################################################################
def login_page():
    """
    Página de login simples. Exige credenciais admin ou caixa definidas em st.secrets.
    """
    st.markdown(
        """
        <style>
        body {
            background-color: white;
        }
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
        response = requests.get(logo_url)
        response.raise_for_status()
        logo = Image.open(BytesIO(response.content))
        st.image(logo, use_column_width=False)
    except requests.exceptions.RequestException:
        st.error("Falha ao carregar o logotipo.")

    st.title("Beach Club")
    st.write("Por favor, insira suas credenciais para acessar o aplicativo.")

    with st.form(key='login_form'):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit_login = st.form_submit_button(label="Login")

    if submit_login:
        credentials = st.secrets["credentials"]
        admin_username = credentials["admin_username"]
        admin_password = credentials["admin_password"]
        caixa_username = credentials["caixa_username"]
        caixa_password = credentials["caixa_password"]

        if username == admin_username and password == admin_password:
            st.session_state.logged_in = True
            st.session_state.username = "admin"
            st.success("Login bem-sucedido!")
        elif username == caixa_username and password == caixa_password:
            st.session_state.logged_in = True
            st.session_state.username = "caixa"
            st.success("Login bem-sucedido!")
        else:
            st.error("Nome de usuário ou senha incorretos.")


###############################################################################
#                            INICIALIZAÇÃO
###############################################################################
def initialize_session_state():
    """
    Inicializa variáveis no session_state se não existirem.
    """
    if 'data' not in st.session_state:
        st.session_state.data = load_all_data()
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False


def apply_custom_css():
    """
    Aplica CSS customizado na aplicação.
    """
    st.markdown(
        """
        <style>
        .css-1d391kg {  /* Classe para título */
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
    Renderiza o menu lateral usando streamlit-option-menu e retorna o item selecionado.
    """
    with st.sidebar:
        st.title("Boituva Beach Club 🎾")
        selected = option_menu(
            "Menu Principal",
            [
                "Home", "Orders", "Products", "Stock", "Clients",
                "Nota Fiscal", "Backup", "Cardápio",
                "Configurações e Ajustes", "Programa de Fidelidade",
                "Calendário de Eventos"
            ],
            icons=[
                "house", "file-text", "box", "list-task", "layers",
                "receipt", "cloud-upload", "list", "gear",
                "gift", "calendar"
            ],
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


def main():
    """
    Função principal que inicia toda a lógica do app Streamlit.
    """
    apply_custom_css()
    initialize_session_state()

    if not st.session_state.logged_in:
        login_page()
    else:
        selected_page = sidebar_navigation()

        # Se a página selecionada mudou, recarregue dados
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

        # Botão de logout
        with st.sidebar:
            if st.button("Logout"):
                keys_to_reset = ['home_page_initialized']
                for key in keys_to_reset:
                    if key in st.session_state:
                        del st.session_state[key]
                st.session_state.logged_in = False
                st.success("Desconectado com sucesso!")
                st.experimental_rerun()


# Se desejar que o app seja carregado automaticamente ao rodar "streamlit run nome.py",
# deixe a chamada abaixo. Se não quiser, basta removê-la.
if __name__ == "__main__":
    main()
