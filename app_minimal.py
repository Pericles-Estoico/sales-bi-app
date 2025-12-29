"""
VERSÃO MÍNIMA DO APP - DIAGNÓSTICO
Teste se o problema é no código ou na configuração do Streamlit Cloud
"""

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Sales BI Pro - Test", page_icon="📊", layout="wide")

st.title("📊 Sales BI Pro - Versão de Diagnóstico")

st.success("✅ APP CARREGOU COM SUCESSO!")

st.markdown("### 🔍 Teste Básico de Funcionalidade")

# Teste 1: Session State
st.markdown("#### Teste 1: Session State")
if 'test_counter' not in st.session_state:
    st.session_state.test_counter = 0

if st.button("Incrementar Contador"):
    st.session_state.test_counter += 1

st.write(f"Contador: {st.session_state.test_counter}")

# Teste 2: Carregamento de Dados
st.markdown("#### Teste 2: Carregamento de Google Sheets")

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

if st.button("Testar Carregamento de Produtos"):
    with st.spinner("Carregando produtos..."):
        try:
            df = pd.read_csv(f"{BASE_URL}&gid=1037607798")
            st.success(f"✅ Produtos carregados: {len(df)} linhas")
            st.dataframe(df.head(10), width="stretch")
        except Exception as e:
            st.error(f"❌ Erro: {e}")

# Teste 3: Tabs
st.markdown("#### Teste 3: Sistema de Abas")

tab1, tab2, tab3 = st.tabs(["Aba 1", "Aba 2", "Aba 3"])

with tab1:
    st.write("✅ Aba 1 funcionando")

with tab2:
    st.write("✅ Aba 2 funcionando")

with tab3:
    st.write("✅ Aba 3 funcionando")

st.divider()

st.markdown("### 📋 Informações do Sistema")
st.write(f"Data/Hora: {datetime.now()}")
st.write(f"Streamlit Version: {st.__version__}")

st.markdown("---")
st.markdown("**Se você vê esta mensagem, o problema NÃO é com o Streamlit, é com o código do app principal.**")
