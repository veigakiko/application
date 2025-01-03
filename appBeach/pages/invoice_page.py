import streamlit as st
import pandas as pd

from db_utils import run_query, run_insert
from app_utils import format_currency

def invoice_page():
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

def process_payment(client, payment_status):
    """
    Updates the status of all open orders for the given client
    to the specified payment_status.
    """
    query = """
        UPDATE public.tb_pedido
        SET status = %s, "Data" = CURRENT_TIMESTAMP
        WHERE "Cliente" = %s AND status = 'em aberto';
    """
    success = run_insert(query, (payment_status, client))
    if success:
        st.success(f"Status atualizado para: {payment_status}")
        # Refresh session data
        st.session_state.data = st.session_state.load_all_data()
    else:
        st.error("Erro ao atualizar o status.")

def generate_invoice_for_printer(df: pd.DataFrame):
    """
    Displays a 'nota fiscal' style receipt for printing.
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
        description = f"{row['Produto'][:20]:<20}"  # limit product name to 20 chars
        quantity_str = f"{int(row['Quantidade']):>5}"
        total_item = row['total']
        total_general += total_item
        total_formatted = format_currency(total_item)
        invoice_note.append(f"{description} {quantity_str} {total_formatted}")

    from app_utils import format_currency  # Just to ensure we have the function here
    invoice_note.append("--------------------------------------------------")
    invoice_note.append(f"{'TOTAL GERAL:':>30} {format_currency(total_general):>10}")
    invoice_note.append("==================================================")
    invoice_note.append("OBRIGADO PELA SUA PREFERÊNCIA!")
    invoice_note.append("==================================================")

    st.text("\n".join(invoice_note))
