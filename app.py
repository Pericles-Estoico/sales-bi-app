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
    total_vendas = df['Total'].sum()
    col1.metric("Total Vendas", f"R$ {total_vendas:,.2f}")
    col2.metric("Produtos", len(df))
    col3.metric("Unidades", int(df['Quantidade'].sum()))
    col4.metric("Ticket Médio", f"R$ {total_vendas / df['Quantidade'].sum():,.2f}")
    
    st.header("📈 Matriz BCG")
    produtos = df.groupby('Produto').agg({'Quantidade': 'sum', 'Total': 'sum'}).reset_index()
    produtos['Participacao'] = (produtos['Total'] / total_vendas) * 100
    
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
    for col, cat, emoji in zip([col1, col2, col3, col4], 
                                ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi'],
                                ['⭐', '🐄', '❓', '🍍']):
        with col:
            prods = produtos[produtos['Categoria'] == cat]
            st.markdown(f"### {emoji} {cat}")
            st.metric("Produtos", len(prods))
            st.metric("Faturamento", f"R$ {prods['Total'].sum():,.0f}")
            if len(prods) > 0:
                st.dataframe(prods[['Produto', 'Quantidade']].head(5), hide_index=True, height=200)
    
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
    
    st.success(f"💡 **Regra 80/20**: {len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.0f}%) geram 80% das vendas (R$ {pareto_80['Total'].sum():,.2f})")
    st.dataframe(pareto_80[['Produto', 'Quantidade', 'Total', 'Categoria']], hide_index=True)
    
    st.header("📤 Exportar para Google Sheets")
    
    has_credentials = 'GOOGLE_SHEETS_CREDENTIALS' in st.secrets
    has_url = 'GOOGLE_SHEETS_URL' in st.secrets
    
    if st.button("Enviar para Google Sheets", disabled=not (has_credentials and has_url)):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            client = gspread.authorize(creds)
            
            spreadsheet = client.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
            
            # Aba Detalhes
            try:
                sheet_detalhes = spreadsheet.worksheet("Detalhes")
            except:
                sheet_detalhes = spreadsheet.add_worksheet("Detalhes", rows=1000, cols=10)
            
            sheet_detalhes.clear()
            sheet_detalhes.append_row(['Data', 'Produto', 'Quantidade', 'Preço Unitário', 'Total', 'Canal', 'Categoria BCG'])
            
            for _, row in df.iterrows():
                cat_bcg = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0] if row['Produto'] in produtos['Produto'].values else 'N/A'
                sheet_detalhes.append_row([
                    str(row.get('Data', '')),
                    row['Produto'],
                    int(row['Quantidade']),
                    float(row['Preço Unitário']),
                    float(row['Total']),
                    row['Canal'],
                    cat_bcg
                ])
            
            # Aba Resumo Executivo
            try:
                sheet_resumo = spreadsheet.worksheet("Resumo Executivo")
            except:
                sheet_resumo = spreadsheet.add_worksheet("Resumo Executivo", rows=100, cols=5)
            
            sheet_resumo.clear()
            sheet_resumo.append_row(['RESUMO EXECUTIVO - SALES BI ANALYTICS'])
            sheet_resumo.append_row([])
            sheet_resumo.append_row(['Métrica', 'Valor'])
            sheet_resumo.append_row(['Total de Vendas', f'R$ {total_vendas:,.2f}'])
            sheet_resumo.append_row(['Total de Produtos', len(df)])
            sheet_resumo.append_row(['Total de Unidades', int(df['Quantidade'].sum())])
            sheet_resumo.append_row(['Ticket Médio', f'R$ {total_vendas / df['Quantidade'].sum():,.2f}'])
            sheet_resumo.append_row([])
            sheet_resumo.append_row(['MATRIZ BCG'])
            sheet_resumo.append_row(['Categoria', 'Produtos', 'Faturamento'])
            
            for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                prods = produtos[produtos['Categoria'] == cat]
                sheet_resumo.append_row([cat, len(prods), f'R$ {prods["Total"].sum():,.2f}'])
            
            sheet_resumo.append_row([])
            sheet_resumo.append_row(['INSIGHTS ESTRATÉGICOS CEO'])
            sheet_resumo.append_row([f'Estrelas ({len(produtos[produtos["Categoria"]=="Estrela"])}): Invista em marketing e expansão'])
            sheet_resumo.append_row([f'Vacas Leiteiras ({len(produtos[produtos["Categoria"]=="Vaca Leiteira"])}): Mantenha estoque e operação estável'])
            sheet_resumo.append_row([f'Interrogações ({len(produtos[produtos["Categoria"]=="Interrogação"])}): Aumente preço ou descontinue'])
            sheet_resumo.append_row([f'Abacaxis ({len(produtos[produtos["Categoria"]=="Abacaxi"])}): Liquidar estoque imediatamente'])
            sheet_resumo.append_row([])
            sheet_resumo.append_row(['PARETO 80/20'])
            sheet_resumo.append_row([f'{len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.0f}%) geram 80% das vendas'])
            
            st.success("✅ Dados enviados com sucesso!")
            st.info(f"🔗 [Abrir Planilha]({st.secrets['GOOGLE_SHEETS_URL']})")
        except Exception as e:
            st.error(f"❌ Erro: {str(e)}")

else:
    st.info("👈 Faça upload de uma planilha na barra lateral para começar")
