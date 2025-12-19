import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import time

# Configuração da Página
st.set_page_config(page_title="Sales BI Pro", page_icon="📊", layout="wide")

# Estilo CSS Personalizado
st.markdown("""
    <style>
    .main {
        background-color: #f5f5f5;
    }
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #45a049;
    }
    .metric-card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box_shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Título Principal
st.title("📊 Sales BI Pro - Dashboard Executivo")

# --- CONFIGURAÇÃO DO GOOGLE SHEETS ---
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def connect_google_sheets():
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPE
        )
        client = gspread.authorize(creds)
        # Tenta abrir a planilha
        sheet = client.open_by_key(st.secrets["google_sheets"]["spreadsheet_id"])
        return sheet
    except Exception as e:
        st.error(f"Erro ao conectar no Google Sheets: {e}")
        return None

# --- FUNÇÕES AUXILIARES ---

def clean_currency(value):
    """
    Converte valores monetários/numéricos de forma robusta.
    Aceita: float, int, string ('R$ 1.200,50', '1.200,50', '1200.50')
    Retorna: float
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if pd.isna(value) or value == "":
        return 0.0
        
    str_val = str(value).strip()
    
    # Remove símbolos de moeda e espaços
    str_val = str_val.replace("R$", "").replace("US$", "").strip()
    
    # Tenta detectar formato brasileiro (ponto como milhar, vírgula como decimal)
    if "," in str_val and "." in str_val:
        # Ex: 1.234,56 -> Remove ponto, troca vírgula por ponto
        if str_val.find(".") < str_val.find(","):
             str_val = str_val.replace(".", "").replace(",", ".")
        # Ex: 1,234.56 (formato americano misturado) -> Remove vírgula
        else:
             str_val = str_val.replace(",", "")
    elif "," in str_val:
        # Ex: 1234,56 -> Troca vírgula por ponto
        str_val = str_val.replace(",", ".")
    
    try:
        return float(str_val)
    except ValueError:
        return 0.0

def clean_percentage(value):
    if isinstance(value, (int, float)):
        return float(value)
    if pd.isna(value) or value == "":
        return 0.0
    str_val = str(value).replace("%", "").replace(",", ".").strip()
    try:
        return float(str_val) / 100
    except:
        return 0.0

def load_config_data(sheet, tab_name, expected_cols):
    try:
        worksheet = sheet.worksheet(tab_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Tratamento de colunas duplicadas ou vazias
        df.columns = [c.strip() for c in df.columns]
        
        # Se faltar coluna esperada, cria vazia
        for col in expected_cols:
            if col not in df.columns:
                # Tenta achar coluna parecida (case insensitive)
                found = False
                for existing_col in df.columns:
                    if existing_col.lower() == col.lower():
                        df.rename(columns={existing_col: col}, inplace=True)
                        found = True
                        break
                if not found:
                    df[col] = None
                    
        return df
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Aba '{tab_name}' não encontrada na planilha.")
        return pd.DataFrame(columns=expected_cols)
    except Exception as e:
        st.error(f"Erro ao ler aba '{tab_name}': {e}")
        return pd.DataFrame(columns=expected_cols)

def get_kit_cost(kit_sku, kits_df, products_df):
    """Calcula o custo de um kit somando os componentes"""
    try:
        kit_row = kits_df[kits_df['Código Kit'].astype(str) == str(kit_sku)]
        if kit_row.empty:
            return 0.0
        
        components_str = str(kit_row.iloc[0]['SKUs Componentes'])
        quantities_str = str(kit_row.iloc[0]['Qtd Componentes'])
        
        # Separa por ponto e vírgula
        components = [c.strip() for c in components_str.split(';') if c.strip()]
        
        # Tenta separar quantidades, se falhar assume 1 para tudo
        try:
            quantities = [float(q.strip().replace(',', '.')) for q in quantities_str.split(';') if q.strip()]
        except:
            quantities = [1.0] * len(components)
            
        # Garante que listas tenham mesmo tamanho
        if len(quantities) < len(components):
            quantities.extend([1.0] * (len(components) - len(quantities)))
            
        total_cost = 0.0
        for sku, qty in zip(components, quantities):
            prod_row = products_df[products_df['Código'].astype(str) == str(sku)]
            if not prod_row.empty:
                cost = clean_currency(prod_row.iloc[0]['Custo (R$)'])
                total_cost += cost * qty
                
        return total_cost
    except Exception as e:
        # st.warning(f"Erro ao calcular kit {kit_sku}: {e}")
        return 0.0

def safe_write_to_sheet(sheet, tab_name, df, mode='overwrite'):
    """
    Escreve dados no Google Sheets de forma segura.
    mode='overwrite': Limpa e escreve tudo.
    mode='append': Adiciona ao final.
    """
    try:
        try:
            ws = sheet.worksheet(tab_name)
        except:
            ws = sheet.add_worksheet(title=tab_name, rows=1000, cols=20)
            
        # Prepara dados para escrita
        # Converte NaN para "" e datas para string
        df_clean = df.fillna("").astype(str)
        data_to_write = df_clean.values.tolist()
        headers = df_clean.columns.tolist()
        
        if mode == 'overwrite':
            ws.clear()
            ws.update([headers] + data_to_write)
        elif mode == 'append':
            # Verifica se está vazio para por cabeçalho
            existing_data = ws.get_all_values()
            if not existing_data:
                ws.update([headers] + data_to_write)
            else:
                # Se já tem dados, verifica se cabeçalho bate (opcional, aqui confiamos na ordem)
                ws.append_rows(data_to_write)
                
        return True
    except Exception as e:
        st.error(f"Erro ao salvar na aba '{tab_name}': {e}")
        return False

def format_currency_br(val):
    try:
        return f"R$ {float(val):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return val

def format_percent_br(val):
    try:
        return f"{float(val)*100:.2f}%".replace(".", ",")
    except:
        return val

# --- LÓGICA PRINCIPAL ---

sheet = connect_google_sheets()

if sheet:
    # Botão para limpar cache e recarregar configs
    if st.sidebar.button("🔄 Recarregar Configurações (Limpar Cache)"):
        st.cache_resource.clear()
        st.rerun()

    # Carregar Tabelas de Configuração
    with st.spinner("Carregando configurações..."):
        df_produtos = load_config_data(sheet, "Produtos", ["Código", "Custo (R$)", "Preço Venda (R$)", "Peso (g)"])
        df_kits = load_config_data(sheet, "Kits", ["Código Kit", "SKUs Componentes", "Qtd Componentes"])
        df_canais = load_config_data(sheet, "Canais", ["Canal", "Taxa Marketplace (%)", "Taxa Fixa Pedido (R$)"])
        df_impostos = load_config_data(sheet, "Impostos", ["Tipo", "Alíquota (%)"])
        df_custos_pedido = load_config_data(sheet, "Custos por Pedido", ["Item", "Custo Unitário (R$)"])
        df_metas = load_config_data(sheet, "Metas", ["Valor"])

    # Sidebar - Upload e Configs
    st.sidebar.header("1. Upload de Arquivo")
    uploaded_file = st.sidebar.file_uploader("Solte seu arquivo aqui (Excel/CSV)", type=["xlsx", "xls", "csv"])
    
    st.sidebar.header("2. Configurações do Pedido")
    data_selecionada = st.sidebar.date_input("Data das Vendas", datetime.today())
    canal_selecionado = st.sidebar.selectbox("Canal de Venda", df_canais["Canal"].unique())
    regime_tributario = st.sidebar.selectbox("Regime Tributário", df_impostos["Tipo"].unique())

    # Processamento
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df_vendas = pd.read_csv(uploaded_file)
            else:
                df_vendas = pd.read_excel(uploaded_file)
                
            # Padronização de Colunas (Tenta adivinhar nomes comuns)
            col_map = {
                'SKU': 'SKU', 'Código': 'SKU', 'Ref': 'SKU', 'Referência': 'SKU',
                'Qtd': 'Qtd', 'Quantidade': 'Qtd', 'Quant.': 'Qtd',
                'Valor': 'Valor Total', 'Preço': 'Valor Total', 'Total': 'Valor Total', 'Venda': 'Valor Total'
            }
            df_vendas.rename(columns=lambda x: col_map.get(x, x), inplace=True)
            
            # Verifica colunas essenciais
            if 'SKU' not in df_vendas.columns or 'Qtd' not in df_vendas.columns or 'Valor Total' not in df_vendas.columns:
                st.error("O arquivo precisa ter colunas de SKU, Quantidade e Valor Total (ou nomes similares).")
            else:
                # --- CÁLCULOS ---
                resultados = []
                
                # Taxas e Impostos
                row_canal = df_canais[df_canais['Canal'] == canal_selecionado].iloc[0]
                taxa_mp_pct = clean_percentage(row_canal['Taxa Marketplace (%)'])
                taxa_fixa = clean_currency(row_canal['Taxa Fixa Pedido (R$)'])
                
                row_imposto = df_impostos[df_impostos['Tipo'] == regime_tributario].iloc[0]
                aliquota_imposto = clean_percentage(row_imposto['Alíquota (%)'])
                
                custo_pedido_fixo = df_custos_pedido['Custo Unitário (R$)'].apply(clean_currency).sum()

                for _, row in df_vendas.iterrows():
                    sku = str(row['SKU']).strip()
                    qtd = float(row['Qtd'])
                    valor_venda = clean_currency(row['Valor Total'])
                    
                    # Identifica Produto ou Kit
                    tipo = "Produto"
                    custo_produto = 0.0
                    
                    # Busca em Produtos
                    prod_match = df_produtos[df_produtos['Código'].astype(str) == sku]
                    if not prod_match.empty:
                        custo_produto = clean_currency(prod_match.iloc[0]['Custo (R$)'])
                    else:
                        # Busca em Kits
                        kit_match = df_kits[df_kits['Código Kit'].astype(str) == sku]
                        if not kit_match.empty:
                            tipo = "Kit"
                            custo_produto = get_kit_cost(sku, df_kits, df_produtos)
                        else:
                            tipo = "Não Encontrado"
                            
                    # Cálculos Financeiros
                    custo_total_prod = custo_produto * qtd
                    imposto_valor = valor_venda * aliquota_imposto
                    taxa_mp_valor = (valor_venda * taxa_mp_pct) + (taxa_fixa * qtd) # Taxa fixa é por item ou pedido? Assumindo por item vendido na linha se for marketplace, ou ajustar conforme regra. Simplificando: taxa fixa * qtd.
                    
                    # Rateio de Custo Fixo do Pedido (Embalagem, etc) - Simplificação: Custo fixo por linha de venda
                    custo_emb = custo_pedido_fixo * qtd 
                    
                    custo_total = custo_total_prod + custo_emb + imposto_valor + taxa_mp_valor
                    lucro = valor_venda - custo_total
                    margem = (lucro / valor_venda) if valor_venda > 0 else 0
                    
                    resultados.append({
                        "Data": data_selecionada.strftime("%Y-%m-%d"),
                        "Canal": canal_selecionado,
                        "CNPJ": regime_tributario, # Usando regime como proxy de CNPJ se não tiver campo específico
                        "Produto": sku,
                        "Tipo": tipo,
                        "Qtd": qtd,
                        "Total Venda": valor_venda,
                        "Custo Produto": custo_total_prod,
                        "Custo Emb.": custo_emb,
                        "Imposto": imposto_valor,
                        "Taxa MP": taxa_mp_valor,
                        "Ads": 0.0, # Placeholder
                        "Custo Total": custo_total,
                        "Lucro Líquido": lucro,
                        "Margem %": margem
                    })
                
                df_resultados = pd.DataFrame(resultados)
                
                # --- EXIBIÇÃO ---
                st.subheader("Prévia dos Resultados (Verifique antes de salvar)")
                
                # Métricas Rápidas
                col1, col2, col3 = st.columns(3)
                col1.metric("Total Vendas", f"R$ {df_resultados['Total Venda'].sum():,.2f}")
                col2.metric("Lucro Estimado", f"R$ {df_resultados['Lucro Líquido'].sum():,.2f}")
                col3.metric("Margem Média", f"{df_resultados['Margem %'].mean()*100:.1f}%")
                
                st.dataframe(df_resultados.style.format({
                    "Total Venda": "R$ {:,.2f}",
                    "Lucro Líquido": "R$ {:,.2f}",
                    "Margem %": "{:.1%}"
                }))
                
                # --- BOTÃO DE SALVAR ---
                st.warning("⚠️ Atenção: Ao clicar abaixo, os dados serão ADICIONADOS ao Google Sheets. O histórico NÃO será apagado.")
                
                if st.button("💾 Confirmar e Enviar para Google Sheets"):
                    with st.spinner("Salvando dados e recalculando dashboards..."):
                        # 1. Salva dados brutos (Append)
                        sucesso_detalhes = safe_write_to_sheet(sheet, "6. Detalhes", df_resultados, mode='append')
                        sucesso_dash = safe_write_to_sheet(sheet, "1. Dashboard Geral", df_resultados, mode='append')
                        
                        if sucesso_detalhes and sucesso_dash:
                            # 2. Lê TODO o histórico para recalcular resumos
                            ws_detalhes = sheet.worksheet("6. Detalhes")
                            all_data = ws_detalhes.get_all_records()
                            df_historico = pd.DataFrame(all_data)
                            
                            # Converte colunas numéricas do histórico
                            cols_num = ['Total Venda', 'Lucro Líquido', 'Margem %', 'Qtd']
                            for col in cols_num:
                                if col in df_historico.columns:
                                    df_historico[col] = df_historico[col].apply(clean_currency)
                            
                            # --- RECÁLCULO DOS DASHBOARDS ---
                            
                            # A. Análise por CNPJ (Regime)
                            if 'CNPJ' in df_historico.columns:
                                df_cnpj = df_historico.groupby('CNPJ')[['Total Venda', 'Lucro Líquido']].sum().reset_index()
                                df_cnpj['Margem Média %'] = df_cnpj['Lucro Líquido'] / df_cnpj['Total Venda']
                                # Formatação
                                df_cnpj_view = df_cnpj.copy()
                                df_cnpj_view['Total Venda'] = df_cnpj_view['Total Venda'].apply(format_currency_br)
                                df_cnpj_view['Lucro Líquido'] = df_cnpj_view['Lucro Líquido'].apply(format_currency_br)
                                df_cnpj_view['Margem Média %'] = df_cnpj_view['Margem Média %'].apply(format_percent_br)
                                safe_write_to_sheet(sheet, "2. Análise por CNPJ", df_cnpj_view, mode='overwrite')
                            
                            # B. Análise Executiva (Por Canal)
                            if 'Canal' in df_historico.columns:
                                df_exec = df_historico.groupby('Canal')[['Total Venda', 'Lucro Líquido']].sum().reset_index()
                                df_exec['Margem %'] = df_exec['Lucro Líquido'] / df_exec['Total Venda']
                                # Formatação
                                df_exec_view = df_exec.copy()
                                df_exec_view['Total Venda'] = df_exec_view['Total Venda'].apply(format_currency_br)
                                df_exec_view['Lucro Líquido'] = df_exec_view['Lucro Líquido'].apply(format_currency_br)
                                df_exec_view['Margem %'] = df_exec_view['Margem %'].apply(format_percent_br)
                                safe_write_to_sheet(sheet, "3. Análise Executiva", df_exec_view, mode='overwrite')
                                
                            # C. Preços Marketplaces (Média de Venda por Produto)
                            if 'Produto' in df_historico.columns:
                                df_precos = df_historico.groupby(['Produto', 'Canal'])['Total Venda'].mean().reset_index()
                                df_precos.rename(columns={'Total Venda': 'Preço Médio Venda'}, inplace=True)
                                df_precos_view = df_precos.copy()
                                df_precos_view['Preço Médio Venda'] = df_precos_view['Preço Médio Venda'].apply(format_currency_br)
                                safe_write_to_sheet(sheet, "4. Preços Marketplaces", df_precos_view, mode='overwrite')

                            # D. Matriz BCG (NOVO!)
                            if 'Produto' in df_historico.columns:
                                # Agrupa por produto
                                df_bcg = df_historico.groupby('Produto').agg({
                                    'Total Venda': 'sum',
                                    'Lucro Líquido': 'sum',
                                    'Qtd': 'sum'
                                }).reset_index()
                                
                                df_bcg['Margem %'] = df_bcg['Lucro Líquido'] / df_bcg['Total Venda']
                                
                                # Critérios de Classificação (Média)
                                media_vendas = df_bcg['Total Venda'].mean()
                                media_margem = df_bcg['Margem %'].mean()
                                
                                def classificar_bcg(row):
                                    alta_venda = row['Total Venda'] >= media_vendas
                                    alta_margem = row['Margem %'] >= media_margem
                                    
                                    if alta_venda and alta_margem:
                                        return "⭐ Estrela"
                                    elif alta_venda and not alta_margem:
                                        return "🐄 Vaca Leiteira"
                                    elif not alta_venda and alta_margem:
                                        return "❓ Interrogação"
                                    else:
                                        return "🍍 Abacaxi"
                                
                                df_bcg['Classificação'] = df_bcg.apply(classificar_bcg, axis=1)
                                
                                # Formatação para salvar
                                df_bcg_view = df_bcg[['Produto', 'Total Venda', 'Margem %', 'Classificação']].copy()
                                df_bcg_view['Total Venda'] = df_bcg_view['Total Venda'].apply(format_currency_br)
                                df_bcg_view['Margem %'] = df_bcg_view['Margem %'].apply(format_percent_br)
                                
                                safe_write_to_sheet(sheet, "5. Matriz BCG", df_bcg_view, mode='overwrite')

                            st.success("✅ Dados salvos e dashboards atualizados com sucesso!")
                            st.balloons()
                        else:
                            st.error("Erro ao salvar dados.")

        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")
