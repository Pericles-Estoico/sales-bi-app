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

# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================
def clean_currency(value):
    """
    Limpa e converte valores monetários de forma robusta.
    Aceita: 3,75 | 3.75 | R$ 3,75 | R$ 3.75 | 375 (se for inteiro, divide por 100 se parecer erro)
    """
    if pd.isna(value) or value == '':
        return 0.0
    
    s_val = str(value).strip()
    
    # Remove R$ e espaços
    s_val = s_val.replace('R$', '').replace(' ', '')
    
    # Se já for um número float/int puro
    try:
        f_val = float(s_val)
        # Lógica heurística: se o valor for muito alto (ex: 375.00) onde deveria ser 3.75
        # Mas cuidado: produtos caros existem. 
        # Melhor abordagem: assumir que o input do Excel está correto se for numérico.
        # O problema geralmente vem de strings com vírgula sendo lidas erradas.
        return f_val
    except:
        pass

    # Tratamento de strings com pontuação
    # Caso brasileiro: 1.234,56 -> remove ponto, troca vírgula por ponto
    if ',' in s_val and '.' in s_val:
        s_val = s_val.replace('.', '').replace(',', '.')
    elif ',' in s_val:
        s_val = s_val.replace(',', '.')
    
    try:
        return float(s_val)
    except:
        return 0.0

def format_currency_br(value):
    """Formata float para string R$ X.XXX,XX"""
    try:
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "R$ 0,00"

def format_percent_br(value):
    """Formata float para string X,XX%"""
    try:
        return f"{value * 100:.2f}%".replace(".", ",")
    except:
        return "0,00%"

def normalizar(texto):
    if pd.isna(texto): return ''
    texto = str(texto)
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return texto.lower().strip()

# ==============================================================================
# CONEXÃO COM GOOGLE SHEETS (MÉTODO ORIGINAL RESTAURADO)
# ==============================================================================
@st.cache_resource
def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    
    # Tenta carregar credenciais do st.secrets
    if "GOOGLE_SHEETS_CREDENTIALS" in st.secrets:
        creds_dict = json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    else:
        st.error("❌ Credenciais não encontradas no st.secrets (GOOGLE_SHEETS_CREDENTIALS).")
        st.stop()
        
    gc = gspread.authorize(creds)
    
    if "GOOGLE_SHEETS_URL" in st.secrets:
        ss = gc.open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
        return ss, gc
    else:
        st.error("❌ URL da planilha não encontrada no st.secrets (GOOGLE_SHEETS_URL).")
        st.stop()

@st.cache_data(ttl=60)
def carregar_dados_detalhes():
    """Carrega os dados da aba '6. Detalhes' para gerar os relatórios."""
    try:
        ss, _ = conectar_google_sheets()
        ws = ss.worksheet("6. Detalhes")
        data = ws.get_all_values()
        if len(data) > 1:
            df = pd.DataFrame(data[1:], columns=data[0])
            # Converter colunas numéricas
            cols_num = ['Quantidade', 'Total Venda', 'Custo Total', 'Lucro Bruto', 'Margem (%)', 'Investimento Ads']
            for col in cols_num:
                if col in df.columns:
                    df[col] = df[col].apply(clean_currency)
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao ler aba Detalhes: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def carregar_configuracoes():
    try:
        ss, gc = conectar_google_sheets()
        configs_data = {}
        
        # Carregar Estoque (Opcional)
        estoque_produtos = set()
        if "TEMPLATE_ESTOQUE_URL" in st.secrets:
            try:
                ss_estoque = gc.open_by_url(st.secrets["TEMPLATE_ESTOQUE_URL"])
                ws_estoque = ss_estoque.worksheet('template_estoque')
                df_estoque = pd.DataFrame(ws_estoque.get_all_records())
                if 'codigo' in df_estoque.columns:
                    estoque_produtos = set(df_estoque['codigo'].tolist())
            except: pass
        
        # Carregar Abas de Configuração
        abas_config = [
            ("Produtos", "produtos"), 
            ("Kits", "kits"), 
            ("Canais", "canais"), 
            ("Custos por Pedido", "custos_ped"), 
            ("Impostos", "impostos"), 
            ("Frete", "frete"), 
            ("Metas", "metas")
        ]
        
        for nome_aba, chave in abas_config:
            try:
                sh = ss.worksheet(nome_aba)
                data = sh.get_all_values()
                if len(data) > 1:
                    # Tratar colunas duplicadas
                    cols = data[0]
                    counts = {}
                    new_cols = []
                    for col in cols:
                        if col in counts:
                            counts[col] += 1
                            new_cols.append(f"{col}_{counts[col]}")
                        else:
                            counts[col] = 0
                            new_cols.append(col)
                    
                    df = pd.DataFrame(data[1:], columns=new_cols)
                    
                    # Limpeza de valores numéricos nas configurações
                    for col in df.columns:
                        if any(x in col for x in ['R$', '%', 'Peso', 'Custo', 'Preço', 'Taxa', 'Frete', 'Valor']):
                            df[col] = df[col].apply(clean_currency)
                    
                    configs_data[chave] = df
            except Exception as e:
                st.warning(f"Aba '{nome_aba}' não encontrada ou vazia: {e}")
                
        return configs_data, estoque_produtos
    except Exception as e:
        return None, None

# ==============================================================================
# LÓGICA DE NEGÓCIO
# ==============================================================================

def classificar_bcg(row, median_vendas, median_margem):
    """Classifica produto na Matriz BCG"""
    vendas = row['Total Venda']
    margem = row['Margem (%)']
    
    if vendas >= median_vendas and margem >= median_margem:
        return 'Estrela ⭐'
    elif vendas >= median_vendas and margem < median_margem:
        return 'Vaca Leiteira 🐄'
    elif vendas < median_vendas and margem >= median_margem:
        return 'Interrogação ❓'
    else:
        return 'Abacaxi 🍍'

def processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads_total):
    # 1. Padronização Inicial
    df_novo = pd.DataFrame()
    
    # Verifica formato (Bling vs Padrão)
    if 'Código' in df_orig.columns and 'Quantidade' in df_orig.columns:
        # Formato Bling/Padrão esperado
        df_novo['Data'] = [data_venda] * len(df_orig)
        df_novo['Produto'] = df_orig['Código']
        df_novo['Quantidade'] = pd.to_numeric(df_orig['Quantidade'], errors='coerce').fillna(0)
        
        # Limpeza crítica de valores monetários
        if 'Valor' in df_orig.columns:
            df_novo['Total'] = df_orig['Valor'].apply(clean_currency)
        elif 'Preço' in df_orig.columns: # Caso tenha preço unitário
             df_novo['Total'] = df_orig['Preço'].apply(clean_currency) * df_novo['Quantidade']
        else:
             df_novo['Total'] = 0.0
             
        df_novo['Preço Unitário'] = df_novo['Total'] / df_novo['Quantidade']
    else:
        st.error("Formato de arquivo desconhecido. Colunas obrigatórias: 'Código', 'Quantidade', 'Valor' (ou 'Preço').")
        return None

    df_novo['Canal'] = CHANNELS[canal]
    df_novo['CNPJ'] = cnpj_regime

    # 2. Carregar Configurações
    produtos_df = st.session_state.get('produtos', pd.DataFrame())
    kits_df = st.session_state.get('kits', pd.DataFrame())
    impostos_df = st.session_state.get('impostos', pd.DataFrame())
    canais_df = st.session_state.get('canais', pd.DataFrame())
    custos_ped_df = st.session_state.get('custos_ped', pd.DataFrame())

    # 3. Mapeamento de Produtos e Kits
    produtos_map = {}
    if not produtos_df.empty:
        for _, row in produtos_df.iterrows():
            cod = str(row['Código']).strip()
            produtos_map[normalizar(cod)] = {
                'custo': float(row.get('Custo (R$)', 0)),
                'nome': row.get('Nome', cod)
            }

    kits_map = {}
    if not kits_df.empty:
        for _, row in kits_df.iterrows():
            cod_kit = str(row['Código Kit']).strip()
            comps_str = str(row.get('SKUs Componentes', ''))
            qtds_str = str(row.get('Qtd Componentes', ''))
            
            componentes = []
            if ';' in comps_str:
                skus = comps_str.split(';')
                qtds = qtds_str.split(';') if ';' in qtds_str else [1]*len(skus)
                for s, q in zip(skus, qtds):
                    componentes.append({'sku': s.strip(), 'qtd': float(q) if q else 1})
            else:
                componentes.append({'sku': comps_str.strip(), 'qtd': float(qtds_str) if qtds_str else 1})
            
            kits_map[normalizar(cod_kit)] = componentes

    # 4. Parâmetros Financeiros
    aliquota = 0.06 # Default Simples
    if not impostos_df.empty and 'Tipo' in impostos_df.columns:
        match = impostos_df[impostos_df['Tipo'].str.contains(cnpj_regime.split()[0], case=False, na=False)]
        if not match.empty:
            aliquota = float(match.iloc[0]['Alíquota (%)']) / 100

    taxa_mp = 0.16
    taxa_fixa = 5.0
    if not canais_df.empty:
        match = canais_df[canais_df['Canal'].str.contains(canal.replace('_', ' '), case=False, na=False)]
        if not match.empty:
            taxa_mp = float(match.iloc[0].get('Taxa Marketplace (%)', 16)) / 100
            taxa_fixa = float(match.iloc[0].get('Taxa Fixa Pedido (R$)', 5))

    custo_emb = 0.0
    if not custos_ped_df.empty:
        custo_emb = custos_ped_df['Custo Unitário (R$)'].sum()

    # 5. Processamento Linha a Linha
    resultados = []
    total_vendas_dia = df_novo['Total'].sum()

    for _, row in df_novo.iterrows():
        prod_cod = str(row['Produto']).strip()
        prod_norm = normalizar(prod_cod)
        qtd = row['Quantidade']
        total_venda = row['Total']
        
        custo_produto = 0.0
        tipo = 'Produto'
        
        # Verifica se é Kit
        if prod_norm in kits_map:
            tipo = 'Kit'
            for comp in kits_map[prod_norm]:
                comp_sku = comp['sku']
                comp_qtd = comp['qtd']
                comp_norm = normalizar(comp_sku)
                if comp_norm in produtos_map:
                    custo_produto += produtos_map[comp_norm]['custo'] * comp_qtd
        # Verifica se é Produto Simples
        elif prod_norm in produtos_map:
            custo_produto = produtos_map[prod_norm]['custo']
        
        custo_total_prod = custo_produto * qtd
        imposto_val = total_venda * aliquota
        comissao_val = total_venda * taxa_mp
        taxa_fixa_val = taxa_fixa * qtd # Taxa fixa é por item vendido ou por pedido? Assumindo por item vendido na falta de ID pedido
        
        # Rateio de Ads (Proporcional ao valor da venda)
        ads_rateio = 0.0
        if total_vendas_dia > 0:
            ads_rateio = (total_venda / total_vendas_dia) * custo_ads_total
            
        custo_total_geral = custo_total_prod + imposto_val + comissao_val + taxa_fixa_val + (custo_emb * qtd) + ads_rateio
        lucro = total_venda - custo_total_geral
        margem = (lucro / total_venda) if total_venda > 0 else 0.0
        
        resultados.append({
            'Data': row['Data'],
            'Canal': row['Canal'],
            'CNPJ': row['CNPJ'],
            'Produto': prod_cod,
            'Tipo': tipo,
            'Quantidade': qtd,
            'Total Venda': total_venda,
            'Custo Produto': custo_total_prod,
            'Impostos': imposto_val,
            'Comissão': comissao_val,
            'Taxas Fixas': taxa_fixa_val,
            'Embalagem': custo_emb * qtd,
            'Investimento Ads': ads_rateio,
            'Custo Total': custo_total_geral,
            'Lucro Bruto': lucro,
            'Margem (%)': margem
        })
        
    return pd.DataFrame(resultados)

def atualizar_dashboards_resumo(df_detalhes):
    """Regera todas as abas de análise a partir do histórico completo"""
    if df_detalhes.empty:
        return None, None, None, None

    # 1. Dashboard Geral
    dash_geral = df_detalhes.groupby('Canal').agg({
        'Total Venda': 'sum',
        'Lucro Bruto': 'sum',
        'Quantidade': 'sum',
        'Margem (%)': 'mean'
    }).reset_index()
    
    # 2. Análise por CNPJ
    dash_cnpj = df_detalhes.groupby(['CNPJ', 'Canal']).agg({
        'Total Venda': 'sum',
        'Lucro Bruto': 'sum',
        'Margem (%)': 'mean'
    }).reset_index()
    
    # 3. Análise Executiva (Por Produto)
    dash_exec = df_detalhes.groupby('Produto').agg({
        'Quantidade': 'sum',
        'Total Venda': 'sum',
        'Lucro Bruto': 'sum',
        'Margem (%)': 'mean'
    }).reset_index()
    
    # 4. Matriz BCG
    median_vendas = dash_exec['Total Venda'].median()
    median_margem = dash_exec['Margem (%)'].median()
    
    dash_exec['Classificação BCG'] = dash_exec.apply(
        lambda x: classificar_bcg(x, median_vendas, median_margem), axis=1
    )
    
    # Matriz BCG por Canal (Aba 5)
    dash_bcg_canal = df_detalhes.groupby(['Canal', 'Produto']).agg({
        'Total Venda': 'sum',
        'Margem (%)': 'mean'
    }).reset_index()
    
    # Calcular medianas por canal
    bcg_final = []
    for canal in dash_bcg_canal['Canal'].unique():
        subset = dash_bcg_canal[dash_bcg_canal['Canal'] == canal].copy()
        med_v = subset['Total Venda'].median()
        med_m = subset['Margem (%)'].median()
        subset['Classificação'] = subset.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
        bcg_final.append(subset)
        
    df_bcg_final = pd.concat(bcg_final) if bcg_final else pd.DataFrame()

    return dash_geral, dash_cnpj, dash_exec, df_bcg_final

# ==============================================================================
# INTERFACE PRINCIPAL
# ==============================================================================

# Inicialização
try:
    ss, gc = conectar_google_sheets()
    configs, estoque_produtos = carregar_configuracoes()
    
    if configs:
        for key, df in configs.items():
            st.session_state[key] = df
        st.session_state['estoque_produtos'] = estoque_produtos
    else:
        st.error("❌ Erro ao carregar configurações. Verifique a conexão.")
        
except Exception as e:
    st.error(f"❌ Erro crítico de conexão: {str(e)}")
    st.stop()

st.title("📊 Sales BI Pro - Dashboard Executivo V10")

# Sidebar
with st.sidebar:
    st.header("📥 Importar Vendas")
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    cnpj_regime = st.selectbox("CNPJ/Regime", ['Simples Nacional', 'Lucro Presumido', 'Lucro Real'])
    
    data_padrao = datetime.now()
    if formato == 'Bling':
        data_venda = st.date_input("Data da Venda", data_padrao)
    else:
        data_venda = data_padrao
        
    custo_ads = st.number_input("💰 Ads do Dia (R$)", min_value=0.0, value=0.0, step=10.0)
    
    uploaded_file = st.file_uploader("Arquivo Excel (.xlsx)", type=['xlsx'])
    
    if uploaded_file and st.button("🚀 Processar e Salvar"):
        with st.spinner("Processando..."):
            try:
                df_orig = pd.read_excel(uploaded_file)
                
                # Processamento
                df_processado = processar_arquivo(df_orig, data_venda, canal, cnpj_regime, custo_ads)
                
                if df_processado is not None and not df_processado.empty:
                    # Salvar Detalhes (Append)
                    ws_detalhes = ss.worksheet("6. Detalhes")
                    
                    # Formatar para salvar (converter floats para strings com vírgula)
                    df_salvar = df_processado.copy()
                    cols_float = ['Total Venda', 'Custo Produto', 'Impostos', 'Comissão', 'Taxas Fixas', 
                                  'Embalagem', 'Investimento Ads', 'Custo Total', 'Lucro Bruto', 'Margem (%)']
                    
                    # Adicionar ao Google Sheets
                    lista_dados = df_salvar.astype(str).values.tolist()
                    ws_detalhes.append_rows(lista_dados)
                    
                    st.success(f"✅ {len(df_processado)} vendas processadas e salvas em '6. Detalhes'!")
                    
                    # Recarregar tudo para atualizar dashboards
                    st.info("🔄 Atualizando dashboards de análise...")
                    
                    # Ler histórico completo
                    df_historico = pd.DataFrame(ws_detalhes.get_all_records())
                    
                    # Converter colunas numéricas do histórico
                    for col in cols_float:
                        if col in df_historico.columns:
                            df_historico[col] = df_historico[col].apply(clean_currency)
                    
                    # Gerar Resumos
                    d_geral, d_cnpj, d_exec, d_bcg = atualizar_dashboards_resumo(df_historico)
                    
                    # Função auxiliar para salvar sobrescrevendo
                    def salvar_aba(nome_aba, df):
                        try:
                            ws = ss.worksheet(nome_aba)
                            ws.clear()
                            # Formatar visualmente
                            df_fmt = df.copy()
                            for c in df_fmt.columns:
                                if 'Margem' in c:
                                    df_fmt[c] = df_fmt[c].apply(format_percent_br)
                                elif any(x in c for x in ['Venda', 'Lucro', 'Custo', 'Ticket']):
                                    df_fmt[c] = df_fmt[c].apply(format_currency_br)
                            
                            ws.update([df_fmt.columns.values.tolist()] + df_fmt.astype(str).values.tolist())
                        except Exception as e:
                            st.error(f"Erro ao salvar {nome_aba}: {e}")

                    # Salvar Abas de Análise
                    if d_geral is not None: salvar_aba("1. Dashboard Geral", d_geral)
                    if d_cnpj is not None: salvar_aba("2. Análise por CNPJ", d_cnpj)
                    if d_exec is not None: salvar_aba("3. Análise Executiva", d_exec)
                    if d_bcg is not None: salvar_aba("5. Matriz BCG", d_bcg)
                    
                    st.success("🎉 Todos os dashboards foram atualizados com sucesso!")
                    time.sleep(2)
                    st.rerun()
                    
            except Exception as e:
                st.error(f"Erro no processamento: {str(e)}")
                st.exception(e)

# Visualização dos Dados
st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📈 Visão Geral", "🏢 Por CNPJ", "⭐ Matriz BCG", "📋 Detalhes"])

# Carregar dados para visualização
df_detalhes = carregar_dados_detalhes()

if not df_detalhes.empty:
    with tab1:
        st.subheader("Performance Geral")
        col1, col2, col3 = st.columns(3)
        total_vendas = df_detalhes['Total Venda'].sum()
        lucro_total = df_detalhes['Lucro Bruto'].sum()
        margem_media = df_detalhes['Margem (%)'].mean()
        
        col1.metric("Vendas Totais", format_currency_br(total_vendas))
        col2.metric("Lucro Bruto", format_currency_br(lucro_total))
        col3.metric("Margem Média", format_percent_br(margem_media))
        
        st.bar_chart(df_detalhes.groupby('Canal')['Total Venda'].sum())

    with tab2:
        st.subheader("Análise por CNPJ")
        df_cnpj = df_detalhes.groupby(['CNPJ', 'Canal'])['Total Venda'].sum().unstack()
        st.dataframe(df_cnpj.style.format("R$ {:,.2f}"))

    with tab3:
        st.subheader("Matriz BCG (Growth-Share Matrix)")
        
        # Recalcular BCG para exibição
        dash_exec = df_detalhes.groupby('Produto').agg({
            'Total Venda': 'sum',
            'Margem (%)': 'mean',
            'Quantidade': 'sum'
        }).reset_index()
        
        med_v = dash_exec['Total Venda'].median()
        med_m = dash_exec['Margem (%)'].median()
        
        dash_exec['Classificação'] = dash_exec.apply(lambda x: classificar_bcg(x, med_v, med_m), axis=1)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⭐ Estrelas", len(dash_exec[dash_exec['Classificação'].str.contains('Estrela')]))
        c2.metric("🐄 Vacas Leiteiras", len(dash_exec[dash_exec['Classificação'].str.contains('Vaca')]))
        c3.metric("❓ Interrogações", len(dash_exec[dash_exec['Classificação'].str.contains('Interrogação')]))
        c4.metric("🍍 Abacaxis", len(dash_exec[dash_exec['Classificação'].str.contains('Abacaxi')]))
        
        st.dataframe(dash_exec.style.format({
            'Total Venda': 'R$ {:,.2f}',
            'Margem (%)': '{:.2%}'
        }))

    with tab4:
        st.subheader("Base de Dados Completa")
        st.dataframe(df_detalhes)
else:
    st.info("Nenhum dado processado ainda. Faça o upload de um arquivo para começar.")
