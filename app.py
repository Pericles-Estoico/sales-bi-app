import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")

st.title("📊 Sales BI Analytics")
st.subheader("Business Intelligence Executivo com Insights Acionáveis")

# Canais
CHANNELS = {
    'geral': '📊 Vendas Gerais',
    'mercado_livre': '🛒 Mercado Livre',
    'shopee_matriz': '🛍️ Shopee Matriz',
    'shopee_150': '🏪 Shopee 1:50',
    'shein': '👗 Shein'
}

# Sidebar
with st.sidebar:
    st.header("Upload de Vendas")
    canal = st.selectbox("Selecione o Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    uploaded_file = st.file_uploader("Planilha Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and st.button("🔄 Processar"):
        df = pd.read_excel(uploaded_file)
        df['Canal'] = CHANNELS[canal]
        st.session_state['data'] = df
        st.success(f"✅ {len(df)} registros carregados!")

# Main
if 'data' in st.session_state and not st.session_state['data'].empty:
    df = st.session_state['data']
    
    # Métricas
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Vendas", f"R$ {df['Total'].sum():,.2f}")
    col2.metric("Produtos", len(df))
    col3.metric("Unidades", int(df['Quantidade'].sum()))
    col4.metric("Ticket Médio", f"R$ {df['Total'].sum() / df['Quantidade'].sum():,.2f}")
    
    # Análise BCG
    st.header("📈 Matriz BCG")
    total_geral = df['Total'].sum()
    produtos = df.groupby('Produto').agg({'Quantidade': 'sum', 'Total': 'sum'}).reset_index()
    produtos['Participacao'] = (produtos['Total'] / total_geral) * 100
    produtos['Crescimento'] = produtos['Quantidade'].apply(lambda x: 15 if x > 5 else 5 if x > 3 else -5)
    
    def classificar_bcg(row):
        if row['Crescimento'] > 10 and row['Participacao'] > 5:
            return 'Estrela'
        elif row['Crescimento'] < 10 and row['Participacao'] > 5:
            return 'Vaca Leiteira'
        elif row['Crescimento'] > 10 and row['Participacao'] <= 5:
            return 'Interrogação'
        else:
            return 'Abacaxi'
    
    produtos['Categoria'] = produtos.apply(classificar_bcg, axis=1)
    
    col1, col2, col3, col4 = st.columns(4)
    for col, cat, emoji in zip([col1, col2, col3, col4], 
                                ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi'],
                                ['⭐', '🐄', '❓', '🍍']):
        with col:
            prods = produtos[produtos['Categoria'] == cat]
            st.subheader(f"{emoji} {cat}")
            st.metric("Produtos", len(prods))
            st.dataframe(prods[['Produto', 'Quantidade']].head(5), hide_index=True)
    
    # Pareto
    st.header("🎯 Análise Pareto 80/20")
    produtos_sorted = produtos.sort_values('Total', ascending=False)
    produtos_sorted['Acumulado'] = produtos_sorted['Total'].cumsum() / produtos_sorted['Total'].sum()
    pareto_80 = produtos_sorted[produtos_sorted['Acumulado'] <= 0.8]
    
    st.info(f"💡 **Insight**: {len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.0f}%) geram 80% das vendas")
    st.dataframe(pareto_80[['Produto', 'Quantidade', 'Total']], hide_index=True)
    
    # Google Sheets
    st.header("📤 Exportar para Google Sheets")
    if st.button("Enviar para Google Sheets"):
        try:
            # Configurar credenciais
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            # Abrir planilha
            sheet = client.open_by_url(st.secrets["GOOGLE_SHEETS_URL"]).sheet1
            
            # Limpar e adicionar dados
            sheet.clear()
            sheet.append_row(['Data', 'Produto', 'Quantidade', 'Preço Unitário', 'Total', 'Canal', 'Categoria BCG'])
            
            for _, row in df.iterrows():
                cat_bcg = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0]
                sheet.append_row([
                    str(row.get('Data', '')),
                    row['Produto'],
                    int(row['Quantidade']),
                    float(row['Preço Unitário']),
                    float(row['Total']),
                    row['Canal'],
                    cat_bcg
                ])
            
            st.success("✅ Dados enviados com sucesso!")
            st.info(f"🔗 [Abrir Planilha]({st.secrets['GOOGLE_SHEETS_URL']})")
        except Exception as e:
            st.error(f"❌ Erro: {str(e)}")
            st.info("💡 Configure GOOGLE_SHEETS_CREDENTIALS e GOOGLE_SHEETS_URL nos Secrets")

else:
    st.info("👈 Faça upload de uma planilha na barra lateral para começar")
    st.markdown("""
    ### O que você terá acesso:
    - 📈 **Matriz BCG**: Classificação automática de produtos
    - 🎯 **Análise Pareto**: Identifica produtos-chave
    - 💡 **Insights Automáticos**: Recomendações acionáveis
    - 📤 **Google Sheets**: Exportação automática
    """)
