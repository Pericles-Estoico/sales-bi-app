import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")

st.title("📊 Sales BI Analytics")
st.subheader("Business Intelligence Executivo com Insights Acionáveis")

CHANNELS = {
    'geral': '📊 Vendas Gerais',
    'mercado_livre': '🛒 Mercado Livre',
    'shopee_matriz': '🛍️ Shopee Matriz',
    'shopee_150': '🏪 Shopee 1:50',
    'shein': '👗 Shein'
}

with st.sidebar:
    st.header("Upload de Vendas")
    canal = st.selectbox("Selecione o Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    uploaded_file = st.file_uploader("Planilha Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and st.button("🔄 Processar"):
        df = pd.read_excel(uploaded_file)
        df['Canal'] = CHANNELS[canal]
        st.session_state['data'] = df
        st.success(f"✅ {len(df)} registros carregados!")

if 'data' in st.session_state and not st.session_state['data'].empty:
    df = st.session_state['data']
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Vendas", f"R$ {df['Total'].sum():,.2f}")
    col2.metric("Produtos", len(df))
    col3.metric("Unidades", int(df['Quantidade'].sum()))
    col4.metric("Ticket Médio", f"R$ {df['Total'].sum() / df['Quantidade'].sum():,.2f}")
    
    st.header("📈 Matriz BCG")
    total_geral = df['Total'].sum()
    produtos = df.groupby('Produto').agg({'Quantidade': 'sum', 'Total': 'sum'}).reset_index()
    produtos['Participacao'] = (produtos['Total'] / total_geral) * 100
    
    # Lógica BCG melhorada
    qtd_mediana = produtos['Quantidade'].median()
    part_mediana = produtos['Participacao'].median()
    
    def classificar_bcg(row):
        crescimento_alto = row['Quantidade'] >= qtd_mediana
        participacao_alta = row['Participacao'] >= part_mediana
        
        if crescimento_alto and participacao_alta:
            return 'Estrela'
        elif not crescimento_alto and participacao_alta:
            return 'Vaca Leiteira'
        elif crescimento_alto and not participacao_alta:
            return 'Interrogação'
        else:
            return 'Abacaxi'
    
    produtos['Categoria'] = produtos.apply(classificar_bcg, axis=1)
    
    col1, col2, col3, col4 = st.columns(4)
    for col, cat, emoji, cor in zip([col1, col2, col3, col4], 
                                     ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi'],
                                     ['⭐', '🐄', '❓', '🍍'],
                                     ['#FFD700', '#32CD32', '#1E90FF', '#FF6347']):
        with col:
            prods = produtos[produtos['Categoria'] == cat]
            st.markdown(f"### {emoji} {cat}")
            st.metric("Produtos", len(prods))
            st.metric("Faturamento", f"R$ {prods['Total'].sum():,.0f}")
            if len(prods) > 0:
                st.dataframe(prods[['Produto', 'Quantidade']].head(5), hide_index=True, height=200)
    
    # Insights BCG
    st.info(f"""
    💡 **Insights Executivos**:
    - **Estrelas** ({len(produtos[produtos['Categoria']=='Estrela'])}): Alto volume + Alta receita → Invista em marketing
    - **Vacas Leiteiras** ({len(produtos[produtos['Categoria']=='Vaca Leiteira'])}): Baixo volume + Alta receita → Mantenha estoque
    - **Interrogações** ({len(produtos[produtos['Categoria']=='Interrogação'])}): Alto volume + Baixa receita → Aumente preço ou descontinue
    - **Abacaxis** ({len(produtos[produtos['Categoria']=='Abacaxi'])}): Baixo volume + Baixa receita → Liquidar estoque
    """)
    
    st.header("🎯 Análise Pareto 80/20")
    produtos_sorted = produtos.sort_values('Total', ascending=False)
    produtos_sorted['Acumulado'] = produtos_sorted['Total'].cumsum() / produtos_sorted['Total'].sum()
    pareto_80 = produtos_sorted[produtos_sorted['Acumulado'] <= 0.8]
    
    st.success(f"💡 **Regra 80/20 Confirmada**: {len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.0f}%) geram 80% das vendas (R$ {pareto_80['Total'].sum():,.2f})")
    st.dataframe(pareto_80[['Produto', 'Quantidade', 'Total', 'Categoria']], hide_index=True)
    
    st.header("📤 Exportar para Google Sheets")
    
    # Verificar se secrets existem
    has_credentials = 'GOOGLE_SHEETS_CREDENTIALS' in st.secrets
    has_url = 'GOOGLE_SHEETS_URL' in st.secrets
    
    if not has_credentials or not has_url:
        st.warning("⚠️ Configure os Secrets primeiro:")
        st.code("""
# No Streamlit Cloud:
# 1. Vá em Settings > Secrets
# 2. Adicione:

GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/SEU_ID_AQUI/edit"

GOOGLE_SHEETS_CREDENTIALS = '''
{
  "type": "service_account",
  "project_id": "seu-projeto",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n",
  "client_email": "seu-email@seu-projeto.iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
'''
        """, language='toml')
        
        with st.expander("📖 Como criar Service Account do Google"):
            st.markdown("""
            1. Acesse [Google Cloud Console](https://console.cloud.google.com/)
            2. Crie um projeto novo
            3. Ative a API do Google Sheets
            4. Vá em **IAM & Admin** > **Service Accounts**
            5. Clique **Create Service Account**
            6. Dê um nome e clique **Create**
            7. Clique em **Keys** > **Add Key** > **Create new key** > **JSON**
            8. Baixe o arquivo JSON
            9. Copie o conteúdo e cole em `GOOGLE_SHEETS_CREDENTIALS`
            10. Compartilhe sua planilha com o email da service account
            """)
    
    if st.button("Enviar para Google Sheets", disabled=not (has_credentials and has_url)):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            sheet = client.open_by_url(st.secrets["GOOGLE_SHEETS_URL"]).sheet1
            
            sheet.clear()
            sheet.append_row(['Data', 'Produto', 'Quantidade', 'Preço Unitário', 'Total', 'Canal', 'Categoria BCG'])
            
            for _, row in df.iterrows():
                cat_bcg = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0] if row['Produto'] in produtos['Produto'].values else 'N/A'
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

else:
    st.info("👈 Faça upload de uma planilha na barra lateral para começar")
    st.markdown("""
    ### O que você terá acesso:
    - 📈 **Matriz BCG**: Classificação automática (Estrela, Vaca Leiteira, Interrogação, Abacaxi)
    - 🎯 **Análise Pareto**: Identifica os 20% de produtos que geram 80% das vendas
    - 💡 **Insights Executivos**: Recomendações acionáveis para cada categoria
    - 📤 **Google Sheets**: Exportação automática com categoria BCG
    """)
