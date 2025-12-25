import streamlit as st
import pandas as pd
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

# ==============================================================================
# VERSÃO V30 - SUPER APP COM FILA ACUMULATIVA E RASTREABILIDADE
# ==============================================================================
# MANTÉM TODA A LÓGICA DA V29 E ADICIONA ACUMULAÇÃO DE VENDAS PARA ESTOQUE
# ==============================================================================

st.set_page_config(page_title="Sales BI Pro + Estoque", page_icon="🏭", layout="wide")

# ==============================================================================
# CONFIGURAÇÕES DO MÓDULO DE ESTOQUE (IMPORTADO DO OUTRO APP)
# ==============================================================================
ESTOQUE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
ESTOQUE_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"

# ==============================================================================
# CONSTANTES E MAPEAMENTOS (BI FINANCEIRO)
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

ORDEM_BCG = ['Vaca Leiteira 🐄', 'Estrela ⭐', 'Interrogação ❓', 'Abacaxi 🍍']

# ==============================================================================
# FUNÇÕES UTILITÁRIAS (GERAL)
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
# FUNÇÕES ESPECÍFICAS DO MÓDULO DE ESTOQUE (IMPORTADAS E ADAPTADAS)
# ==============================================================================
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

def normalize_key(s: str) -> str:
    if s is None: return ""
    s = str(s)
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    s = s.replace('ß', 'ss')
    s = ''.join(ch for ch in s if ch.isalnum() or ch == '-')
    return s.upper().strip()

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

def expandir_kits_estoque_acumulado(df_vendas_acumulado, df_estoque):
    # Prepara mapa de kits do estoque externo
    key_to_code = dict(zip(df_estoque['codigo_key'], df_estoque['codigo'].astype(str)))
    kits = {}
    for _, row in df_estoque.iterrows():
        if str(row.get('eh_kit', '')).strip().lower() == 'sim':
            kit_key = row['codigo_key']
            comps = [normalize_key(c.strip()) for c in str(row.get('componentes', '')).split(',') if c.strip()]
            quants = parse_int_list(row.get('quantidades', ''))
            if comps and quants and len(comps) == len(quants):
                kits[kit_key] = list(zip(comps, quants))
    
    linhas = []
    # df_vendas_acumulado tem colunas: Produto, Quantidade, Canal
    for _, row in df_vendas_acumulado.iterrows():
        qty = safe_int(row.get('Quantidade', 0), 0)
        code_key = normalize_key(row['Produto'])
        canal = row.get('Canal', 'Desconhecido')
        
        if code_key in kits:
            for comp_key, comp_qty in kits[code_key]:
                linhas.append({
                    'codigo_key': comp_key, 
                    'quantidade': qty * safe_int(comp_qty, 0),
                    'origem': canal
                })
        else:
            linhas.append({
                'codigo_key': code_key, 
                'quantidade': qty,
                'origem': canal
            })
            
    if not linhas: return pd.DataFrame()
    
    df = pd.DataFrame(linhas)
    
    # Agrupa somando quantidade e concatenando origens únicas
    df_agrupado = df.groupby('codigo_key').agg({
        'quantidade': 'sum',
        'origem': lambda x: ', '.join(sorted(set(x)))
    }).reset_index()
    
    # Enriquece com dados do estoque
    est_map = {}
    for _, r in df_estoque.iterrows():
        est_map[r['codigo_key']] = {
            'nome': r.get('nome', 'N/A'),
            'estoque_atual': r.get('estoque_atual', 0),
            'codigo_canonical': r.get('codigo', '')
        }
        
    df_agrupado['encontrado'] = df_agrupado['codigo_key'].isin(est_map.keys())
    
    df_ok = df_agrupado[df_agrupado['encontrado']].copy()
    if not df_ok.empty:
        df_ok['nome'] = df_ok['codigo_key'].map(lambda k: est_map[k]['nome'])
        df_ok['estoque_atual'] = df_ok['codigo_key'].map(lambda k: est_map[k]['estoque_atual'])
        df_ok['codigo_canonical'] = df_ok['codigo_key'].map(lambda k: est_map[k]['codigo_canonical'])
        df_ok['estoque_final'] = df_ok['estoque_atual'] - df_ok['quantidade']
        
    return df_ok

def movimentar_estoque_webhook(codigo, quantidade, tipo, colaborador):
    try:
        payload = {
            'codigo': codigo,
            'quantidade': safe_int(quantidade, 0),
            'tipo': tipo,
            'colaborador': colaborador
        }
        r = requests.post(ESTOQUE_WEBHOOK_URL, json=payload, timeout=20)
        return r.json()
    except Exception as e:
        return {'success': False, 'message': f'Erro: {str(e)}'}

# ==============================================================================
# CONEXÃO COM GOOGLE SHEETS (BI FINANCEIRO)
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
# LÓGICA DE NEGÓCIO (BI FINANCEIRO)
# ==============================================================================
def classificar_bcg(row, median_vendas, median_margem):
    vendas = row['Total Venda']
    margem = row['Margem (%)']
    if vendas >= median_vendas and margem >= median_margem: return 'Estrela ⭐'
    elif vendas >= median_vendas and margem < median_margem: return 'Vaca Leiteira 🐄'
    elif vendas < median_vendas and margem >= median_margem: return 'Interrogação ❓'
    else: return 'Abacaxi 🍍'

def obter_status_meta(margem, metas):
    try:
        minima = float(metas.get('Margem Líquida Mínima (%)', 10)) / 100
        ideal = float(metas.get('Margem Líquida Ideal (%)', 15)) / 100
        
        if margem >= ideal: return '🟢 Ideal'
        elif margem >= minima: return '🟡 Atenção'
        else: return '🔴 Crítico'
    except: return '⚪ N/A'

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
        erro_motivo = ""
        
        if prod_norm in kits_map:
            tipo = 'Kit'
            encontrado = True
            for comp in kits_map[prod_norm]:
                c_norm = normalizar(comp['sku'])
                if c_norm in produtos_map:
                    c_custo = produtos_map[c_norm]['custo']
                    if c_custo <= 0:
                        encontrado = False
                        erro_motivo = f"Componente {comp['sku']} com Custo Zero"
                        break
                    custo_produto += c_custo * comp['qtd']
                else:
                    encontrado = False
                    erro_motivo = f"Componente {comp['sku']} não cadastrado"
                    break
        elif prod_norm in produtos_map:
            custo_produto = produtos_map[prod_norm]['custo']
            if custo_produto > 0:
                encontrado = True
            else:
                erro_motivo = "Custo Zero no Cadastro"
        else:
            erro_motivo = "Produto não cadastrado"
        
        if not encontrado:
            faltantes.append({'Código': prod_cod, 'Motivo': erro_motivo})
            continue

        custo_total_prod = custo_produto * qtd
        imposto_val = total_venda * aliquota
        comissao_val = total_venda * taxa_mp
        taxa_fixa_val = taxa_fixa * qtd
        ads_rateio = (total_venda / total_vendas_dia) * custo_ads_total if total_vendas_dia > 0 else 0.0
        
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

def calcular_giro_produtos(df_detalhes):
    kits_df = st.session_state.get('kits', pd.DataFrame())
    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    giro_real = []
    
    for _, row in df_detalhes.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd_venda = row['Quantidade']
        
        if prod_norm in kits_map:
            for comp in kits_map[prod_norm]:
                giro_real.append({
                    'SKU Real': comp['sku'],
                    'Qtd Vendida': qtd_venda * comp['qtd'],
                    'Origem': 'Kit'
                })
        else:
            giro_real.append({
                'SKU Real': prod_cod,
                'Qtd Vendida': qtd_venda,
                'Origem': 'Avulso'
            })
            
    if not giro_real: return pd.DataFrame()
    
    df_giro = pd.DataFrame(giro_real)
    df_agrupado = df_giro.groupby('SKU Real')['Qtd Vendida'].sum().reset_index()
    df_agrupado = df_agrupado.sort_values('Qtd Vendida', ascending=False)
    
    return df_agrupado

def calcular_oportunidades(df_detalhes):
    kits_df = st.session_state.get('kits', pd.DataFrame())
    kits_map = {}
    if not kits_df.empty and 'Código Kit' in kits_df.columns:
        for _, row in kits_df.iterrows():
            cod_kit = normalizar(str(row['Código Kit']))
            comps = str(row.get('SKUs Componentes', '')).split(';') if ';' in str(row.get('SKUs Componentes', '')) else [str(row.get('SKUs Componentes', ''))]
            qtds = str(row.get('Qtd Componentes', '')).split(';') if ';' in str(row.get('Qtd Componentes', '')) else [str(row.get('Qtd Componentes', ''))]
            if len(qtds) < len(comps): qtds = [1]*len(comps)
            kits_map[cod_kit] = [{'sku': c.strip(), 'qtd': clean_float(q)} for c, q in zip(comps, qtds)]

    giro_canal = []
    
    for _, row in df_detalhes.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd_venda = row['Quantidade']
        canal = row['Canal']
        
        if prod_norm in kits_map:
            for comp in kits_map[prod_norm]:
                giro_canal.append({
                    'SKU Real': comp['sku'],
                    'Canal': canal,
                    'Qtd Vendida': qtd_venda * comp['qtd']
                })
        else:
            giro_canal.append({
                'SKU Real': prod_cod,
                'Canal': canal,
                'Qtd Vendida': qtd_venda
            })
            
    if not giro_canal: return pd.DataFrame()
    
    df_giro_canal = pd.DataFrame(giro_canal)
    df_pivot = df_giro_canal.pivot_table(index='SKU Real', columns='Canal', values='Qtd Vendida', aggfunc='sum', fill_value=0).reset_index()
    
    cols_canais = [c for c in df_pivot.columns if c != 'SKU Real']
    df_pivot['Total Geral'] = df_pivot[cols_canais].sum(axis=1)
    df_pivot = df_pivot.sort_values('Total Geral', ascending=False)
    
    return df_pivot

def atualizar_dashboards_resumo(df_detalhes, metas_dict):
    if df_detalhes.empty: return None, None, None, None, None, None, None
    
    cols_req = ['Canal', 'Total Venda', 'Lucro Bruto', 'Quantidade', 'Margem (%)', 'CNPJ', 'Produto']
    if not all(c in df_detalhes.columns for c in cols_req): return None, None, None, None, None, None, None

    dash_geral = df_detalhes.groupby('Canal').agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Quantidade': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    dash_geral['Status Meta'] = dash_geral['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
    
    dash_cnpj = df_detalhes.groupby(['CNPJ', 'Canal']).agg({
        'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    
    dash_exec = df_detalhes.groupby('Produto').agg({
        'Quantidade': 'sum', 'Total Venda': 'sum', 'Lucro Bruto': 'sum', 'Margem (%)': 'mean'
    }).reset_index()
    med_v = dash_exec['Total Venda'].median()
    med_m = dash_exec['Margem (%)'].median()
    dash_exec['Classificação BCG'] = dash_exec.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
    dash_exec['Status Meta'] = dash_exec['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
    
    dash_exec['Classificação BCG'] = pd.Categorical(dash_exec['Classificação BCG'], categories=ORDEM_BCG, ordered=True)
    dash_exec = dash_exec.sort_values(['Classificação BCG', 'Total Venda'], ascending=[True, False])
    dash_exec.insert(0, 'Ranking', range(1, len(dash_exec) + 1))
    
    dash_bcg_canal = df_detalhes.groupby(['Canal', 'Produto']).agg({
        'Total Venda': 'sum', 'Margem (%)': 'mean', 'Quantidade': 'sum'
    }).reset_index()
    bcg_final = []
    for canal in dash_bcg_canal['Canal'].unique():
        subset = dash_bcg_canal[dash_bcg_canal['Canal'] == canal].copy()
        med_v_c = subset['Total Venda'].median()
        med_m_c = subset['Margem (%)'].median()
        subset['Classificação'] = subset.apply(lambda x: classificar_bcg(x, med_v_c, med_m_c), axis=1)
        subset['Status Meta'] = subset['Margem (%)'].apply(lambda x: obter_status_meta(x, metas_dict))
        
        subset['Classificação'] = pd.Categorical(subset['Classificação'], categories=ORDEM_BCG, ordered=True)
        subset = subset.sort_values(['Classificação', 'Total Venda'], ascending=[True, False])
        subset.insert(0, 'Ranking', range(1, len(subset) + 1))
        
        bcg_final.append(subset)
    
    df_bcg_final = pd.concat(bcg_final) if bcg_final else pd.DataFrame()
    if not df_bcg_final.empty:
        df_bcg_final = df_bcg_final.sort_values(['Canal', 'Ranking'])

    df_precos = df_detalhes.groupby(['Produto', 'Canal']).agg({
        'Total Venda': 'sum', 'Quantidade': 'sum'
    }).reset_index()
    df_precos['Preço Médio'] = df_precos['Total Venda'] / df_precos['Quantidade']
    df_precos_pivot = df_precos.pivot(index='Produto', columns='Canal', values='Preço Médio').reset_index()

    df_giro = calcular_giro_produtos(df_detalhes)
    df_oportunidades = calcular_oportunidades(df_detalhes)

    return dash_geral, dash_cnpj, dash_exec, df_bcg_final, df_precos_pivot, df_giro, df_oportunidades

def salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades):
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
    if d_giro is not None: salvar_aba("7. Giro de Produtos", d_giro)
    if d_oportunidades is not None: salvar_aba("8. Oportunidades", d_oportunidades)

# ==============================================================================
# INTERFACE
# ==============================================================================
try:
    ss, gc = conectar_google_sheets()
    configs, estoque_produtos = carregar_configuracoes()
    metas_dict = {}
    if configs:
        for key, df in configs.items(): st.session_state[key] = df
        st.session_state['estoque_produtos'] = estoque_produtos
        
        if 'metas' in configs and not configs['metas'].empty:
            for _, row in configs['metas'].iterrows():
                try:
                    metas_dict[row['Indicador']] = float(row['Valor'])
                except: pass
except Exception as e:
    st.error(f"Erro conexão: {e}")
    st.stop()

st.title("📊 Sales BI Pro + 🏭 Fábrica")

with st.sidebar:
    st.header("🔌 Status da Conexão")
    if ss:
        st.success(f"Conectado a: **{ss.title}**")
        
        qtd_prod = len(st.session_state.get('produtos', []))
        qtd_kits = len(st.session_state.get('kits', []))
        
        if qtd_prod > 0: st.info(f"📦 Produtos Carregados: {qtd_prod}")
        else: st.error("❌ Nenhum Produto encontrado! Verifique a aba 'Produtos'.")
        
        if qtd_kits > 0: st.info(f"🧩 Kits Carregados: {qtd_kits}")
        else: st.warning("⚠️ Nenhum Kit encontrado (ou aba 'Kits' vazia).")
    else:
        st.error("❌ Desconectado")

    st.divider()
    st.header("📥 Importar Vendas")
    
    if st.button("🔄 Atualizar Dados (Limpar Cache)"):
        carregar_dados_detalhes.clear()
        carregar_configuracoes.clear()
        carregar_estoque_externo.clear()
        st.success("Cache limpo! Recarregando...")
        time.sleep(1)
        st.rerun()
        
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_regime = st.selectbox("CNPJ/Regime", ['Simples Nacional', 'Lucro Presumido', 'Lucro Real'])
    data_venda = st.date_input("Data", datetime.now()) if formato == 'Bling' else datetime.now()
    custo_ads = st.number_input("💰 Ads (R$)", min_value=0.0, step=10.0)
    uploaded_file = st.file_uploader("Arquivo Excel", type=['xlsx'])
    
    # Variável de sessão para guardar a FILA ACUMULADA de vendas para baixa
    if 'fila_baixa_estoque' not in st.session_state:
        st.session_state['fila_baixa_estoque'] = pd.DataFrame()

    if uploaded_file and st.button("🚀 Processar e Salvar"):
        with st.spinner("Processando..."):
            try:
                df_orig = pd.read_excel(uploaded_file)
                df_processado, df_faltantes = processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads)
                
                if not df_faltantes.empty:
                    st.error("⛔ OPERAÇÃO CANCELADA: Foram encontrados produtos com erros ou não cadastrados!")
                    st.error("Nenhum dado foi salvo na planilha para proteger a integridade do banco de dados.")
                    st.dataframe(df_faltantes)
                    st.download_button("📥 Baixar Relatório de Erros", 
                                       data=to_excel(df_faltantes), 
                                       file_name="erros_impediram_salvamento.xlsx")
                
                elif df_processado is not None and not df_processado.empty:
                    # ACUMULA NA FILA DE BAIXA (NÃO SUBSTITUI)
                    df_novo_lote = df_processado.copy()
                    df_novo_lote['Canal'] = CHANNELS[canal] # Garante que o canal está correto
                    
                    if st.session_state['fila_baixa_estoque'].empty:
                        st.session_state['fila_baixa_estoque'] = df_novo_lote
                    else:
                        st.session_state['fila_baixa_estoque'] = pd.concat([st.session_state['fila_baixa_estoque'], df_novo_lote], ignore_index=True)
                    
                    # Salva no Google Sheets (Financeiro)
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
                    st.success(f"✅ {len(df_processado)} vendas salvas com sucesso! Adicionadas à Fila de Baixa.")
                    
                    carregar_dados_detalhes.clear()
                    df_historico = carregar_dados_detalhes()
                    if not df_historico.empty:
                        d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_historico, metas_dict)
                        salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades)
                        st.success("Dashboards atualizados!")
                        time.sleep(1)
                        st.rerun()
                    else: st.warning("Dados salvos, mas histórico parece vazio.")
            except Exception as e: st.error(f"Erro: {e}")

    st.divider()
    st.header("💾 Manutenção")
    if st.button("💾 Forçar Salvar Dashboards"):
        with st.spinner("Recalculando e salvando abas..."):
            df_historico = carregar_dados_detalhes()
            if not df_historico.empty:
                d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_historico, metas_dict)
                salvar_todos_dashboards(ss, d_geral, d_cnpj, d_exec, d_precos, d_bcg, d_giro, d_oportunidades)
                st.success("Todas as abas foram atualizadas na planilha!")
            else:
                st.warning("Não há dados em '6. Detalhes' para processar.")

st.divider()
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs(["📈 Visão Geral", "🏢 Por CNPJ", "⭐ BCG Geral", "🎯 BCG por Canal", "💲 Preços", "📋 Detalhes", "📦 Giro de Produtos", "🚀 Oportunidades", "🏭 Fábrica & Estoque"])
df_detalhes = carregar_dados_detalhes()

if not df_detalhes.empty and 'Total Venda' in df_detalhes.columns:
    d_geral, d_cnpj, d_exec, d_bcg, d_precos, d_giro, d_oportunidades = atualizar_dashboards_resumo(df_detalhes, metas_dict)

    with tab1:
        total_venda = df_detalhes['Total Venda'].sum()
        margem_media = df_detalhes['Margem (%)'].mean()
        ticket_medio = df_detalhes['Total Venda'].mean()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Vendas Totais", format_currency_br(total_venda))
        
        delta_color_margem = "normal"
        if metas_dict:
            if margem_media >= metas_dict.get('Margem Líquida Ideal (%)', 15)/100: delta_color_margem = "normal"
            elif margem_media < metas_dict.get('Margem Líquida Mínima (%)', 10)/100: delta_color_margem = "inverse"
            else: delta_color_margem = "off"
            
        col2.metric("Margem Média", format_percent_br(margem_media), delta_color=delta_color_margem)
        
        delta_color_ticket = "normal"
        if metas_dict:
            if ticket_medio >= metas_dict.get('Ticket Médio Ideal (R$)', 60): delta_color_ticket = "normal"
            elif ticket_medio < metas_dict.get('Ticket Médio Mínimo (R$)', 45): delta_color_ticket = "inverse"
            else: delta_color_ticket = "off"
            
        col3.metric("Ticket Médio (Linha)", format_currency_br(ticket_medio), delta_color=delta_color_ticket)
        
        st.bar_chart(df_detalhes.groupby('Canal')['Total Venda'].sum())
        st.download_button("📥 Baixar Resumo Geral", data=to_excel(d_geral), file_name="resumo_geral.xlsx")
    with tab2:
        st.dataframe(d_cnpj.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar Análise CNPJ", data=to_excel(d_cnpj), file_name="analise_cnpj.xlsx")
    with tab3:
        st.subheader("Matriz BCG Geral (Ranking)")
        st.dataframe(d_exec.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar BCG Geral", data=to_excel(d_exec), file_name="bcg_geral.xlsx")
    with tab4:
        st.subheader("Matriz BCG por Canal (Ranking)")
        st.dataframe(d_bcg.style.format({'Total Venda': 'R$ {:,.2f}', 'Margem (%)': '{:.2%}'}))
        st.download_button("📥 Baixar BCG por Canal", data=to_excel(d_bcg), file_name="bcg_canal.xlsx")
    with tab5:
        st.subheader("Preços Médios por Marketplace")
        st.dataframe(d_precos.style.format(lambda x: f"R$ {x:,.2f}" if isinstance(x, (int, float)) and pd.notna(x) else ("-" if pd.isna(x) else x)))
        st.download_button("📥 Baixar Preços", data=to_excel(d_precos), file_name="precos_marketplaces.xlsx")
    with tab6:
        st.dataframe(df_detalhes)
        st.download_button("📥 Baixar Detalhes Completos", data=to_excel(df_detalhes), file_name="detalhes_vendas.xlsx")
    with tab7:
        st.subheader("📦 Giro de Produtos (Explosão de Kits + Avulsos)")
        filtro_texto = st.text_input("🔍 Filtrar por Atributo (ex: ML, P, Branco)", "")
        df_giro_view = d_giro.copy()
        if filtro_texto:
            df_giro_view = df_giro_view[df_giro_view['SKU Real'].str.contains(filtro_texto, case=False, na=False)]
            st.info(f"Mostrando {len(df_giro_view)} produtos contendo '{filtro_texto}'")
        st.dataframe(df_giro_view)
        st.download_button("📥 Baixar Giro de Produtos", data=to_excel(df_giro_view), file_name="giro_produtos.xlsx")
    with tab8:
        st.subheader("🚀 Oportunidades de Expansão (Cross-Assortment)")
        st.info("Esta tabela mostra quantas unidades de cada produto (real) foram vendidas em cada canal. Use para identificar onde você NÃO está vendendo.")
        filtro_oportunidade = st.text_input("🔍 Filtrar Oportunidades (ex: Body)", "")
        df_op_view = d_oportunidades.copy()
        if filtro_oportunidade:
            df_op_view = df_op_view[df_op_view['SKU Real'].str.contains(filtro_oportunidade, case=False, na=False)]
        st.dataframe(df_op_view)
        st.download_button("📥 Baixar Oportunidades", data=to_excel(df_op_view), file_name="oportunidades_expansao.xlsx")
    
    with tab9:
        st.subheader("🏭 Fábrica & Controle de Estoque")
        st.markdown("""
        <div style='background-color: #f0f2f6; padding: 15px; border-radius: 5px; border-left: 5px solid #ff4b4b;'>
            <b>MÓDULO DE INTEGRAÇÃO EXTERNA</b><br>
            Esta aba conecta com sua planilha de estoque separada. As ações aqui <b>não afetam</b> os dados financeiros do BI.
        </div>
        """, unsafe_allow_html=True)
        
        col_ctrl1, col_ctrl2 = st.columns(2)
        with col_ctrl1:
            if st.button("🔄 Carregar Estoque Externo"):
                carregar_estoque_externo.clear()
                st.success("Estoque recarregado!")
        with col_ctrl2:
            if st.button("🗑️ Limpar Fila de Baixa (Começar do Zero)"):
                st.session_state['fila_baixa_estoque'] = pd.DataFrame()
                st.success("Fila de baixa limpa! Pode começar a subir novos arquivos.")
                time.sleep(1)
                st.rerun()
            
        df_estoque_ext = carregar_estoque_externo()
        
        if df_estoque_ext.empty:
            st.error("Não foi possível carregar o estoque externo. Verifique a conexão.")
        else:
            st.success(f"Conectado ao Estoque Externo: {len(df_estoque_ext)} produtos carregados.")
            
            # Verifica se tem vendas acumuladas na fila
            df_vendas_fila = st.session_state.get('fila_baixa_estoque', pd.DataFrame())
            
            if df_vendas_fila.empty:
                st.info("ℹ️ A fila de baixa está vazia. Faça upload das vendas na barra lateral para adicionar itens aqui.")
            else:
                st.subheader(f"Análise de Baixa (Fila Acumulada: {len(df_vendas_fila)} registros)")
                df_baixa = expandir_kits_estoque_acumulado(df_vendas_fila, df_estoque_ext)
                
                if df_baixa.empty:
                    st.warning("Nenhum produto das vendas foi encontrado no estoque externo.")
                else:
                    # Formatação para exibição
                    df_view = df_baixa[['codigo_canonical', 'nome', 'estoque_atual', 'quantidade', 'estoque_final', 'origem']].copy()
                    df_view.columns = ['Código', 'Produto', 'Estoque Atual', 'Qtd a Baixar', 'Estoque Final', 'Origem da Demanda']
                    
                    # Alerta de estoque negativo
                    negativos = df_view[df_view['Estoque Final'] < 0]
                    if not negativos.empty:
                        st.error(f"🚨 ATENÇÃO: {len(negativos)} produtos ficarão com estoque NEGATIVO!")
                        st.dataframe(negativos)
                    
                    st.dataframe(df_view)
                    
                    col_btn1, col_btn2 = st.columns(2)
                    with col_btn1:
                        if st.button("✅ CONFIRMAR BAIXA NO ESTOQUE", type="primary"):
                            progress_bar = st.progress(0)
                            status_text = st.empty()
                            sucessos = 0
                            erros = 0
                            
                            total_items = len(df_baixa)
                            for idx, row in df_baixa.iterrows():
                                status_text.text(f"Baixando {row['codigo_canonical']}...")
                                res = movimentar_estoque_webhook(
                                    row['codigo_canonical'], 
                                    row['quantidade'], 
                                    'saida', 
                                    'SalesBI_Auto'
                                )
                                if res.get('success'): sucessos += 1
                                else: erros += 1
                                progress_bar.progress((idx + 1) / total_items)
                                
                            status_text.empty()
                            progress_bar.empty()
                            
                            if erros == 0:
                                st.success(f"Sucesso! {sucessos} itens baixados no estoque externo.")
                                carregar_estoque_externo.clear() # Limpa cache para recarregar saldo novo
                                st.session_state['fila_baixa_estoque'] = pd.DataFrame() # Limpa fila após sucesso
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.warning(f"Processo finalizado com {sucessos} sucessos e {erros} erros.")
                    
                    with col_btn2:
                        if st.button("📄 Gerar Ordem de Produção (PDF/Print)"):
                            st.info("Funcionalidade de PDF em desenvolvimento. Use o print da tabela acima por enquanto.")

else:
    st.info("Aguardando dados...")
