import streamlit as st
import pandas as pd
from datetime import datetime

from db_utils import run_query, run_insert
from app_utils import download_df_as_csv

def clients_page():
    st.title("Clients")
    st.subheader("Register a New Client")

    # Basic form to add a client (you can expand with more fields)
    with st.form(key='client_form'):
        nome_completo = st.text_input("Full Name", max_chars=100)
        submit_client = st.form_submit_button(label="Register New Client")

    if submit_client:
        if nome_completo:
            # Example placeholders for now
            data_nascimento = datetime(2000, 1, 1).date()
            genero = "Man"
            telefone = "0000-0000"
            unique_id = datetime.now().strftime("%Y%m%d%H%M%S")
            email = f"{nome_completo.replace(' ', '_').lower()}_{unique_id}@example.com"
            endereco = "Endereço padrão"

            query = """
                INSERT INTO public.tb_clientes (nome_completo, data_nascimento, genero, telefone, email, endereco, data_cadastro)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP);
            """
            success = run_insert(query, (nome_completo, data_nascimento, genero, telefone, email, endereco))
            if success:
                st.success("Client registered successfully!")
                st.session_state.data = st.session_state.load_all_data()
            else:
                st.error("Failed to register the client.")
        else:
            st.warning("Please fill in the Full Name field.")

    # Display all clients
    clients_data = run_query(
        """
        SELECT nome_completo, data_nascimento, genero,
               telefone, email, endereco, data_cadastro
        FROM public.tb_clientes
        ORDER BY data_cadastro DESC;
        """
    )
    if clients_data:
        st.subheader("All Clients")
        columns = ["Full Name", "Birth Date", "Gender", "Phone", "Email", "Address", "Register Date"]
        df_clients = pd.DataFrame(clients_data, columns=columns)
        st.dataframe(df_clients, use_container_width=True)

        download_df_as_csv(df_clients, "clients.csv", label="Download Clients CSV")

        # Admin can edit or delete a client
        if st.session_state.get("username") == "admin":
            st.subheader("Edit or Delete an Existing Client")
            client_emails = df_clients["Email"].unique().tolist()
            selected_email = st.selectbox("Select a client by Email:", [""] + client_emails)

            if selected_email:
                selected_client_row = df_clients[df_clients["Email"] == selected_email].iloc[0]
                original_name = selected_client_row["Full Name"]

                with st.form(key='edit_client_form'):
                    col1, col2 = st.columns(2)
                    with col1:
                        edit_name = st.text_input("Full Name", value=original_name, max_chars=100)
                    with col2:
                        st.write("")  # Layout placeholder
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
                        success = run_insert(update_query, (edit_name, selected_email))
                        if success:
                            st.success("Client updated successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to update the client.")
                    else:
                        st.warning("Please fill in the Full Name field.")

                if delete_button:
                    confirm = st.checkbox("Are you sure you want to delete this client?")
                    if confirm:
                        delete_query = "DELETE FROM public.tb_clientes WHERE email = %s;"
                        success = run_insert(delete_query, (selected_email,))
                        if success:
                            st.success("Client deleted successfully!")
                            st.session_state.data = st.session_state.load_all_data()
                        else:
                            st.error("Failed to delete the client.")
    else:
        st.info("No clients found.")
