import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import re

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")
st.title("📊 Sales BI Analytics - Análise Evolutiva")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

def converter_planilha_bling(df_bling, data_venda):
    """Converte planilha do Bling para formato do app"""
    df_convertido = pd.DataFrame()
    
    # Mapear colunas
    df_convertido['Data'] = data_venda
    df_convertido['Produto'] = df_bling['Código']
    df_convertido['Quantidade'] = df_bling['Quantidade']
    
    # Limpar valores monetários (R$ 877,80 → 877.80)
    df_convertido['Total'] = df_bling['Valor'].apply(lambda x: 
        float(str(x).replace('R$', '').replace('.', '').replace(',', '.').strip())
    )
    
    # Calcular preço unitário
    df_convertido['Preço Unitário'] = df_convertido['Total'] / df_convertido['Quantidade']
    
    return df_convertido

with st.sidebar:
    st.header("Upload de Vendas")
    
    # Seletor de formato
    formato = st.radio("Formato da Planilha", 
                       ['Bling (Código, Quantidade, Valor)', 
                        'Padrão (Data, Produto, Quantidade, Total)'])
    
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    
    # Data da venda (para planilhas Bling)
    if formato.startswith('Bling'):
        data_venda = st.date_input("Data da Venda", datetime.now())
    
    uploaded_file = st.file_uploader("Planilha Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and st.button("🔄 Processar"):
        try:
            df_original = pd.read_excel(uploaded_file)
            
            # Detectar formato automaticamente
            colunas = df_original.columns.tolist()
            
            if 'Código' in colunas and 'Valor' in colunas:
                # Formato Bling
                st.info("✅ Formato Bling detectado - Convertendo...")
                df_novo = converter_planilha_bling(df_original, data_venda.strftime('%Y-%m-%d'))
                st.success(f"✅ Convertido: {len(df_novo)} produtos")
            else:
                # Formato padrão
                df_novo = df_original.copy()
            
            df_novo['Canal'] = CHANNELS[canal]
            df_novo['Data_Upload'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            st.session_state['data_novo'] = df_novo
            
            # Mostrar preview
            st.subheader("Preview dos Dados")
            st.dataframe(df_novo.head(10))
            st.metric("Total de Produtos", len(df_novo))
            st.metric("Faturamento Total", f"R$ {df_novo['Total'].sum():,.2f}")
            
        except Exception as e:
            st.error(f"❌ Erro ao processar: {str(e)}")

if 'data_novo' in st.session_state:
    df_novo = st.session_state['data_novo']
    
    if st.button("📤 Enviar para Google Sheets"):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
            spreadsheet = gspread.authorize(creds).open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
            
            # Ler dados existentes
            try:
                sheet_detalhes = spreadsheet.worksheet("6. Detalhes")
                dados_existentes = sheet_detalhes.get_all_values()
                if len(dados_existentes) > 1:
                    df_existente = pd.DataFrame(dados_existentes[1:], columns=dados_existentes[0])
                    df_existente['Quantidade'] = pd.to_numeric(df_existente['Quantidade'], errors='coerce')
                    df_existente['Total'] = pd.to_numeric(df_existente['Total'], errors='coerce')
                else:
                    df_existente = pd.DataFrame()
            except:
                df_existente = pd.DataFrame()
                sheet_detalhes = spreadsheet.add_worksheet("6. Detalhes", 5000, 10)
            
            df_completo = pd.concat([df_existente, df_novo], ignore_index=True) if not df_existente.empty else df_novo
            
            total_vendas = df_completo['Total'].sum()
            produtos = df_completo.groupby('Produto').agg({'Quantidade': 'sum', 'Total': 'sum'}).reset_index()
            produtos['Participacao'] = (produtos['Total'] / total_vendas) * 100
            
            qtd_mediana = produtos['Quantidade'].median()
            part_mediana = produtos['Participacao'].median()
            
            def classificar_bcg(row):
                if row['Quantidade'] >= qtd_mediana and row['Participacao'] >= part_mediana: return 'Estrela'
                elif row['Quantidade'] < qtd_mediana and row['Participacao'] >= part_mediana: return 'Vaca Leiteira'
                elif row['Quantidade'] >= qtd_mediana and row['Participacao'] < part_mediana: return 'Interrogação'
                else: return 'Abacaxi'
            
            produtos['Categoria'] = produtos.apply(classificar_bcg, axis=1)
            
            if 'Data' in df_completo.columns:
                df_completo['Data'] = pd.to_datetime(df_completo['Data'], errors='coerce')
                vendas_por_dia = df_completo.groupby('Data').agg({'Total': 'sum', 'Quantidade': 'sum'}).reset_index().sort_values('Data')
            
            dias_analisados = len(df_completo['Data'].unique()) if 'Data' in df_completo.columns else 1
            
            # 1. Dashboard Executivo
            try: sheet1 = spreadsheet.worksheet("1. Dashboard Executivo")
            except: sheet1 = spreadsheet.add_worksheet("1. Dashboard Executivo", 100, 5)
            
            dados1 = [
                ['DASHBOARD EXECUTIVO'],
                [f'Atualizado: {datetime.now().strftime("%d/%m/%Y %H:%M")}'],
                [],
                ['PERÍODO TOTAL'],
                ['Dias com Vendas', dias_analisados],
                ['Total Acumulado', f'R$ {total_vendas:,.2f}'],
                ['Produtos Únicos', len(produtos)],
                ['Unidades Totais', int(df_completo['Quantidade'].sum())],
                [],
                ['MATRIZ BCG'],
                ['Categoria', 'Produtos', 'Faturamento'],
                ['⭐ Estrelas', len(produtos[produtos['Categoria']=='Estrela']), f'R$ {produtos[produtos["Categoria"]=="Estrela"]["Total"].sum():,.2f}'],
                ['🐄 Vacas', len(produtos[produtos['Categoria']=='Vaca Leiteira']), f'R$ {produtos[produtos["Categoria"]=="Vaca Leiteira"]["Total"].sum():,.2f}'],
                ['❓ Interrogações', len(produtos[produtos['Categoria']=='Interrogação']), f'R$ {produtos[produtos["Categoria"]=="Interrogação"]["Total"].sum():,.2f}'],
                ['🍍 Abacaxis', len(produtos[produtos['Categoria']=='Abacaxi']), f'R$ {produtos[produtos["Categoria"]=="Abacaxi"]["Total"].sum():,.2f}']
            ]
            sheet1.clear()
            sheet1.update('A1', dados1)
            
            # 2. Evolução Temporal
            try: sheet2 = spreadsheet.worksheet("2. Evolução")
            except: sheet2 = spreadsheet.add_worksheet("2. Evolução", 500, 5)
            
            dados2 = [['EVOLUÇÃO DIA A DIA'], [], ['Data', 'Faturamento', 'Unidades', 'Crescimento %']]
            if 'Data' in df_completo.columns and not vendas_por_dia.empty:
                for i, row in vendas_por_dia.iterrows():
                    crescimento = ''
                    if i > 0:
                        anterior = vendas_por_dia.iloc[i-1]['Total']
                        crescimento = f'{((row["Total"] - anterior) / anterior * 100):.1f}%' if anterior > 0 else 'N/A'
                    dados2.append([row['Data'].strftime('%d/%m/%Y'), f'R$ {row["Total"]:,.2f}', int(row['Quantidade']), crescimento])
            sheet2.clear()
            sheet2.update('A1', dados2)
            
            # 3. BCG
            try: sheet3 = spreadsheet.worksheet("3. BCG")
            except: sheet3 = spreadsheet.add_worksheet("3. BCG", 500, 5)
            
            dados3 = [['MATRIZ BCG DETALHADA'], []]
            for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                prods = produtos[produtos['Categoria'] == cat].head(20)
                dados3.append([f'{cat.upper()} ({len(produtos[produtos["Categoria"]==cat])} produtos)'])
                dados3.append(['Produto', 'Qtd', 'Faturamento', '% Part'])
                for _, p in prods.iterrows():
                    dados3.append([p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'{p["Participacao"]:.2f}%'])
                dados3.append([])
            sheet3.clear()
            sheet3.update('A1', dados3)
            
            # 4. Pareto
            produtos_sorted = produtos.sort_values('Total', ascending=False)
            produtos_sorted['Acumulado'] = produtos_sorted['Total'].cumsum() / produtos_sorted['Total'].sum()
            pareto_80 = produtos_sorted[produtos_sorted['Acumulado'] <= 0.8]
            
            try: sheet4 = spreadsheet.worksheet("4. Pareto")
            except: sheet4 = spreadsheet.add_worksheet("4. Pareto", 500, 6)
            
            dados4 = [
                ['PARETO 80/20'],
                [],
                [f'{len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.1f}%) = 80% vendas'],
                [f'R$ {pareto_80["Total"].sum():,.2f}'],
                [],
                ['Ranking', 'Produto', 'Qtd', 'Faturamento', '% Acum', 'BCG']
            ]
            for i, (_, p) in enumerate(pareto_80.iterrows(), 1):
                dados4.append([i, p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'{p["Acumulado"]*100:.1f}%', p['Categoria']])
            sheet4.clear()
            sheet4.update('A1', dados4)
            
            # 5. Recomendações CEO
            try: sheet5 = spreadsheet.worksheet("5. CEO")
            except: sheet5 = spreadsheet.add_worksheet("5. CEO", 100, 3)
            
            estrelas = len(produtos[produtos['Categoria']=='Estrela'])
            vacas = len(produtos[produtos['Categoria']=='Vaca Leiteira'])
            interrogacoes = len(produtos[produtos['Categoria']=='Interrogação'])
            abacaxis = len(produtos[produtos['Categoria']=='Abacaxi'])
            
            dados5 = [
                ['RECOMENDAÇÕES CEO'],
                [f'{dias_analisados} dias analisados'],
                [],
                ['PRIORIDADE', 'AÇÃO', 'IMPACTO'],
                ['🔴 CRÍTICA', f'Investir nas {estrelas} Estrelas', '+30% receita'],
                ['🟡 ALTA', f'Manter {vacas} Vacas', 'Fluxo de caixa'],
                ['🟠 MÉDIA', f'Revisar {interrogacoes} Interrogações', 'Reduzir custos'],
                ['🔴 CRÍTICA', f'Liquidar {abacaxis} Abacaxis', 'Liberar capital'],
                [],
                ['FOCO'],
                [f'{len(pareto_80)} produtos Pareto = R$ {pareto_80["Total"].sum():,.2f}'],
                [],
                ['PRÓXIMOS PASSOS'],
                ['1. Aumentar estoque Estrelas 50%'],
                ['2. Promoção Interrogações'],
                ['3. Liquidação Abacaxis 70% off']
            ]
            sheet5.clear()
            sheet5.update('A1', dados5)
            
            # 6. Detalhes
            dados6 = [['Data', 'Produto', 'Qtd', 'Preço', 'Total', 'Canal', 'BCG', 'Upload']]
            for _, row in df_completo.iterrows():
                cat = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0] if row['Produto'] in produtos['Produto'].values else 'N/A'
                dados6.append([
                    str(row.get('Data', '')),
                    row['Produto'],
                    int(row['Quantidade']) if pd.notna(row['Quantidade']) else 0,
                    float(row['Preço Unitário']) if pd.notna(row.get('Preço Unitário', 0)) else 0,
                    float(row['Total']) if pd.notna(row['Total']) else 0,
                    row.get('Canal', ''),
                    cat,
                    row.get('Data_Upload', '')
                ])
            sheet_detalhes.clear()
            sheet_detalhes.update('A1', dados6)
            
            st.success(f"✅ {len(df_completo)} registros ({len(df_novo)} novos)")
            st.info(f"📊 {dias_analisados} dias")
            st.info(f"🔗 [Abrir]({st.secrets['GOOGLE_SHEETS_URL']})")
            
        except Exception as e:
            st.error(f"❌ {str(e)}")
else:
    st.info("👈 Upload planilha")
    st.markdown("""
    ### Formatos Aceitos:
    
    **1. Bling (automático)**
    - Colunas: Código, Quantidade, Valor
    - Sistema converte automaticamente
    
    **2. Padrão**
    - Colunas: Data, Produto, Quantidade, Total
    """)
