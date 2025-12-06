import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")
st.title("📊 Sales BI Analytics - Análise Completa")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

def converter_planilha_bling(df_bling, data_venda):
    df_convertido = pd.DataFrame()
    df_convertido['Data'] = data_venda
    df_convertido['Produto'] = df_bling['Código']
    df_convertido['Quantidade'] = df_bling['Quantidade']
    df_convertido['Total'] = df_bling['Valor'].apply(lambda x: 
        float(str(x).replace('R$', '').replace('.', '').replace(',', '.').strip())
    )
    df_convertido['Preço Unitário'] = df_convertido['Total'] / df_convertido['Quantidade']
    return df_convertido

with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Upload JSON de configurações
    config_file = st.file_uploader("📋 Config. Produtos/Canais (JSON)", type=['json'])
    if config_file:
        config = json.load(config_file)
        st.session_state['config'] = config
        st.success("✅ Configurações carregadas")
        
        # Mostrar resumo
        if 'produtos' in config:
            st.metric("Produtos cadastrados", len(config['produtos']))
        if 'canais' in config:
            st.metric("Canais configurados", len(config['canais']))
    
    st.divider()
    st.header("📤 Upload de Vendas")
    
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    
    if formato == 'Bling':
        data_venda = st.date_input("Data da Venda", datetime.now())
    
    uploaded_file = st.file_uploader("Planilha Excel", type=['xlsx', 'xls'])
    
    if uploaded_file and st.button("🔄 Processar"):
        try:
            df_original = pd.read_excel(uploaded_file)
            colunas = df_original.columns.tolist()
            
            if 'Código' in colunas and 'Valor' in colunas:
                st.info("✅ Formato Bling detectado")
                df_novo = converter_planilha_bling(df_original, data_venda.strftime('%Y-%m-%d'))
            else:
                df_novo = df_original.copy()
            
            df_novo['Canal'] = CHANNELS[canal]
            df_novo['Data_Upload'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Enriquecer com configurações
            if 'config' in st.session_state:
                config = st.session_state['config']
                
                # Adicionar custo e margem
                if 'produtos' in config:
                    produtos_config = {p['nome']: p for p in config['produtos']}
                    df_novo['Custo_Unit'] = df_novo['Produto'].apply(
                        lambda x: produtos_config.get(x, {}).get('custo', 0)
                    )
                    df_novo['Custo_Total'] = df_novo['Custo_Unit'] * df_novo['Quantidade']
                    df_novo['Margem_Bruta'] = df_novo['Total'] - df_novo['Custo_Total']
                
                # Adicionar taxas do canal
                if 'canais' in config:
                    canais_config = {c['nome']: c for c in config['canais']}
                    canal_info = canais_config.get(CHANNELS[canal], {})
                    taxa_var = canal_info.get('taxa_variavel', 0) / 100
                    taxa_fixa = canal_info.get('taxa_fixa', 0)
                    
                    df_novo['Taxa_Variavel'] = df_novo['Total'] * taxa_var
                    df_novo['Taxa_Fixa'] = taxa_fixa
                    df_novo['Lucro_Liquido'] = df_novo['Margem_Bruta'] - df_novo['Taxa_Variavel'] - df_novo['Taxa_Fixa']
            
            st.session_state['data_novo'] = df_novo
            
            st.subheader("Preview")
            st.dataframe(df_novo.head(10))
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Produtos", len(df_novo))
            col2.metric("Faturamento", f"R$ {df_novo['Total'].sum():,.2f}")
            if 'Lucro_Liquido' in df_novo.columns:
                col3.metric("Lucro Líquido", f"R$ {df_novo['Lucro_Liquido'].sum():,.2f}")
            
        except Exception as e:
            st.error(f"❌ {str(e)}")

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
                    for col in ['Quantidade', 'Total', 'Custo_Total', 'Margem_Bruta', 'Lucro_Liquido']:
                        if col in df_existente.columns:
                            df_existente[col] = pd.to_numeric(df_existente[col], errors='coerce')
                else:
                    df_existente = pd.DataFrame()
            except:
                df_existente = pd.DataFrame()
            
            try:
                sheet_detalhes = spreadsheet.worksheet("6. Detalhes")
            except:
                sheet_detalhes = spreadsheet.add_worksheet("6. Detalhes", 5000, 15)
            
            df_completo = pd.concat([df_existente, df_novo], ignore_index=True) if not df_existente.empty else df_novo
            
            # Análise de produtos
            agg_dict = {'Quantidade': 'sum', 'Total': 'sum'}
            if 'Custo_Total' in df_completo.columns:
                agg_dict['Custo_Total'] = 'sum'
                agg_dict['Margem_Bruta'] = 'sum'
            if 'Lucro_Liquido' in df_completo.columns:
                agg_dict['Lucro_Liquido'] = 'sum'
            
            produtos = df_completo.groupby('Produto').agg(agg_dict).reset_index()
            
            total_vendas = produtos['Total'].sum()
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
            try: sheet1 = spreadsheet.worksheet("1. Dashboard")
            except: sheet1 = spreadsheet.add_worksheet("1. Dashboard", 100, 5)
            
            lucro_total = produtos['Lucro_Liquido'].sum() if 'Lucro_Liquido' in produtos.columns else 0
            margem_total = produtos['Margem_Bruta'].sum() if 'Margem_Bruta' in produtos.columns else 0
            
            dados1 = [
                ['DASHBOARD EXECUTIVO'],
                [f'Atualizado: {datetime.now().strftime("%d/%m/%Y %H:%M")}'],
                [],
                ['PERÍODO TOTAL'],
                ['Dias', dias_analisados],
                ['Faturamento', f'R$ {total_vendas:,.2f}'],
                ['Margem Bruta', f'R$ {margem_total:,.2f}'],
                ['Lucro Líquido', f'R$ {lucro_total:,.2f}'],
                ['Produtos', len(produtos)],
                ['Unidades', int(df_completo['Quantidade'].sum())],
                [],
                ['MATRIZ BCG'],
                ['Categoria', 'Qtd', 'Faturamento', 'Lucro']
            ]
            
            for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                prods_cat = produtos[produtos['Categoria']==cat]
                lucro_cat = prods_cat['Lucro_Liquido'].sum() if 'Lucro_Liquido' in prods_cat.columns else 0
                emoji = {'Estrela': '⭐', 'Vaca Leiteira': '🐄', 'Interrogação': '❓', 'Abacaxi': '🍍'}[cat]
                dados1.append([
                    f'{emoji} {cat}',
                    len(prods_cat),
                    f'R$ {prods_cat["Total"].sum():,.2f}',
                    f'R$ {lucro_cat:,.2f}'
                ])
            
            sheet1.clear()
            sheet1.update('A1', dados1)
            
            # 2. Evolução
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
            except: sheet3 = spreadsheet.add_worksheet("3. BCG", 500, 6)
            
            dados3 = [['MATRIZ BCG'], []]
            for cat in ['Estrela', 'Vaca Leiteira', 'Interrogação', 'Abacaxi']:
                prods = produtos[produtos['Categoria'] == cat].head(20)
                dados3.append([f'{cat.upper()} ({len(produtos[produtos["Categoria"]==cat])})'])
                
                if 'Lucro_Liquido' in prods.columns:
                    dados3.append(['Produto', 'Qtd', 'Faturamento', 'Lucro', '% Part'])
                    for _, p in prods.iterrows():
                        dados3.append([p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'R$ {p["Lucro_Liquido"]:.2f}', f'{p["Participacao"]:.2f}%'])
                else:
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
            except: sheet4 = spreadsheet.add_worksheet("4. Pareto", 500, 7)
            
            dados4 = [
                ['PARETO 80/20'],
                [],
                [f'{len(pareto_80)} produtos = 80% vendas'],
                [f'Faturamento: R$ {pareto_80["Total"].sum():,.2f}'],
                []
            ]
            
            if 'Lucro_Liquido' in pareto_80.columns:
                dados4.append(['Rank', 'Produto', 'Qtd', 'Faturamento', 'Lucro', '% Acum', 'BCG'])
                for i, (_, p) in enumerate(pareto_80.iterrows(), 1):
                    dados4.append([i, p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'R$ {p["Lucro_Liquido"]:.2f}', f'{p["Acumulado"]*100:.1f}%', p['Categoria']])
            else:
                dados4.append(['Rank', 'Produto', 'Qtd', 'Faturamento', '% Acum', 'BCG'])
                for i, (_, p) in enumerate(pareto_80.iterrows(), 1):
                    dados4.append([i, p['Produto'], int(p['Quantidade']), f'R$ {p["Total"]:.2f}', f'{p["Acumulado"]*100:.1f}%', p['Categoria']])
            
            sheet4.clear()
            sheet4.update('A1', dados4)
            
            # 5. CEO
            try: sheet5 = spreadsheet.worksheet("5. CEO")
            except: sheet5 = spreadsheet.add_worksheet("5. CEO", 100, 3)
            
            estrelas = len(produtos[produtos['Categoria']=='Estrela'])
            vacas = len(produtos[produtos['Categoria']=='Vaca Leiteira'])
            interrogacoes = len(produtos[produtos['Categoria']=='Interrogação'])
            abacaxis = len(produtos[produtos['Categoria']=='Abacaxi'])
            
            dados5 = [
                ['RECOMENDAÇÕES CEO'],
                [f'{dias_analisados} dias | Lucro: R$ {lucro_total:,.2f}'],
                [],
                ['PRIORIDADE', 'AÇÃO', 'IMPACTO'],
                ['🔴 CRÍTICA', f'Investir {estrelas} Estrelas', 'Alto lucro + Alto volume'],
                ['🟡 ALTA', f'Manter {vacas} Vacas', 'Fluxo de caixa estável'],
                ['🟠 MÉDIA', f'Testar {interrogacoes} Interrogações', 'Potencial não explorado'],
                ['🔴 CRÍTICA', f'Liquidar {abacaxis} Abacaxis', 'Liberar capital parado'],
                [],
                ['FOCO PARETO'],
                [f'{len(pareto_80)} produtos = R$ {pareto_80["Total"].sum():,.2f}'],
            ]
            sheet5.clear()
            sheet5.update('A1', dados5)
            
            # 6. Detalhes
            colunas_detalhes = ['Data', 'Produto', 'Qtd', 'Preço', 'Total', 'Canal', 'BCG', 'Upload']
            if 'Custo_Total' in df_completo.columns:
                colunas_detalhes.insert(5, 'Custo')
                colunas_detalhes.insert(6, 'Margem')
            if 'Lucro_Liquido' in df_completo.columns:
                colunas_detalhes.insert(-2, 'Lucro')
            
            dados6 = [colunas_detalhes]
            for _, row in df_completo.iterrows():
                cat = produtos[produtos['Produto'] == row['Produto']]['Categoria'].values[0] if row['Produto'] in produtos['Produto'].values else 'N/A'
                linha = [
                    str(row.get('Data', '')),
                    row['Produto'],
                    int(row['Quantidade']) if pd.notna(row['Quantidade']) else 0,
                    float(row['Preço Unitário']) if pd.notna(row.get('Preço Unitário', 0)) else 0,
                    float(row['Total']) if pd.notna(row['Total']) else 0
                ]
                
                if 'Custo_Total' in row:
                    linha.append(float(row['Custo_Total']) if pd.notna(row['Custo_Total']) else 0)
                    linha.append(float(row['Margem_Bruta']) if pd.notna(row['Margem_Bruta']) else 0)
                
                if 'Lucro_Liquido' in row:
                    linha.append(float(row['Lucro_Liquido']) if pd.notna(row['Lucro_Liquido']) else 0)
                
                linha.extend([row.get('Canal', ''), cat, row.get('Data_Upload', '')])
                dados6.append(linha)
            
            sheet_detalhes.clear()
            sheet_detalhes.update('A1', dados6)
            
            st.success(f"✅ {len(df_completo)} registros ({len(df_novo)} novos)")
            st.info(f"📊 {dias_analisados} dias | Lucro: R$ {lucro_total:,.2f}")
            st.info(f"🔗 [Abrir]({st.secrets['GOOGLE_SHEETS_URL']})")
            
        except Exception as e:
            st.error(f"❌ {str(e)}")
else:
    st.info("👈 Configure e faça upload")
    st.markdown("""
    ### Como usar:
    
    1. **Upload JSON** (opcional): Configurações de produtos e canais
    2. **Upload Excel**: Planilha de vendas (Bling ou padrão)
    3. **Enviar**: Análise completa com margem e lucro
    
    **Com JSON**: Análise de lucro líquido por produto/canal
    **Sem JSON**: Análise de faturamento bruto (BCG, Pareto)
    """)
