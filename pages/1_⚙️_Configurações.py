import streamlit as st
import pandas as pd
import json
import os

st.set_page_config(
    page_title="Configurações - Sales BI",
    page_icon="⚙️",
    layout="wide"
)

st.title("⚙️ Configurações do Sistema")

# Diretório de configurações
CONFIG_DIR = "data"
PRODUCTS_CONFIG = os.path.join(CONFIG_DIR, "products_config.json")
CHANNELS_CONFIG = os.path.join(CONFIG_DIR, "channels_config.json")

# Criar diretório se não existir
os.makedirs(CONFIG_DIR, exist_ok=True)

# Carregar configurações existentes
def load_config(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_config(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Tabs
tab1, tab2, tab3 = st.tabs(["💰 Produtos", "🏪 Canais", "📊 Visualizar"])

with tab1:
    st.header("💰 Configuração de Produtos")
    st.markdown("Configure custos e preços de venda dos produtos")
    
    products_config = load_config(PRODUCTS_CONFIG)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("➕ Adicionar/Editar Produto")
        
        produto_nome = st.text_input("Nome do Produto", key="produto_nome")
        custo_unitario = st.number_input("Custo Unitário (R$)", min_value=0.0, step=0.01, key="custo")
        preco_venda = st.number_input("Preço de Venda (R$)", min_value=0.0, step=0.01, key="preco")
        
        if st.button("💾 Salvar Produto", use_container_width=True):
            if produto_nome:
                if 'custos' not in products_config:
                    products_config['custos'] = {}
                if 'precos' not in products_config:
                    products_config['precos'] = {}
                
                products_config['custos'][produto_nome] = custo_unitario
                products_config['precos'][produto_nome] = preco_venda
                
                save_config(PRODUCTS_CONFIG, products_config)
                st.success(f"✅ Produto '{produto_nome}' salvo com sucesso!")
                st.rerun()
            else:
                st.error("❌ Digite o nome do produto")
    
    with col2:
        st.subheader("📋 Produtos Cadastrados")
        
        if products_config.get('custos'):
            df_produtos = pd.DataFrame({
                'Produto': list(products_config['custos'].keys()),
                'Custo (R$)': list(products_config['custos'].values()),
                'Preço (R$)': [products_config['precos'].get(p, 0) for p in products_config['custos'].keys()]
            })
            
            df_produtos['Margem Bruta (%)'] = ((df_produtos['Preço (R$)'] - df_produtos['Custo (R$)']) / df_produtos['Preço (R$)'] * 100).round(2)
            
            st.dataframe(df_produtos, use_container_width=True, height=400)
            
            # Opção de deletar
            st.markdown("---")
            produto_deletar = st.selectbox("Deletar Produto", [''] + list(products_config['custos'].keys()))
            
            if produto_deletar and st.button("🗑️ Deletar", use_container_width=True):
                if produto_deletar in products_config['custos']:
                    del products_config['custos'][produto_deletar]
                if produto_deletar in products_config['precos']:
                    del products_config['precos'][produto_deletar]
                
                save_config(PRODUCTS_CONFIG, products_config)
                st.success(f"✅ Produto '{produto_deletar}' deletado!")
                st.rerun()
        else:
            st.info("📝 Nenhum produto cadastrado ainda")
    
    # Upload em massa
    st.markdown("---")
    st.subheader("📤 Upload em Massa")
    
    uploaded_products = st.file_uploader(
        "Carregar planilha de produtos (Colunas: Produto, Custo, Preço)",
        type=['xlsx', 'xls', 'csv'],
        key="upload_products"
    )
    
    if uploaded_products:
        try:
            if uploaded_products.name.endswith('.csv'):
                df_upload = pd.read_csv(uploaded_products)
            else:
                df_upload = pd.read_excel(uploaded_products)
            
            st.dataframe(df_upload.head(), use_container_width=True)
            
            if st.button("💾 Importar Produtos", use_container_width=True):
                if 'custos' not in products_config:
                    products_config['custos'] = {}
                if 'precos' not in products_config:
                    products_config['precos'] = {}
                
                for idx, row in df_upload.iterrows():
                    produto = str(row.get('Produto', row.get('produto', '')))
                    custo = float(row.get('Custo', row.get('custo', 0)))
                    preco = float(row.get('Preço', row.get('Preco', row.get('preco', 0))))
                    
                    if produto:
                        products_config['custos'][produto] = custo
                        products_config['precos'][produto] = preco
                
                save_config(PRODUCTS_CONFIG, products_config)
                st.success(f"✅ {len(df_upload)} produtos importados!")
                st.rerun()
        
        except Exception as e:
            st.error(f"❌ Erro ao processar arquivo: {str(e)}")

with tab2:
    st.header("🏪 Configuração de Canais")
    st.markdown("Configure taxas variáveis e fixas por canal de venda")
    
    channels_config = load_config(CHANNELS_CONFIG)
    
    # Canais disponíveis
    CANAIS = {
        'Geral': '📊 Vendas Gerais',
        'Mercado Livre': '🛒 Mercado Livre',
        'Shopee Matriz': '🛍️ Shopee Matriz',
        'Shopee 1:50': '🏪 Shopee 1:50',
        'Shein': '👗 Shein'
    }
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("➕ Configurar Canal")
        
        canal_selecionado = st.selectbox(
            "Selecione o Canal",
            list(CANAIS.keys()),
            format_func=lambda x: CANAIS[x]
        )
        
        st.markdown(f"### {CANAIS[canal_selecionado]}")
        
        taxa_variavel = st.number_input(
            "Taxa Variável (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            value=channels_config.get(canal_selecionado, {}).get('taxa_variavel', 0.0),
            help="Percentual sobre o valor da venda (ex: comissão do marketplace)"
        )
        
        taxa_fixa = st.number_input(
            "Taxa Fixa por Venda (R$)",
            min_value=0.0,
            step=0.01,
            value=channels_config.get(canal_selecionado, {}).get('taxa_fixa', 0.0),
            help="Valor fixo cobrado por venda (ex: taxa de envio, embalagem)"
        )
        
        if st.button("💾 Salvar Configuração", use_container_width=True):
            channels_config[canal_selecionado] = {
                'taxa_variavel': taxa_variavel,
                'taxa_fixa': taxa_fixa
            }
            
            save_config(CHANNELS_CONFIG, channels_config)
            st.success(f"✅ Configuração do canal '{canal_selecionado}' salva!")
            st.rerun()
    
    with col2:
        st.subheader("📋 Canais Configurados")
        
        if channels_config:
            df_canais = pd.DataFrame([
                {
                    'Canal': canal,
                    'Taxa Variável (%)': config.get('taxa_variavel', 0),
                    'Taxa Fixa (R$)': config.get('taxa_fixa', 0)
                }
                for canal, config in channels_config.items()
            ])
            
            st.dataframe(df_canais, use_container_width=True)
        else:
            st.info("📝 Nenhum canal configurado ainda")
        
        # Exemplo de cálculo
        st.markdown("---")
        st.markdown("### 💡 Exemplo de Cálculo")
        
        if canal_selecionado in channels_config:
            config = channels_config[canal_selecionado]
            
            exemplo_preco = st.number_input("Preço de Venda (R$)", value=100.0, step=1.0)
            
            taxa_var_valor = exemplo_preco * (config['taxa_variavel'] / 100)
            taxa_total = taxa_var_valor + config['taxa_fixa']
            valor_liquido = exemplo_preco - taxa_total
            
            col_a, col_b, col_c = st.columns(3)
            
            with col_a:
                st.metric("Taxa Variável", f"R$ {taxa_var_valor:.2f}")
            
            with col_b:
                st.metric("Taxa Total", f"R$ {taxa_total:.2f}")
            
            with col_c:
                st.metric("Valor Líquido", f"R$ {valor_liquido:.2f}")

with tab3:
    st.header("📊 Visualização Geral")
    
    products_config = load_config(PRODUCTS_CONFIG)
    channels_config = load_config(CHANNELS_CONFIG)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("💰 Resumo de Produtos")
        
        if products_config.get('custos'):
            total_produtos = len(products_config['custos'])
            custo_medio = sum(products_config['custos'].values()) / total_produtos
            preco_medio = sum(products_config['precos'].values()) / total_produtos
            margem_media = ((preco_medio - custo_medio) / preco_medio * 100)
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.metric("Total de Produtos", total_produtos)
                st.metric("Custo Médio", f"R$ {custo_medio:.2f}")
            
            with col_b:
                st.metric("Preço Médio", f"R$ {preco_medio:.2f}")
                st.metric("Margem Média", f"{margem_media:.1f}%")
        else:
            st.info("📝 Configure produtos na aba 'Produtos'")
    
    with col2:
        st.subheader("🏪 Resumo de Canais")
        
        if channels_config:
            total_canais = len(channels_config)
            taxa_var_media = sum(c.get('taxa_variavel', 0) for c in channels_config.values()) / total_canais
            taxa_fixa_media = sum(c.get('taxa_fixa', 0) for c in channels_config.values()) / total_canais
            
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.metric("Canais Configurados", total_canais)
                st.metric("Taxa Variável Média", f"{taxa_var_media:.1f}%")
            
            with col_b:
                st.metric("Taxa Fixa Média", f"R$ {taxa_fixa_media:.2f}")
        else:
            st.info("📝 Configure canais na aba 'Canais'")
    
    # Exportar configurações
    st.markdown("---")
    st.subheader("📥 Exportar Configurações")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📥 Baixar Config. Produtos (JSON)", use_container_width=True):
            if products_config:
                st.download_button(
                    "💾 Download",
                    data=json.dumps(products_config, ensure_ascii=False, indent=2),
                    file_name="produtos_config.json",
                    mime="application/json",
                    use_container_width=True
                )
    
    with col2:
        if st.button("📥 Baixar Config. Canais (JSON)", use_container_width=True):
            if channels_config:
                st.download_button(
                    "💾 Download",
                    data=json.dumps(channels_config, ensure_ascii=False, indent=2),
                    file_name="canais_config.json",
                    mime="application/json",
                    use_container_width=True
                )
