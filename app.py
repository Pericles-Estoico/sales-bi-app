import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")
st.title("📊 Sales BI Analytics - Análise Evolutiva")
st.subheader("Histórico Acumulado com Storytelling")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

with st.sidebar:
    st.header("Upload de Vendas")
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    uploaded_file = st.file_uploader("Planilha Excel", type=['xlsx', 'xls'])
    if uploaded_file and st.button("🔄 Processar e Adicionar"):
        df_novo = pd.read_excel(uploaded_file)
        df_novo['Canal'] = CHANNELS[canal]
        df_novo['Data_Upload'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        st.session_state['data_novo'] = df_novo
        st.success(f"✅ {len(df_novo)} novos registros carregados!")

if 'data_novo' in st.session_state:
    df_novo = st.session_state['data_novo']
    
    st.header("📤 Enviar para Google Sheets (Modo Acumulado)")
    st.info("Os novos dados serão **adicionados** aos existentes, mantendo histórico completo")
    
    if st.button("Enviar e Analisar Histórico Completo"):
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
            
            # Combinar dados
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
            
            # Análise por data
            if 'Data' in df_completo.columns:
                df_completo['Data'] = pd.to_datetime(df_completo['Data'], errors='coerce')
                vendas_por_dia = df_completo.groupby('Data').agg({'Total': 'sum', 'Quantidade': 'sum'}).reset_index()
                vendas_por_dia = vendas_por_dia.sort_values('Data')
            
            # 1. Dashboard Executivo
            try: sheet1 = spreadsheet.worksheet("1. Dashboard Executivo")
            except: sheet1 = spreadsheet.add_worksheet("1. Dashboard Executivo", 100, 5)
            sheet1.clear()
            
            dias_analisados = len(df_completo['Data'].unique()) if 'Data' in df_completo.columns else 1
            
            sheet1.append_rows([
                ['DASHBOARD EXECUTIVO - HISTÓRICO COMPLETO'],
                [f'Atualizado em: {datetime.now().strftime("%d/%m/%Y %H:%M")}'],
                [],
                ['PERÍODO TOTAL ANALISADO'],
                ['Dias com Vendas', dias_analisados],
                ['Total Acumulado', f'R$ {total_vendas:,.2f}'],
                ['Produtos Únicos', len(produtos)],
                ['Unidades Totais', int(df_completo['Quantidade'].sum())],
                ['Ticket Médio Geral', f'R$ {total_vendas / df_completo["Quantidade"].sum():,.2f}'],
                [],
                ['MATRIZ BCG - HISTÓRICO COMPLETO'],
                ['Categoria', 'Produtos', 'Faturamento Total'],
                ['⭐ Estrelas', len(produtos[produtos['Categoria']=='Estrela']), f'R$ {produtos[produtos["Categoria"]=="Estrela"]["Total"].sum():,.2f}'],
                ['🐄 Vacas Leiteiras', len(produtos[produtos['Categoria']=='Vaca Leiteira']), f'R$ {produtos[produtos["Categoria"]=="Vaca Leiteira"]["Total"].sum():,.2f}'],
                ['❓ Interrogações', len(produtos[produtos['Categoria']=='Interrogação']), f'R$ {produtos[produtos["Categoria"]=="Interrogação"]["Total"].sum():,.2f}'],
                ['🍍 Abacaxis', len(produtos[produtos['Categoria']=='Abacaxi']), f'R$ {produtos[produtos["Categoria"]=="Abacaxi"]["Total"].sum():,.2f}']
            ])
            
            # 2. Evolução Temporal
            try: sheet2 = spreadsheet.worksheet("2. Evolução Temporal")
            except: sheet2 = spreadsheet.add_worksheet("2. Evolução Temporal", 500, 6)
            sheet2.clear()
            sheet2.append_row(['EVOLUÇÃO DIA A DIA'])
            sheet2.append_row([])
            if 'Data' in df_completo.columns and not vendas_por_dia.empty:
                sheet2.append_row(['Data', 'Faturamento', 'Unidades', 'Ticket Médio', 'Crescimento %'])
                for i, row in vendas_por_dia.iterrows():
                    crescimento = ''
                    if i > 0:
                        anterior = vendas_por_dia.iloc[i-1]['Total']
                        crescimento = f'{((row["Total"] - anterior) / anterior * 100):.1f}%' if anterior > 0 else 'N/A'
                    sheet2.append_row([
                        row['Data'].strftime('%d/%m/%Y'),
                        f'R$ {row["Total"]:,.2f}',
                        int(row['Quantidade']),
                        f'R$ {row["Total"] / row["Quantidade"]:.2f}',
                        crescimento
                    ])
            
            # 3. Análise BCG
            try: sheet3 = spreadsheet.worksheet("3. Análise BCG")
            except: sheet3 = spreadsheet.add_worksheet("3. Análise BCG", 500, 5)
            sheet3.clear()
            sheet3.append_row(['MATRIZ BCG - ANÁLISE DETALHADA'])
            sheet3.append_row([])
            for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                prods = produtos[produtos['Categoria'] == cat]
                sheet3.append_row([f'{cat.upper()} ({len(prods)} produtos)'])
                sheet3.append_row(['Produto', 'Qtd Total', 'Faturamento', '% Participação'])
                for _, p in prods.iterrows():
                    sheet3.append_row([p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'{p["Participacao"]:.2f}%'])
                sheet3.append_row([])
            
            # 4. Pareto
            produtos_sorted = produtos.sort_values('Total', ascending=False)
            produtos_sorted['Acumulado'] = produtos_sorted['Total'].cumsum() / produtos_sorted['Total'].sum()
            pareto_80 = produtos_sorted[produtos_sorted['Acumulado'] <= 0.8]
            
            try: sheet4 = spreadsheet.worksheet("4. Pareto 80-20")
            except: sheet4 = spreadsheet.add_worksheet("4. Pareto 80-20", 500, 6)
            sheet4.clear()
            sheet4.append_row(['ANÁLISE PARETO 80/20 - HISTÓRICO COMPLETO'])
            sheet4.append_row([])
            sheet4.append_row([f'✅ {len(pareto_80)} produtos ({len(pareto_80)/len(produtos)*100:.1f}%) geram 80% das vendas'])
            sheet4.append_row([f'💰 Representam R$ {pareto_80["Total"].sum():,.2f} do total'])
            sheet4.append_row([])
            sheet4.append_row(['Ranking', 'Produto', 'Quantidade', 'Faturamento', '% Acumulado', 'Categoria BCG'])
            for i, (_, p) in enumerate(pareto_80.iterrows(), 1):
                sheet4.append_row([i, p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'{p["Acumulado"]*100:.1f}%', p['Categoria']])
            
            # 5. Recomendações CEO
            try: sheet5 = spreadsheet.worksheet("5. Recomendações CEO")
            except: sheet5 = spreadsheet.add_worksheet("5. Recomendações CEO", 100, 3)
            sheet5.clear()
            
            estrelas = len(produtos[produtos['Categoria']=='Estrela'])
            vacas = len(produtos[produtos['Categoria']=='Vaca Leiteira'])
            interrogacoes = len(produtos[produtos['Categoria']=='Interrogação'])
            abacaxis = len(produtos[produtos['Categoria']=='Abacaxi'])
            
            sheet5.append_rows([
                ['RECOMENDAÇÕES ESTRATÉGICAS CEO'],
                [f'Baseado em {dias_analisados} dias de vendas'],
                [],
                ['PRIORIDADE', 'AÇÃO RECOMENDADA', 'IMPACTO ESPERADO'],
                ['🔴 CRÍTICA', f'Investir pesado nas {estrelas} Estrelas', f'Potencial de crescimento: +30% em receita'],
                ['🟡 ALTA', f'Manter operação das {vacas} Vacas Leiteiras', 'Fluxo de caixa estável garantido'],
                ['🟠 MÉDIA', f'Revisar estratégia de {interrogacoes} Interrogações', 'Reduzir custos ou aumentar margem'],
                ['🔴 CRÍTICA', f'Liquidar {abacaxis} Abacaxis IMEDIATAMENTE', 'Liberar capital de giro'],
                [],
                ['FOCO ESTRATÉGICO'],
                [f'Concentrar 80% dos esforços nos {len(pareto_80)} produtos Pareto'],
                [f'Eles já geram R$ {pareto_80["Total"].sum():,.2f} ({pareto_80["Total"].sum()/total_vendas*100:.0f}% do total)'],
                [],
                ['PRÓXIMOS PASSOS'],
                ['1. Aumentar estoque das Estrelas em 50%'],
                ['2. Criar promoções para Interrogações (teste de preço)'],
                ['3. Desconto de 70% nos Abacaxis (liquidação total)'],
                [f'4. Monitorar evolução diária (já temos {dias_analisados} dias de histórico)']
            ])
            
            # 6. Detalhes (Acumular dados)
            sheet_detalhes.clear()
            sheet_detalhes.append_row(['Data', 'Produto', 'Quantidade', 'Preço Unit', 'Total', 'Canal', 'Categoria BCG', 'Data Upload'])
            for _, row in df_completo.iterrows():
                cat = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0] if row['Produto'] in produtos['Produto'].values else 'N/A'
                sheet_detalhes.append_row([
                    str(row.get('Data', '')),
                    row['Produto'],
                    int(row['Quantidade']) if pd.notna(row['Quantidade']) else 0,
                    float(row['Preço Unitário']) if pd.notna(row.get('Preço Unitário', 0)) else 0,
                    float(row['Total']) if pd.notna(row['Total']) else 0,
                    row.get('Canal', ''),
                    cat,
                    row.get('Data_Upload', '')
                ])
            
            st.success(f"✅ Análise completa! {len(df_completo)} registros totais ({len(df_novo)} novos)")
            st.info(f"📊 Histórico: {dias_analisados} dias analisados")
            st.info(f"🔗 [Abrir Planilha]({st.secrets['GOOGLE_SHEETS_URL']})")
            
        except Exception as e:
            st.error(f"❌ Erro: {str(e)}")
else:
    st.info("👈 Faça upload da planilha do dia")
    st.markdown("""
    ### Como funciona:
    1. **Primeiro dia**: Upload da planilha → Cria análise inicial
    2. **Dias seguintes**: Upload de novos dados → **Acumula** com anteriores
    3. **Histórico completo**: Análise evolutiva dia a dia
    4. **Recomendações CEO**: Baseadas em todo o período
    """)
