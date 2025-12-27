import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import unicodedata
import io
import time
import requests
import math
from io import StringIO
import xlsxwriter

# ==============================================================================
# CONFIGURAÇÕES GERAIS
# ==============================================================================
st.set_page_config(page_title="Sales BI Pro + MRP Fábrica", page_icon="🏭", layout="wide")

# URLs das Planilhas (MANTIDAS DA VERSÃO V49 ESTÁVEL)
BCG_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv&gid=961459380"
# URL da aba Kits para correção de cadastro
KITS_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv&gid=1605252243" # GID da aba Kits (assumido, será verificado)
# URL do Estoque (RESTAURADA DA VERSÃO V33)
ESTOQUE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"

# Constantes de Mapeamento
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

ORDEM_BCG = ['Vaca Leiteira 🐄', 'Estrela ⭐', 'Interrogação ❓', 'Abacaxi 🍍']

# ==============================================================================
# FUNÇÕES UTILITÁRIAS (MANTIDAS DA V49)
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

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

def normalize_key(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace('ß', 'ss')
    s = ''.join(ch for ch in s if ch.isalnum() or ch == '-')
    return s.upper().strip()

def safe_int(x, default=0):
    try:
        if x is None: return default
        if isinstance(x, float) and math.isnan(x): return default
        if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null", "n/a"}: return default
        return int(float(str(x).replace(",", ".")))
    except: return default

def parse_int_list(value):
    if value is None: return []
    if isinstance(value, float) and math.isnan(value): return []
    parts = [p.strip() for p in str(value).split(",")]
    out = []
    for p in parts:
        if not p: continue
        v = safe_int(p, None)
        if v is not None: out.append(v)
    return out

# ==============================================================================
# FUNÇÕES DE ESTOQUE E MRP (RESTAURADAS DA V33)
# ==============================================================================
@st.cache_data(ttl=60)
def carregar_estoque_externo():
    try:
        r = requests.get(ESTOQUE_SHEETS_URL, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        
        req = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max']
        for c in req:
            if c not in df.columns: df[c] = 0
            
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'], errors='coerce').fillna(0)
        
        for c in ['componentes', 'quantidades', 'eh_kit']:
            if c not in df.columns: df[c] = ''
            else: df[c] = df[c].astype(str).fillna('')
            
        df['codigo_key'] = df['codigo'].astype(str).map(normalize_key)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar estoque externo: {e}")
        return pd.DataFrame()

def calcular_mrp_recursivo(codigo_key, qtd_necessaria, df_estoque, nivel=0, caminho=""):
    acoes = []
    produto = df_estoque[df_estoque['codigo_key'] == codigo_key]
    if produto.empty:
        acoes.append({
            'nivel': nivel, 'codigo': codigo_key, 'nome': f"PRODUTO NÃO ENCONTRADO ({codigo_key})",
            'acao': 'ERRO_CADASTRO', 'qtd': qtd_necessaria, 'estoque_atual': 0, 'caminho': caminho
        })
        return acoes

    row = produto.iloc[0]
    nome = row['nome']
    estoque_atual = safe_int(row['estoque_atual'])
    eh_kit = str(row.get('eh_kit', '')).strip().lower() == 'sim'
    
    qtd_usar_estoque = min(estoque_atual, qtd_necessaria)
    qtd_faltante = qtd_necessaria - qtd_usar_estoque
    
    if qtd_usar_estoque > 0:
        acoes.append({
            'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
            'acao': 'SEPARAR_ESTOQUE', 'qtd': qtd_usar_estoque, 'estoque_atual': estoque_atual, 'caminho': caminho
        })
        
    if qtd_faltante > 0:
        if eh_kit:
            comps = [normalize_key(c.strip()) for c in str(row.get('componentes', '')).split(',') if c.strip()]
            quants = parse_int_list(row.get('quantidades', ''))
            
            if comps and quants and len(comps) == len(quants):
                acoes.append({
                    'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                    'acao': 'PRODUZIR_MONTAR', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
                })
                for comp_key, comp_qtd_unit in zip(comps, quants):
                    qtd_comp_total = qtd_faltante * comp_qtd_unit
                    novo_caminho = f"{caminho} > {nome}" if caminho else nome
                    acoes_filho = calcular_mrp_recursivo(comp_key, qtd_comp_total, df_estoque, nivel + 1, novo_caminho)
                    acoes.extend(acoes_filho)
            else:
                acoes.append({
                    'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                    'acao': 'ERRO_RECEITA', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
                })
        else:
            acoes.append({
                'nivel': nivel, 'codigo': row['codigo'], 'nome': nome,
                'acao': 'COMPRAR_PRODUZIR_EXTERNO', 'qtd': qtd_faltante, 'estoque_atual': estoque_atual, 'caminho': caminho
            })
    return acoes

def processar_mrp_fila(df_vendas_fila, df_estoque):
    vendas_agrupadas = df_vendas_fila.groupby('Produto')['Quantidade'].sum().reset_index()
    plano_mrp = []
    for _, row in vendas_agrupadas.iterrows():
        cod_key = normalize_key(row['Produto'])
        qtd = safe_int(row['Quantidade'])
        acoes = calcular_mrp_recursivo(cod_key, qtd, df_estoque)
        plano_mrp.extend(acoes)
    return pd.DataFrame(plano_mrp)

def gerar_excel_hierarquico(df_vendas_fila, df_estoque):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1})
    fmt_pai = workbook.add_format({'bold': True, 'bg_color': '#EFEFEF', 'border': 1})
    fmt_filho = workbook.add_format({'indent': 2, 'border': 1})
    fmt_check = workbook.add_format({'border': 1})
    
    mapa_produto_semi = {}
    for _, row in df_estoque.iterrows():
        if str(row.get('eh_kit', '')).lower() == 'sim':
            comps_cods = [normalize_key(c.strip()) for c in str(row.get('componentes', '')).split(',') if c.strip()]
            if comps_cods:
                semi_cod = comps_cods[0]
                semi_row = df_estoque[df_estoque['codigo_key'] == semi_cod]
                if not semi_row.empty:
                    mapa_produto_semi[row['codigo_key']] = semi_row.iloc[0]['nome']

    canais = df_vendas_fila['Canal'].unique()
    
    for canal in canais:
        safe_canal = str(canal).replace('/', '_').replace('\\', '_')[:30]
        ws = workbook.add_worksheet(safe_canal)
        
        ws.write(0, 0, "Produto (Semi / Acabamento)", fmt_header)
        ws.write(0, 1, "Quantidade Total", fmt_header)
        ws.write(0, 2, "Check Produção", fmt_header)
        ws.set_column(0, 0, 50)
        ws.set_column(1, 2, 15)
        
        df_canal = df_vendas_fila[df_vendas_fila['Canal'] == canal]
        vendas_agrupadas = df_canal.groupby('Produto')['Quantidade'].sum().reset_index()
        
        hierarquia = {}
        for _, row in vendas_agrupadas.iterrows():
            prod_nome = row['Produto']
            qtd = row['Quantidade']
            prod_key = normalize_key(prod_nome)
            
            semi_nome = mapa_produto_semi.get(prod_key, "OUTROS / SEMI NÃO IDENTIFICADO")
            
            if semi_nome not in hierarquia: hierarquia[semi_nome] = []
            hierarquia[semi_nome].append({'produto': prod_nome, 'qtd': qtd})
            
        row_idx = 1
        for semi in sorted(hierarquia.keys()):
            total_semi = sum(item['qtd'] for item in hierarquia[semi])
            ws.write(row_idx, 0, f"SEMI: {semi}", fmt_pai)
            ws.write(row_idx, 1, total_semi, fmt_pai)
            row_idx += 1
            
            for item in hierarquia[semi]:
                ws.write(row_idx, 0, item['produto'], fmt_filho)
                ws.write(row_idx, 1, item['qtd'], fmt_filho)
                ws.write(row_idx, 2, "[   ]", fmt_check)
                row_idx += 1
            
    workbook.close()
    return output.getvalue()

# ==============================================================================
# NOVA FUNÇÃO: GERAR EXCEL DE CORREÇÃO DE CADASTRO
# ==============================================================================
def gerar_excel_correcao_cadastro():
    try:
        # Tenta ler a aba "Kits" da planilha de BI
        # GID da aba Kits: 1605252243 (verificado no arquivo Config_BI_Final_MatrizBCG.xlsx)
        url_kits = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv&gid=1605252243"
        df_kits = pd.read_csv(url_kits)
        
        # Prepara o DataFrame no formato da template_estoque
        df_export = pd.DataFrame()
        df_export['codigo'] = df_kits['Código Kit']
        df_export['eh_kit'] = 'Sim'
        df_export['componentes'] = df_kits['SKUs Componentes'].str.replace(';', ',') # Ajusta separador se necessário
        df_export['quantidades'] = df_kits['Qtd Componentes'].str.replace(';', ',') # Ajusta separador se necessário
        
        # Gera o Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Correcao_Cadastro')
            
            # Formatação básica
            workbook = writer.book
            worksheet = writer.sheets['Correcao_Cadastro']
            fmt_header = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1})
            for col_num, value in enumerate(df_export.columns.values):
                worksheet.write(0, col_num, value, fmt_header)
            worksheet.set_column(0, 0, 30) # Coluna Codigo
            worksheet.set_column(1, 1, 10) # Coluna eh_kit
            worksheet.set_column(2, 3, 50) # Colunas componentes e quantidades
            
        return output.getvalue()
    except Exception as e:
        st.error(f"Erro ao gerar arquivo de correção: {e}")
        return None

# ==============================================================================
# LÓGICA DE DADOS E CACHE (MANTIDA DA V49)
# ==============================================================================
@st.cache_data(ttl=600)
def carregar_dados_detalhes():
    try:
        url = BCG_SHEETS_URL
        df = pd.read_csv(url)
        
        cols_num = ['Total Venda', 'Lucro Bruto', 'Quantidade', 'Margem (%)', 'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 'Embalagem', 'Investimento Ads', 'Custo Total']
        for col in cols_num:
            if col in df.columns:
                if 'Margem' in col: df[col] = df[col].apply(clean_percent_read)
                else: df[col] = df[col].apply(clean_currency)
        
        df['Quantidade'] = pd.to_numeric(df['Quantidade'], errors='coerce').fillna(0).astype(int)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

def classificar_bcg(row, med_venda, med_margem):
    venda = row['Total Venda']
    margem = row['Margem (%)']
    if venda >= med_venda and margem >= med_margem: return 'Estrela ⭐'
    elif venda >= med_venda and margem < med_margem: return 'Vaca Leiteira 🐄'
    elif venda < med_venda and margem >= med_margem: return 'Interrogação ❓'
    else: return 'Abacaxi 🍍'

def obter_status_meta(valor, metas):
    if not metas: return "N/A"
    meta_margem = metas.get('Margem (%)', 0.30)
    return "✅ Meta Batida" if valor >= meta_margem else "❌ Abaixo da Meta"

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================
with st.sidebar:
    st.title("Importar Novas Vendas")
    
    if st.button("🔄 Atualizar Dados (Limpar Cache)"):
        carregar_dados_detalhes.clear()
        st.rerun()
        
    st.divider()
    
    # CORREÇÃO CRÍTICA: Key para evitar erro removeChild
    modo_simulacao = st.checkbox("🧪 Modo Simulação", value=False, key="sandbox_mode")
    
    if modo_simulacao:
        st.warning("⚠️ MODO SIMULAÇÃO ATIVO\nNenhum dado será salvo no banco de dados.")
    
    st.divider()
    
    formato = st.radio("Formato", ["Bling", "Padrão"])
    canal_selecionado = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_selecionado = st.selectbox("CNPJ/Regime", ["Simples Nacional", "Lucro Presumido", "MEI"])
    data_venda = st.date_input("Data", datetime.now())
    ads_valor = st.number_input("Ads (R$)", min_value=0.0, step=10.0)
    
    uploaded_file = st.file_uploader("Arquivo Excel", type=['xlsx', 'xls'])
    
    if uploaded_file:
        try:
            df_upload = pd.read_excel(uploaded_file)
            
            # Normalização de colunas
            cols_map = {c: normalizar(c) for c in df_upload.columns}
            col_prod = next((c for c, n in cols_map.items() if 'produto' in n or 'descricao' in n), None)
            col_qtd = next((c for c, n in cols_map.items() if 'quantidade' in n or 'qtd' in n), None)
            col_val = next((c for c, n in cols_map.items() if 'valor' in n or 'total' in n or 'preco' in n), None)
            
            if not col_prod or not col_qtd:
                st.error("Colunas 'Produto' e 'Quantidade' não encontradas no Excel.")
            else:
                df_processado = df_upload.copy()
                df_processado = df_processado.rename(columns={col_prod: 'Produto', col_qtd: 'Quantidade', col_val: 'Total Venda'})
                
                # Preenchimento de dados faltantes
                df_processado['Data'] = data_venda
                df_processado['Canal'] = CHANNELS[canal_selecionado]
                df_processado['CNPJ'] = cnpj_selecionado
                df_processado['Investimento Ads'] = ads_valor
                
                # Cálculos básicos (simplificados para manter compatibilidade)
                df_processado['Total Venda'] = pd.to_numeric(df_processado['Total Venda'], errors='coerce').fillna(0)
                df_processado['Quantidade'] = pd.to_numeric(df_processado['Quantidade'], errors='coerce').fillna(0)
                
                # Adicionar à fila de processamento (Simulação ou Real)
                if st.button("Processar Arquivo"):
                    if 'fila_simulacao' not in st.session_state: st.session_state['fila_simulacao'] = pd.DataFrame()
                    if 'fila_baixa_estoque' not in st.session_state: st.session_state['fila_baixa_estoque'] = pd.DataFrame()
                    
                    if modo_simulacao:
                        st.session_state['fila_simulacao'] = pd.concat([st.session_state['fila_simulacao'], df_processado], ignore_index=True)
                        st.success(f"🧪 {len(df_processado)} vendas adicionadas à fila de SIMULAÇÃO.")
                    else:
                        st.session_state['fila_baixa_estoque'] = pd.concat([st.session_state['fila_baixa_estoque'], df_processado], ignore_index=True)
                        st.success(f"✅ {len(df_processado)} vendas adicionadas à fila REAL.")
                        
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

# ==============================================================================
# DASHBOARD PRINCIPAL
# ==============================================================================
st.title("📊 Sales BI Pro + 🏭 MRP Fábrica")

# Carregar dados
df_detalhes = carregar_dados_detalhes()

# Abas
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", 
    "💲 Preços", "📋 Detalhes", "📦 Giro de Produtos", "🚀 Oportunidades", "🏭 MRP Fábrica"
])

if not df_detalhes.empty:
    # Lógica de Dashboards (Mantida da V49)
    with tab1:
        total_venda = df_detalhes['Total Venda'].sum()
        margem_media = df_detalhes['Margem (%)'].mean()
        ticket_medio = df_detalhes['Total Venda'].mean()
        c1, c2, c3 = st.columns(3)
        c1.metric("Vendas Totais", format_currency_br(total_venda))
        c2.metric("Margem Média", format_percent_br(margem_media))
        c3.metric("Ticket Médio", format_currency_br(ticket_medio))
        
        fig_vendas = px.bar(df_detalhes.groupby('Canal')['Total Venda'].sum().reset_index(), x='Canal', y='Total Venda', title="Vendas por Canal")
        st.plotly_chart(fig_vendas, use_container_width=True)

    with tab2:
        df_cnpj = df_detalhes.groupby('CNPJ')['Total Venda'].sum().reset_index()
        fig_cnpj = px.pie(df_cnpj, values='Total Venda', names='CNPJ', title="Vendas por CNPJ")
        st.plotly_chart(fig_cnpj, use_container_width=True)
        st.dataframe(df_detalhes.groupby(['CNPJ', 'Canal'])['Total Venda'].sum().reset_index())

    with tab3:
        med_v = df_detalhes['Total Venda'].median()
        med_m = df_detalhes['Margem (%)'].median()
        df_bcg = df_detalhes.groupby('Produto').agg({'Total Venda': 'sum', 'Margem (%)': 'mean', 'Quantidade': 'sum'}).reset_index()
        df_bcg['Classificação'] = df_bcg.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
        
        fig_bcg = px.scatter(df_bcg, x='Margem (%)', y='Quantidade', size='Total Venda', color='Classificação',
                             hover_name='Produto', title="Matriz BCG Geral",
                             color_discrete_map={'Estrela ⭐': 'gold', 'Vaca Leiteira 🐄': 'silver', 'Interrogação ❓': 'blue', 'Abacaxi 🍍': 'red'})
        st.plotly_chart(fig_bcg, use_container_width=True)

    with tab4:
        canal_bcg = st.selectbox("Selecione o Canal", df_detalhes['Canal'].unique())
        df_canal = df_detalhes[df_detalhes['Canal'] == canal_bcg]
        if not df_canal.empty:
            med_v_c = df_canal['Total Venda'].median()
            med_m_c = df_canal['Margem (%)'].median()
            df_bcg_c = df_canal.groupby('Produto').agg({'Total Venda': 'sum', 'Margem (%)': 'mean', 'Quantidade': 'sum'}).reset_index()
            df_bcg_c['Classificação'] = df_bcg_c.apply(lambda x: classificar_bcg(x, med_v_c, med_m_c), axis=1)
            
            fig_bcg_c = px.scatter(df_bcg_c, x='Margem (%)', y='Quantidade', size='Total Venda', color='Classificação',
                                 hover_name='Produto', title=f"Matriz BCG - {canal_bcg}",
                                 color_discrete_map={'Estrela ⭐': 'gold', 'Vaca Leiteira 🐄': 'silver', 'Interrogação ❓': 'blue', 'Abacaxi 🍍': 'red'})
            st.plotly_chart(fig_bcg_c, use_container_width=True)

    with tab5:
        st.dataframe(df_detalhes.groupby(['Produto', 'Canal'])['Total Venda'].mean().unstack())

    with tab6:
        st.dataframe(df_detalhes)

    with tab7:
        st.dataframe(df_detalhes.groupby('Produto')['Quantidade'].sum().sort_values(ascending=False))

    with tab8:
        st.info("Funcionalidade de Oportunidades em desenvolvimento.")

    # ABA MRP FÁBRICA (RESTAURADA DA V33 + NOVO BOTÃO DE CORREÇÃO)
    with tab9:
        st.subheader("🏭 MRP - Planejamento de Produção em Cascata")
        
        if modo_simulacao:
            st.warning("🧪 EXIBINDO DADOS DE SIMULAÇÃO (NADA SERÁ SALVO)")
            df_vendas_fila = st.session_state.get('fila_simulacao', pd.DataFrame())
        else:
            df_vendas_fila = st.session_state.get('fila_baixa_estoque', pd.DataFrame())
            
        col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
        with col_ctrl1:
            if st.button("🔄 Carregar Estoque Externo"):
                carregar_estoque_externo.clear()
                st.success("Estoque recarregado!")
        with col_ctrl2:
            if st.button("🗑️ Limpar Fila"):
                if modo_simulacao: st.session_state['fila_simulacao'] = pd.DataFrame()
                else: st.session_state['fila_baixa_estoque'] = pd.DataFrame()
                st.success("Fila limpa!")
                time.sleep(1)
                st.rerun()
        with col_ctrl3:
            # NOVO BOTÃO DE CORREÇÃO
            excel_correcao = gerar_excel_correcao_cadastro()
            if excel_correcao:
                st.download_button(
                    label="🛠️ Baixar Correção de Cadastro",
                    data=excel_correcao,
                    file_name="correcao_cadastro_kits.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="Baixa um Excel com os dados de Kits da planilha de BI para corrigir a planilha de Estoque."
                )
            
        df_estoque_ext = carregar_estoque_externo()
        
        if df_estoque_ext.empty:
            st.error("Não foi possível carregar o estoque externo.")
        else:
            if df_vendas_fila.empty:
                st.info("ℹ️ A fila de vendas está vazia.")
            else:
                st.subheader(f"Plano de Produção ({len(df_vendas_fila)} vendas na fila)")
                
                # PROCESSAMENTO MRP
                df_mrp = processar_mrp_fila(df_vendas_fila, df_estoque_ext)
                
                if df_mrp.empty:
                    st.warning("Nenhuma ação necessária.")
                else:
                    st.write("### 📋 O que precisa ser feito?")
                    acoes_order = ['SEPARAR_ESTOQUE', 'PRODUZIR_MONTAR', 'COMPRAR_PRODUZIR_EXTERNO', 'ERRO_CADASTRO', 'ERRO_RECEITA']
                    for acao in acoes_order:
                        itens = df_mrp[df_mrp['acao'] == acao]
                        if not itens.empty:
                            itens_agrupados = itens.groupby(['codigo', 'nome'])['qtd'].sum().reset_index()
                            with st.expander(f"{acao.replace('_', ' ')} ({len(itens_agrupados)} itens)", expanded=True):
                                st.dataframe(itens_agrupados)
                    
                    st.divider()
                    
                    # GERAÇÃO DE EXCEL HIERÁRQUICO
                    try:
                        excel_bytes = gerar_excel_hierarquico(df_vendas_fila, df_estoque_ext)
                        st.download_button(
                            label="📥 Baixar Ordem de Produção (Excel Hierárquico)",
                            data=excel_bytes,
                            file_name=f"ordem_producao_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary"
                        )
                    except Exception as e:
                        st.error(f"Erro ao gerar Excel: {e}")
else:
    st.info("Aguardando dados...")
