import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
import io
import time

# ==============================================================================
# VERSÃO V22 - ORDENAÇÃO BCG E REVISÃO EMBALAGEM
# CORREÇÕES ACUMULADAS:
# 1. Autenticação restaurada
# 2. Matriz BCG implementada (Geral e Por Canal)
# 3. Correção de valores monetários (R$)
# 4. Correção de abas vazias e cabeçalhos
# 5. Correção de leitura de float com vírgula (Kits)
# 6. Limpeza de cache forçada
# 7. Proteção contra colunas ausentes
# 8. Arredondamento de margem
# 9. Aba '4. Preços Marketplaces' implementada
# 10. Relatório de Produtos Faltantes (Download)
# 11. Botões de Download dos Relatórios
# 12. Criação automática de abas inexistentes
# 13. Formatação de texto forçada (R$ e %) na planilha
# 14. Leitura inteligente de valores formatados
# 15. Botão de Atualização Manual (Limpar Cache)
# 16. Tratamento de 'nan' na aba de preços (substituído por '-')
# 17. Formatação forçada de R$ na aba de preços
# 18. NOVO: Ordenação BCG (Vaca -> Estrela -> Interrogação -> Abacaxi)
# ==============================================================================

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================
st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# ==============================================================================
# CONSTANTES E MAPEAMENTOS
# ==============================================================================
CHANNELS = {
    'geral': '📊 Vendas Gerais',
    'mercado_livre': '🛒 Mercado Livre',
    'shopee_matriz': '🛍️ Shopee Matriz',
    'shopee_150': '🏪 Shopee 1:50',
    'shein': '👗 Shein'
}

COLUNAS_ESPERADAS = [
    'Data', 'Canal', 'CNPJ', 'Produto', 'Tipo', 'Quantidade', 'Total Venda',
    'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 'Embalagem',
    'Investimento Ads', 'Custo Total', 'Lucro Bruto', 'Margem (%)'
]

# Ordem personalizada para BCG
ORDEM_BCG = ['Vaca Leiteira 🐄', 'Estrela ⭐', 'Interrogação ❓', 'Abacaxi 🍍']

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def clean_currency(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('R$', '').replace(' ', '').replace('%', '')
    try: return float(s_val)
    except: pass
    if ',' in s_val and '.' in s_val: s_val = s_val.replace('.', '').replace(',', '.')
    elif ',' in s_val: s_val = s_val.replace(',', '.')
    try: return float(s_val)
    except: return 0.0

def clean_percent_read(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace('%', '').replace(' ', '')
    if ',' in s_val: s_val = s_val.replace('.', '').replace(',', '.')
    try: return float(s_val) / 100
    except: return 0.0

def clean_float(value):
    if pd.isna(value) or value == '': return 0.0
    s_val = str(value).strip().replace(',', '.')
    try: return float(s_val)
    except: return 0.0

def format_currency_br(value):
    try: return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "R$ 0,00"

def format_percent_br(value):
    try: return f"{value * 100:.2f}%".replace(".", ",")
    except: return "0,00%"

def to_excel(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

# ==============================================================================
# CONEXÃO COM GOOGLE SHEETS
# ==============================================================================
@st.cache_resource
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
        creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        st.error("❌ Credenciais não encontradas no st.secrets.")
        st.stop()
    gc = gspread.authorize(creds)
    if "GOOGLE_SHEETS_URL" in st.secrets:
        ss = gc.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
        return ss, gc
    else:
        st.error("❌ URL da planilha não encontrada.")
        st.stop()

@st.cache_data(ttl=60)
def carregar_dados_detalhes():
    try:
        ss, _ = conectar_google_sheets()
        ws = ss.worksheet("6. Detalhes")
        all_values = ws.get_all_values()
        if not all_values: return pd.DataFrame(columns=COLUNAS_ESPERADAS)
        
        header_idx = -1
        for i, row in enumerate(all_values[:5]):
            if 'Total Venda' in row and 'Lucro Bruto' in row and 'Produto' in row:
                header_idx = i
                break
        
        if header_idx == -1: return pd.DataFrame(columns=COLUNAS_ESPERADAS)
            
        df = pd.DataFrame(all_values[header_idx+1:], columns=all_values[header_idx])
        
        cols_money = ['Total Venda', 'Custo Total', 'Lucro Bruto', 'Investimento Ads', 'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 'Embalagem']
        for col in cols_money:
            if col in df.columns: df[col] = df[col].apply(clean_currency)
            
        if 'Margem (%)' in df.columns:
            df['Margem (%)'] = df['Margem (%)'].apply(clean_percent_read)
            
        if 'Quantidade' in df.columns:
            df['Quantidade'] = df['Quantidade'].apply(clean_float)
            
        return df
    except: return pd.DataFrame(columns=COLUNAS_ESPERADAS)

@st.cache_data(ttl=3600)
def carregar_configuracoes():
    try:
        ss, gc = conectar_google_sheets()
        configs_data = {}
        estoque_produtos = set()
        
        if "TEMPLATE_ESTOQUE_URL" in st.secrets:
            try:
                ss_estoque = gc.open_by_url(st.secrets["TEMPLATE_ESTOQUE_URL"])
                ws_estoque = ss_estoque.worksheet('template_estoque')
                df_estoque = pd.DataFrame(ws_estoque.get_all_records())
                if 'codigo' in df_estoque.columns:
                    estoque_produtos = set(df_estoque['codigo'].tolist())
            except: pass
        
        abas_config = [("Produtos", "produtos"), ("Kits", "kits"), ("Canais", "canais"), 
                       ("Custos por Pedido", "custos_ped"), ("Impostos", "impostos"), 
                       ("Frete", "frete"), ("Metas", "metas")]
        
        for nome_aba, chave in abas_config:
            try:
                sh = ss.worksheet(nome_aba)
                data = sh.get_all_values()
                if len(data) > 1:
                    cols = data[0]
                    counts = {}
                    new_cols = []
                    for col in cols:
                        if col in counts: counts[col] += 1; new_cols.append(f"{col}_{counts[col]}")
                        else: counts[col] = 0; new_cols.append(col)
                    
                    df = pd.DataFrame(data[1:], columns=new_cols)
                    for col in df.columns:
                        if any(x in col for x in ['R$', '%', 'Peso', 'Custo', 'Preço', 'Taxa', 'Frete', 'Valor']):
                            df[col] = df[col].apply(clean_currency)
                    configs_data[chave] = df
            except: pass
        return configs_data, estoque_produtos
    except: return None, None

# ==============================================================================
# LÓGICA DE NEGÓCIO
# ==============================================================================
def classificar_bcg(row, median_vendas, median_margem):
    vendas = row['Total Venda']
    margem = row['Margem (%)']
    if vendas >= median_vendas and margem >= median_margem: return 'Estrela ⭐'
    elif vendas >= median_vendas and margem < median_margem: return 'Vaca Leiteira 🐄'
    elif vendas < median_vendas and margem >= median_margem: return 'Interrogação ❓'
    else: return 'Abacaxi 🍍'

def processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads_total):
    df_novo = pd.DataFrame()
    if 'Código' in df_orig.columns and 'Quantidade' in df_orig.columns:
        df_novo['Data'] = [data_venda] * len(df_orig)
        df_novo['Produto'] = df_orig['Código']
        df_novo['Quantidade'] = pd.to_numeric(df_orig['Quantidade'], errors='coerce').fillna(0)
        
        if 'Valor' in df_orig.columns: df_novo['Total'] = df_orig['Valor'].apply(clean_currency)
        elif 'Preço' in df_orig.columns: df_novo['Total'] = df_orig['Preço'].apply(clean_currency) * df_novo['Quantidade']
        else: df_novo['Total'] = 0.0
        df_novo['Preço Unitário'] = df_novo['Total'] / df_novo['Quantidade']
    else:
        st.error("Colunas obrigatórias não encontradas: 'Código', 'Quantidade', 'Valor' (ou 'Preço').")
        return None, None

    df_novo['Canal'] = CHANNELS[canal]
    df_novo['CNPJ'] = cnpj_regime

    produtos_df = st.session_state.get('produtos', pd.DataFrame())
    kits_df = st.session_state.get('kits', pd.DataFrame())
    impostos_df = st.session_state.get('impostos', pd.DataFrame())
    canais_df = st.session_state.get('canais', pd.DataFrame())
    custos_ped_df = st.session_state.get('custos_ped', pd.DataFrame())

    produtos_map = {}
    if not produtos_df.empty and 'Código' in produtos_df.columns:
        for _, row in produtos_df.iterrows():
            produtos_map[normalizar(str(row['Código']))] = {'custo': float(row.get('Custo (R$)', 0))}

    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    aliquota = 0.06
    if not impostos_df.empty and 'Tipo' in impostos_df.columns:
        m = impostos_df[impostos_df['Tipo'].str.contains(cnpj_regime.split()[0], case=False, na=False)]
        if not m.empty: aliquota = float(m.iloc[0]['Alíquota (%)']) / 100

    taxa_mp, taxa_fixa = 0.16, 5.0
    if not canais_df.empty and 'Canal' in canais_df.columns:
        m = canais_df[canais_df['Canal'].str.contains(canal.replace('_', ' '), case=False, na=False)]
        if not m.empty:
            taxa_mp = float(m.iloc[0].get('Taxa Marketplace (%)', 16)) / 100
            taxa_fixa = float(m.iloc[0].get('Taxa Fixa Pedido (R$)', 5))

    custo_emb = 0.0
    if not custos_ped_df.empty and 'Custo Unitário (R$)' in custos_ped_df.columns:
        custo_emb = custos_ped_df['Custo Unitário (R$)'].sum()

    resultados = []
    faltantes = []
    total_vendas_dia = df_novo['Total'].sum()

    for _, row in df_novo.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd = row['Quantidade']
        total_venda = row['Total']
        
        custo_produto = 0.0
        tipo = 'Produto'
        encontrado = False
        
        if prod_norm in kits_map:
            tipo = 'Kit'
            encontrado = True
            for comp in kits_map[prod_norm]:
                c_norm = normalizar(comp['sku'])
                if c_norm in produtos_map: custo_produto += produtos_map[c_norm]['custo'] * comp['qtd']
        elif prod_norm in produtos_map:
            custo_produto = produtos_map[prod_norm]['custo']
            encontrado = True
        
        if not encontrado:
            faltantes.append({'Código': prod_cod, 'Tipo': 'Não Cadastrado'})

        custo_total_prod = custo_produto * qtd
        imposto_val = total_venda * aliquota
        comissao_val = total_venda * taxa_mp
        taxa_fixa_val = taxa_fixa * qtd
        ads_rateio = (total_venda / total_vendas_dia) * custo_ads_total if total_vendas_dia > 0 else 0.0
        
        # Custo de embalagem é por unidade vendida (kit conta como 1 unidade)
        custo_total_geral = custo_total_prod + imposto_val + comissao_val + taxa_fixa_val + (custo_emb * qtd) + ads_rateio
        lucro = total_venda - custo_total_geral
        margem = (lucro / total_venda) if total_venda > 0 else 0.0
        
        resultados.append({
            'Data': row['Data'], 'Canal': row['Canal'], 'CNPJ': row['CNPJ'],
            'Produto': prod_cod, 'Tipo': tipo, 'Quantidade': qtd, 'Total Venda': total_venda,
            'Custo Produto': custo_total_prod, 'Impostos': imposto_val, 'Comissão': comissao_val,
            'Taxas Fixas': taxa_fixa_val, 'Embalagem': custo_emb * qtd, 'Investimento Ads': ads_rateio,
            'Custo Total': custo_total_geral, 'Lucro Bruto': lucro, 'Margem (%)': margem
        })
        
    return pd.DataFrame(resultados), pd.DataFrame(faltantes)

def atualizar_dashboards_resumo(df_detalhes):
    if df_detalhes.empty: return None, None, None, None, None
    
    cols_req = ['Canal', 'Total Venda', 'Lucro Bruto', 'Quantidade', 'Margem (%)', 'CNPJ', 'Produto']
    if not all(c in df_detalhes.columns for c in cols_req): return None, None, None, None, None

    dash_geral = df_detalhes.groupby('Canal').agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Quantidade': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    
    dash_cnpj = df_detalhes.groupby(['CNPJ', 'Canal']).agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    
    dash_exec = df_detalhes.groupby('Produto').agg({
        'Quantidade': 'sum', 'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    med_v = dash_exec['Total Venda'].median()
    med_m = dash_exec['Margem (%)'].median()
    dash_exec['Classificação BCG'] = dash_exec.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
    
    # Ordenação BCG Geral
    dash_exec['Classificação BCG'] = pd.Categorical(dash_exec['Classificação BCG'], categories=ORDEM_BCG, ordered=True)
    dash_exec = dash_exec.sort_values('Classificação BCG')
    
    dash_bcg_canal = df_detalhes.groupby(['Canal', 'Produto']).agg({
        'Total Venda': 'sum', 'Margem (%)': 'mean', 'Quantidade': 'sum'
    }).reset_index()
    bcg_final = []
    for canal in dash_bcg_canal['Canal'].unique():
        subset = dash_bcg_canal[dash_bcg_canal['Canal'] == canal].copy()
        med_v_c = subset['Total Venda'].median()
        med_m_c = subset['Margem (%)'].median()
        subset['Classificação'] = subset.apply(lambda x: classificar_bcg(x, med_v_c, med_m_c), axis=1)
        bcg_final.append(subset)
    
    df_bcg_final = pd.concat(bcg_final) if bcg_final else pd.DataFrame()
    if not df_bcg_final.empty:
        # Ordenação BCG por Canal
        df_bcg_final['Classificação'] = pd.Categorical(df_bcg_final['Classificação'], categories=ORDEM_BCG, ordered=True)
        df_bcg_final = df_bcg_final.sort_values(['Canal', 'Classificação'])

    df_precos = df_detalhes.groupby(['Produto', 'Canal']).agg({
        'Total Venda': 'sum', 'Quantidade': 'sum'
    }).reset_index()
    df_precos['Preço Médio'] = df_precos['Total Venda'] / df_precos['Quantidade']
    df_precos_pivot = df_precos.pivot(index='Produto', columns='Canal', values='Preço Médio').reset_index()

    return dash_geral, dash_cnpj, dash_exec, df_bcg_final, df_precos_pivot

# ==============================================================================
# INTERFACE
# ==============================================================================
try:
    ss, gc = conectar_google_sheets()
    configs, estoque_produtos = carregar_configuracoes()
    if configs:
        for key, df in configs.items(): st.session_state[key] = df
        st.session_state['estoque_produtos'] = estoque_produtos
except Exception as e:
    st.error(f"Erro conexão: {e}")
    st.stop()

st.title("📊 Sales BI Pro - Dashboard Executivo V22")

with st.sidebar:
    st.header("📥 Importar Vendas")
    
    # BOTÃO DE ATUALIZAÇÃO MANUAL
    if st.button("🔄 Atualizar Dados (Limpar Cache)"):
        carregar_dados_detalhes.clear()
        carregar_configuracoes.clear()
        st.success("Cache limpo! Recarregando...")
        time.sleep(1)
        st.rerun()
        
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_regime = st.selectbox("CNPJ/Regime", ['Simples Nacional', 'Lucro Presumido', 'Lucro Real'])
    data_venda = st.date_input("Data", datetime.now()) if formato == 'Bling' else datetime.now()
    custo_ads = st.number_input("💰 Ads (R$)", min_value=0.0, step=10.0)
    uploaded_file = st.file_uploader("Arquivo Excel", type=['xlsx'])
    
    if uploaded_file and st.button("🚀 Processar e Salvar"):
        with st.spinner("Processando..."):
            try:
                df_orig = pd.read_excel(uploaded_file)
                df_processado, df_faltantes = processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads)
                
                if df_processado is not None and not df_processado.empty:
                    ws_detalhes = ss.worksheet("6. Detalhes")
                    first_row = ws_detalhes.row_values(1)
                    if not first_row or 'Total Venda' not in first_row or 'Lucro Bruto' not in first_row:
                        ws_detalhes.clear()
                        ws_detalhes.append_row(COLUNAS_ESPERADAS)
                    
                    df_salvar = df_processado.copy()
                    for c in df_salvar.columns:
                        if 'Margem' in c: df_salvar[c] = df_salvar[c].apply(format_percent_br)
                        elif any(x in c for x in ['Venda', 'Lucro', 'Custo', 'Preço', 'Impostos', 'Comissão', 'Taxas', 'Embalagem', 'Ads']): 
                            df_salvar[c] = df_salvar[c].apply(format_currency_br)
                    
                    df_salvar = df_salvar[COLUNAS_ESPERADAS]
                    ws_detalhes.append_rows(df_salvar.astype(str).values.tolist())
                    st.success(f"✅ {len(df_processado)} vendas salvas!")
                    
                    carregar_dados_detalhes.clear()
                    df_historico = carregar_dados_detalhes()
                    if not df_historico.empty:
                        d_geral, d_cnpj, d_exec, d_bcg, d_precos = atualizar_dashboards_resumo(df_historico)
                        
                        def salvar_aba(nome, df):
                            try:
                                try:
                                    ws = ss.worksheet(nome)
                                except:
                                    ws = ss.add_worksheet(title=nome, rows=1000, cols=20)
                                
                                ws.clear()
                                df_fmt = df.copy()
                                
                                if nome == "4. Preços Marketplaces":
                                    for col in df_fmt.columns:
                                        if col != 'Produto':
                                            df_fmt[col] = df_fmt[col].apply(lambda x: format_currency_br(x) if pd.notna(x) and x != 0 else "-")
                                else:
                                    for c in df_fmt.columns:
                                        if 'Margem' in c: df_fmt[c] = df_fmt[c].apply(format_percent_br)
                                        elif any(x in c for x in ['Venda', 'Lucro', 'Custo', 'Preço']): df_fmt[c] = df_fmt[c].apply(format_currency_br)
                                
                                ws.update([df_fmt.columns.values.tolist()] + df_fmt.astype(str).values.tolist())
                            except Exception as e: st.error(f"Erro ao salvar aba {nome}: {e}")

                        if d_geral is not None: salvar_aba("1. Dashboard Geral", d_geral)
                        if d_cnpj is not None: salvar_aba("2. Análise por CNPJ", d_cnpj)
                        if d_exec is not None: salvar_aba("3. Análise Executiva", d_exec)
                        if d_precos is not None: salvar_aba("4. Preços Marketplaces", d_precos)
                        if d_bcg is not None: salvar_aba("5. Matriz BCG", d_bcg)
                        
                        st.success("Dashboards atualizados!")
                        
                        if not df_faltantes.empty:
                            st.warning(f"⚠️ {len(df_faltantes)} produtos não encontrados no cadastro!")
                            st.download_button("📥 Baixar Lista de Faltantes", 
                                               data=to_excel(df_faltantes), 
                                               file_name="produtos_faltantes.xlsx")
                        
                        time.sleep(1)
                        st.rerun()
                    else: st.warning("Dados salvos, mas histórico parece vazio.")
            except Exception as e: st.error(f"Erro: {e}")

st.divider()
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", "💲 Preços", "📋 Detalhes"])
df_detalhes = carregar_dados_detalhes()

if not df_detalhes.empty and 'Total Venda' in df_detalhes.columns:
    d_geral, d_cnpj, d_exec, d_bcg, d_precos = atualizar_dashboards_resumo(df_detalhes)

    with tab1:
        st.metric("Vendas Totais", format_currency_br(df_detalhes['Total Venda'].sum()))
        st.bar_chart(df_detalhes.groupby('Canal')['Total Venda'].sum())
        st.download_button("📥 Baixar Resumo Geral", data=to_excel(d_geral), file_name="resumo_geral.xlsx")
    with tab2:
        st.dataframe(d_cnpj.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar Análise CNPJ", data=to_excel(d_cnpj), file_name="analise_cnpj.xlsx")
    with tab3:
        st.subheader("Matriz BCG Geral")
        st.dataframe(d_exec.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar BCG Geral", data=to_excel(d_exec), file_name="bcg_geral.xlsx")
    with tab4:
        st.subheader("Matriz BCG por Canal")
        st.dataframe(d_bcg.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar BCG por Canal", data=to_excel(d_bcg), file_name="bcg_canal.xlsx")
    with tab5:
        st.subheader("Preços Médios por Marketplace")
        st.dataframe(d_precos.style.format(lambda x: f"R$ {x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else ("-" if pd.isna(x) else x)))
        st.download_button("📥 Baixar Preços", data=to_excel(d_precos), file_name="precos_marketplaces.xlsx")
    with tab6:
        st.dataframe(df_detalhes)
        st.download_button("📥 Baixar Detalhes Completos", data=to_excel(df_detalhes), file_name="detalhes_vendas.xlsx")
else:
    st.info("Aguardando dados...")
