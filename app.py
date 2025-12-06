import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

st.set_page_config(page_title="Sales BI Analytics", page_icon="📊", layout="wide")
st.title("📊 Sales BI Analytics")

CHANNELS = {'geral': '📊 Vendas Gerais', 'mercado_livre': '🛒 Mercado Livre', 'shopee_matriz': '🛍️ Shopee Matriz', 'shopee_150': '🏪 Shopee 1:50', 'shein': '👗 Shein'}

def converter_planilha_bling(df_bling, data_venda):
    df = pd.DataFrame()
    df['Data'] = data_venda
    df['Produto'] = df_bling['Código']
    df['Quantidade'] = df_bling['Quantidade']
    df['Total'] = df_bling['Valor'].apply(lambda x: float(str(x).replace('R$','').replace('.','').replace(',','.').strip()))
    df['Preço Unitário'] = df['Total'] / df['Quantidade']
    return df

with st.sidebar:
    st.header("⚙️ Config")
    config_file = st.file_uploader("📋 Produtos/Canais (Excel)", type=['xlsx','xls'])
    if config_file:
        produtos_df = pd.read_excel(config_file, sheet_name='Produtos')
        canais_df = pd.read_excel(config_file, sheet_name='Canais')
        st.session_state['produtos_config'] = produtos_df
        st.session_state['canais_config'] = canais_df
        st.success(f"✅ {len(produtos_df)} produtos")
    
    st.divider()
    st.header("📤 Vendas")
    formato = st.radio("Formato", ['Bling', 'Padrão'])
    canal = st.selectbox("Canal", list(CHANNELS.keys()), format_func=lambda x: CHANNELS[x])
    if formato == 'Bling':
        data_venda = st.date_input("Data", datetime.now())
    uploaded_file = st.file_uploader("Excel", type=['xlsx','xls'])
    
    if uploaded_file and st.button("🔄 Processar"):
        try:
            df_original = pd.read_excel(uploaded_file)
            if 'Código' in df_original.columns:
                df_novo = converter_planilha_bling(df_original, data_venda.strftime('%Y-%m-%d'))
            else:
                df_novo = df_original.copy()
            
            df_novo['Canal'] = CHANNELS[canal]
            df_novo['Data_Upload'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Enriquecer com config
            if 'produtos_config' in st.session_state:
                prod_config = st.session_state['produtos_config']
                prod_dict = dict(zip(prod_config['Código'], prod_config['Custo (R$)']))
                preco_dict = dict(zip(prod_config['Código'], prod_config['Preço Venda (R$)']))
                
                df_novo['Custo_Unit'] = df_novo['Produto'].map(prod_dict).fillna(0)
                df_novo['Preco_Cadastrado'] = df_novo['Produto'].map(preco_dict).fillna(0)
                df_novo['Custo_Total'] = df_novo['Custo_Unit'] * df_novo['Quantidade']
                df_novo['Margem_Bruta'] = df_novo['Total'] - df_novo['Custo_Total']
                
                # VALIDAÇÃO DE PREÇO
                df_novo['Preco_Real'] = df_novo['Preço Unitário']
                df_novo['Divergencia_%'] = ((df_novo['Preco_Real'] - df_novo['Preco_Cadastrado']) / df_novo['Preco_Cadastrado'] * 100).fillna(0)
                
                # Alertas
                divergencias = df_novo[abs(df_novo['Divergencia_%']) > 5]
                if len(divergencias) > 0:
                    st.warning(f"⚠️ {len(divergencias)} produtos com preço divergente (>5%)")
            
            if 'canais_config' in st.session_state:
                canal_df = st.session_state['canais_config']
                canal_info = canal_df[canal_df['Canal'] == canal.replace('_',' ').title()].iloc[0] if len(canal_df[canal_df['Canal'] == canal.replace('_',' ').title()]) > 0 else None
                if canal_info is not None:
                    taxa_mkt = canal_info['Taxa Marketplace (%)'] / 100
                    df_novo['Taxa_Marketplace'] = df_novo['Total'] * taxa_mkt
                    df_novo['Taxa_Fixa'] = canal_info['Taxa Fixa por Pedido (R$)'] / len(df_novo)
                    df_novo['Taxa_Gateway'] = canal_info['Taxa Gateway (R$)'] / len(df_novo)
                    df_novo['Lucro_Liquido'] = df_novo['Margem_Bruta'] - df_novo['Taxa_Marketplace'] - df_novo['Taxa_Fixa'] - df_novo['Taxa_Gateway']
            
            st.session_state['data_novo'] = df_novo
            st.dataframe(df_novo.head())
            
            col1,col2,col3 = st.columns(3)
            col1.metric("Produtos", len(df_novo))
            col2.metric("Faturamento", f"R$ {df_novo['Total'].sum():,.2f}")
            if 'Lucro_Liquido' in df_novo.columns:
                col3.metric("Lucro", f"R$ {df_novo['Lucro_Liquido'].sum():,.2f}")
        except Exception as e:
            st.error(f"❌ {e}")

if 'data_novo' in st.session_state:
    if st.button("📤 Enviar"):
        try:
            df_novo = st.session_state['data_novo']
            scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(st.secrets["GOOGLE_SHEETS_CREDENTIALS"]), scope)
            ss = gspread.authorize(creds).open_by_url(st.secrets["GOOGLE_SHEETS_URL"])
            
            # Ler existente
            try:
                sh = ss.worksheet("6. Detalhes")
                ex = sh.get_all_values()
                df_ex = pd.DataFrame(ex[1:], columns=ex[0]) if len(ex)>1 else pd.DataFrame()
                for c in ['Quantidade','Total','Custo_Total','Margem_Bruta','Lucro_Liquido']:
                    if c in df_ex.columns: df_ex[c] = pd.to_numeric(df_ex[c], errors='coerce')
            except:
                df_ex = pd.DataFrame()
            
            try: sh = ss.worksheet("6. Detalhes")
            except: sh = ss.add_worksheet("6. Detalhes", 5000, 20)
            
            df_full = pd.concat([df_ex, df_novo], ignore_index=True) if not df_ex.empty else df_novo
            
            # Análise
            agg = {'Quantidade':'sum','Total':'sum'}
            if 'Custo_Total' in df_full.columns: agg.update({'Custo_Total':'sum','Margem_Bruta':'sum'})
            if 'Lucro_Liquido' in df_full.columns: agg['Lucro_Liquido'] = 'sum'
            
            prods = df_full.groupby('Produto').agg(agg).reset_index()
            total = prods['Total'].sum()
            prods['Part%'] = (prods['Total']/total)*100
            
            med_q = prods['Quantidade'].median()
            med_p = prods['Part%'].median()
            
            def bcg(r):
                if r['Quantidade']>=med_q and r['Part%']>=med_p: return 'Estrela'
                elif r['Quantidade']<med_q and r['Part%']>=med_p: return 'Vaca Leiteira'
                elif r['Quantidade']>=med_q and r['Part%']<med_p: return 'Interrogação'
                else: return 'Abacaxi'
            
            prods['BCG'] = prods.apply(bcg, axis=1)
            
            if 'Data' in df_full.columns:
                df_full['Data'] = pd.to_datetime(df_full['Data'], errors='coerce')
                dias_df = df_full.groupby('Data').agg({'Total':'sum','Quantidade':'sum'}).reset_index().sort_values('Data')
            
            dias = len(df_full['Data'].unique()) if 'Data' in df_full.columns else 1
            
            # DIVERGÊNCIAS
            if 'Divergencia_%' in df_full.columns:
                diverg = df_full[abs(df_full['Divergencia_%'])>5][['Produto','Preco_Cadastrado','Preco_Real','Divergencia_%']].drop_duplicates()
                try: sh_div = ss.worksheet("7. Divergencias")
                except: sh_div = ss.add_worksheet("7. Divergencias", 200, 5)
                
                dados_div = [['DIVERGÊNCIAS DE PREÇO (>5%)'], [], ['Produto','Preço Config','Preço Real','Diferença %']]
                for _,d in diverg.iterrows():
                    dados_div.append([d['Produto'], f"R$ {d['Preco_Cadastrado']:.2f}", f"R$ {d['Preco_Real']:.2f}", f"{d['Divergencia_%']:.1f}%"])
                sh_div.clear()
                sh_div.update('A1', dados_div)
            
            # Dashboard
            try: sh1 = ss.worksheet("1. Dashboard")
            except: sh1 = ss.add_worksheet("1. Dashboard", 100, 5)
            
            lucro = prods['Lucro_Liquido'].sum() if 'Lucro_Liquido' in prods.columns else 0
            margem = prods['Margem_Bruta'].sum() if 'Margem_Bruta' in prods.columns else 0
            
            d1 = [['DASHBOARD'],
                  [datetime.now().strftime("%d/%m/%Y %H:%M")],[],
                  ['Dias',dias],
                  ['Faturamento',f'R$ {total:,.2f}'],
                  ['Margem',f'R$ {margem:,.2f}'],
                  ['Lucro',f'R$ {lucro:,.2f}'],
                  ['Produtos',len(prods)],[],
                  ['BCG','Qtd','Faturamento','Lucro']]
            
            for cat in ['Estrela','Vaca Leiteira','Interrogação','Abacaxi']:
                pc = prods[prods['BCG']==cat]
                lc = pc['Lucro_Liquido'].sum() if 'Lucro_Liquido' in pc.columns else 0
                d1.append([cat, len(pc), f'R$ {pc["Total"].sum():,.2f}', f'R$ {lc:,.2f}'])
            
            sh1.clear()
            sh1.update('A1', d1)
            
            # Detalhes
            cols = ['Data','Produto','Qtd','Preço','Total','Canal','BCG','Upload']
            if 'Custo_Total' in df_full.columns: cols.insert(5,'Custo')
            if 'Lucro_Liquido' in df_full.columns: cols.insert(-2,'Lucro')
            if 'Divergencia_%' in df_full.columns: cols.insert(-2,'Diverg%')
            
            d6 = [cols]
            for _,r in df_full.iterrows():
                cat = prods[prods['Produto']==r['Produto']]['BCG'].values[0] if r['Produto'] in prods['Produto'].values else 'N/A'
                linha = [str(r.get('Data','')), r['Produto'], int(r['Quantidade']), float(r['Preço Unitário']), float(r['Total'])]
                if 'Custo_Total' in r: linha.append(float(r['Custo_Total']))
                if 'Lucro_Liquido' in r: linha.append(float(r['Lucro_Liquido']))
                if 'Divergencia_%' in r: linha.append(f"{r['Divergencia_%']:.1f}%")
                linha.extend([r.get('Canal',''), cat, r.get('Data_Upload','')])
                d6.append(linha)
            
            sh.clear()
            sh.update('A1', d6)
            
            st.success(f"✅ {len(df_full)} registros")
            if 'Divergencia_%' in df_full.columns:
                divs = len(df_full[abs(df_full['Divergencia_%'])>5])
                if divs > 0:
                    st.warning(f"⚠️ {divs} produtos com preço divergente - veja aba 'Divergencias'")
            st.info(f"🔗 [Abrir]({st.secrets['GOOGLE_SHEETS_URL']})")
        except Exception as e:
            st.error(f"❌ {e}")
else:
    st.info("👈 Configure e faça upload")
