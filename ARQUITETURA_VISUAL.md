# 🏗️ ARQUITETURA DO SISTEMA - Sales BI Pro

## 📊 FLUXO DE DADOS ATUAL

```
┌─────────────────────────────────────────────────────────────────┐
│                    FONTES DE DADOS EXTERNAS                     │
└─────────────────────────────────────────────────────────────────┘
                                 │
                    ┌────────────┴───────────┐
                    ▼                        ▼
        ┌───────────────────┐    ┌──────────────────────┐
        │  Google Sheets 1  │    │  Google Sheets 2     │
        │  (BCG Analysis)   │    │  (Estoque)           │
        │                   │    │                      │
        │  • Produtos       │    │  • estoque_atual     │
        │  • Custos         │    │  • estoque_min/max   │
        │  • Preços         │    │  • eh_kit            │
        │  • Vendas         │    │  • componentes       │
        │  • Análises       │    │  • custo_unitario    │
        └─────────┬─────────┘    └──────────┬───────────┘
                  │                         │
                  │  ✅ INTEGRADO            │  ❌ NÃO INTEGRADO
                  │                         │
                  ▼                         ▼
        ┌─────────────────────────────────────────┐
        │      STREAMLIT APP (app.py)             │
        │                                         │
        │  ┌───────────────────────────────┐     │
        │  │  MÓDULOS DISPONÍVEIS:         │     │
        │  │                               │     │
        │  │  ✅ bcg_analysis.py           │     │
        │  │  ✅ google_sheets_integration │     │
        │  │  ✅ stock_projection.py       │     │
        │  │  ✅ profitability_analysis.py │     │
        │  │  ✅ pareto_analysis.py        │     │
        │  └───────────────────────────────┘     │
        │                                         │
        │  TABS ATUAIS:                           │
        │  📈 Visão Geral                         │
        │  🏢 Por CNPJ                            │
        │  ⭐ BCG Geral                           │
        │  🎯 BCG por Canal                       │
        │  💲 Preços                              │
        │  📝 Detalhes                            │
        │  🔄 Giro de Produtos                    │
        │  🚀 Oportunidades                       │
        └─────────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────────────┐
        │         USUÁRIO FINAL                   │
        │  https://salesholdingsilvabi...         │
        └─────────────────────────────────────────┘
```

---

## 🎯 ARQUITETURA PROPOSTA (APÓS MELHORIAS)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     FONTES DE DADOS EXTERNAS                         │
└──────────────────────────────────────────────────────────────────────┘
                                    │
            ┌───────────────────────┼────────────────────────┐
            ▼                       ▼                        ▼
┌─────────────────┐    ┌──────────────────────┐   ┌──────────────────┐
│ Google Sheets 1 │    │  Google Sheets 2     │   │  Upload Manual   │
│ (BCG/Vendas)    │    │  (Estoque)           │   │  (Excel/CSV)     │
│                 │    │                      │   │                  │
│ • Dashboard     │    │  • Produtos          │   │  • Bling         │
│ • CNPJ          │    │  • Estoque atual     │   │  • ML/Shopee     │
│ • BCG Matrix    │    │  • Kits (BOM)        │   │  • Shein         │
│ • Preços        │    │  • Componentes       │   │                  │
│ • Detalhes      │    │  • Níveis min/max    │   │                  │
│ • Giro          │    │                      │   │                  │
│ • Oportunidades │    │                      │   │                  │
└────────┬────────┘    └──────────┬───────────┘   └────────┬─────────┘
         │                        │                        │
         │  ✅ READ              │  ✅ READ ONLY          │  📤 PROCESS
         ▼                        ▼                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                    DATA PROCESSING LAYER                           │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │  NEW MODULES TO ADD:                                         │ │
│  │                                                               │ │
│  │  🆕 inventory_integration.py                                 │ │
│  │     - Lê planilha de estoque (somente leitura)              │ │
│  │     - Calcula cobertura de estoque                          │ │
│  │     - Identifica produtos em ruptura                        │ │
│  │                                                               │ │
│  │  🆕 bom_analysis.py (Bill of Materials)                      │ │
│  │     - Explode estrutura de kits                             │ │
│  │     - Calcula necessidade de insumos                        │ │
│  │     - Verifica disponibilidade (múltiplas camadas)          │ │
│  │                                                               │ │
│  │  🆕 production_report.py                                     │ │
│  │     - Gera ordem de produção                                │ │
│  │     - Lista insumos faltantes por camada                    │ │
│  │     - Sugere prioridades de compra                          │ │
│  │                                                               │ │
│  │  🆕 sales_importer.py                                        │ │
│  │     - Processa upload de vendas                             │ │
│  │     - Normaliza dados de diferentes marketplaces            │ │
│  │     - Atualiza planilha BCG automaticamente                 │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                      STREAMLIT APP ENHANCED                        │
│                                                                    │
│  EXISTING TABS:                    NEW TABS:                      │
│  📈 Visão Geral                   🆕 📦 Gestão de Estoque         │
│  🏢 Por CNPJ                       🆕 🏭 Análise BOM              │
│  ⭐ BCG Geral                      🆕 📋 Ordem de Produção        │
│  🎯 BCG por Canal                  🆕 ⚠️ Alertas de Ruptura       │
│  💲 Preços                         🆕 📊 Dashboard Executivo      │
│  📝 Detalhes                                                      │
│  🔄 Giro de Produtos                                              │
│  🚀 Oportunidades                                                 │
│                                                                    │
│  FEATURES ENHANCED:                                                │
│  ✨ Upload automático → Planilha BCG                              │
│  ✨ Análise de ruptura em tempo real                             │
│  ✨ Sugestão de compras baseada em vendas                        │
│  ✨ Visualização de estrutura de kits (árvore)                   │
│  ✨ Exportação de relatórios (PDF/Excel)                         │
└────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                         OUTPUTS & INSIGHTS                         │
│                                                                    │
│  📊 Dashboards Interativos                                        │
│  📈 Gráficos BCG com drill-down                                   │
│  📦 Status de estoque em tempo real                               │
│  🏭 Ordens de produção priorizadas                                │
│  ⚠️ Alertas de ruptura/oportunidades                              │
│  📄 Relatórios executivos (PDF/Excel)                             │
│  💡 Insights automáticos (ML futuro)                              │
└────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 FLUXO DE INTEGRAÇÃO ESTOQUE ↔ VENDAS

```
┌────────────────────────────────────────────────────────────────┐
│  CENÁRIO: Análise de Necessidade de Produção                  │
└────────────────────────────────────────────────────────────────┘

1️⃣ VENDAS (Últimos 30 dias)
   │
   ├─→ Produto A: 100 unidades vendidas
   ├─→ Produto B: 50 unidades vendidas
   └─→ Produto C: 200 unidades vendidas
   
                    ↓ ANÁLISE BCG
   
   ┌────────────────────────────────┐
   │ Classificação:                 │
   │ • Produto C = ⭐ Estrela       │
   │ • Produto A = 🐄 Vaca Leiteira │
   │ • Produto B = 🍍 Abacaxi       │
   └────────────────────────────────┘

2️⃣ PROJEÇÃO (Próximos 30 dias)
   │
   ├─→ Produto A: ~100 unidades (estável)
   ├─→ Produto B: ~30 unidades (queda)
   └─→ Produto C: ~250 unidades (crescimento)

                    ↓ CROSS-CHECK ESTOQUE
   
   ┌────────────────────────────────────────┐
   │ Estoque Atual:                         │
   │ • Produto A: 120 un ✅ OK (12 dias)    │
   │ • Produto B: 80 un ✅ OK (80 dias)     │
   │ • Produto C: 50 un ⚠️ CRÍTICO (6 dias) │
   └────────────────────────────────────────┘

3️⃣ ANÁLISE BOM (Produto C = Kit)
   │
   └─→ Produto C precisa:
       │
       ├─→ Insumo X: 2 unidades/produto
       │   └─→ Necessário: 500 unidades
       │       └─→ Em estoque: 200 unidades ❌
       │           └─→ FALTAM: 300 unidades
       │
       ├─→ Insumo Y: 1 unidade/produto
       │   └─→ Necessário: 250 unidades
       │       └─→ Em estoque: 300 unidades ✅
       │
       └─→ Insumo Z: 3 unidades/produto
           └─→ Necessário: 750 unidades
               └─→ Em estoque: 100 unidades ❌
                   └─→ FALTAM: 650 unidades
                       │
                       └─→ Insumo Z é KIT! Verificar componentes:
                           ├─→ Sub-insumo Z1: 2 un ✅ OK
                           └─→ Sub-insumo Z2: 1 un ❌ FALTA 200

4️⃣ RELATÓRIO DE PRODUÇÃO
   
   ┌─────────────────────────────────────────────────────┐
   │ 🏭 ORDEM DE PRODUÇÃO - Produto C (Prioridade ALTA)  │
   ├─────────────────────────────────────────────────────┤
   │ Meta: Produzir 250 unidades                         │
   │                                                     │
   │ ⚠️ INSUMOS FALTANTES:                               │
   │                                                     │
   │ Nível 1 (Produto Final):                           │
   │ • Insumo X: Comprar 300 unidades                   │
   │ • Insumo Z: Produzir 650 unidades                  │
   │                                                     │
   │ Nível 2 (Componentes do Insumo Z):                 │
   │ • Sub-insumo Z2: Comprar 200 unidades              │
   │                                                     │
   │ 💰 INVESTIMENTO ESTIMADO:                           │
   │ • Insumo X: R$ 4.500,00 (300 × R$ 15)              │
   │ • Sub-insumo Z2: R$ 1.000,00 (200 × R$ 5)          │
   │ • TOTAL: R$ 5.500,00                               │
   │                                                     │
   │ 📅 PRAZO: 15 dias (considerando lead time)         │
   └─────────────────────────────────────────────────────┘
```

---

## 🎯 DECISÃO DE IMPLEMENTAÇÃO

### Opção A: RÁPIDA (2-3 horas)
**Integração Básica de Estoque**

```python
# Adicionar ao app.py
@st.cache_data(ttl=300)
def carregar_estoque():
    url = "https://docs.google.com/.../export?format=csv&gid=..."
    df = pd.read_csv(url)
    return df

# Nova aba
with tabs[8]:  # 📦 Gestão de Estoque
    df_estoque = carregar_estoque()
    st.dataframe(df_estoque)
    
    # Produtos com estoque baixo
    baixo = df_estoque[df_estoque['estoque_atual'] < df_estoque['estoque_min']]
    st.warning(f"⚠️ {len(baixo)} produtos abaixo do estoque mínimo")
```

**Entregável**: Visualização de estoque + alertas simples

---

### Opção B: MÉDIA (1 dia)
**Integração + Análise de Ruptura**

```python
# modules/inventory_analysis.py
class InventoryAnalysis:
    def __init__(self, df_vendas, df_estoque):
        self.vendas = df_vendas
        self.estoque = df_estoque
    
    def calcular_cobertura(self):
        # Média de vendas diárias
        media_vendas = self.vendas.groupby('Produto')['Quantidade'].sum() / 30
        
        # Cruzar com estoque
        df = self.estoque.merge(media_vendas, on='codigo')
        df['dias_cobertura'] = df['estoque_atual'] / df['media_vendas']
        
        return df
    
    def produtos_em_risco(self, dias_limite=7):
        cobertura = self.calcular_cobertura()
        return cobertura[cobertura['dias_cobertura'] < dias_limite]
```

**Entregável**: Análise completa de ruptura com dias de cobertura

---

### Opção C: COMPLETA (2-3 dias)
**BOM + Produção + Relatórios**

```python
# modules/bom_analysis.py
class BOMAnalysis:
    def explode_kit(self, produto_codigo, quantidade_necessaria):
        """
        Explode kit em múltiplas camadas
        Retorna árvore de necessidades
        """
        tree = {
            'produto': produto_codigo,
            'quantidade': quantidade_necessaria,
            'em_estoque': self.get_estoque(produto_codigo),
            'faltante': max(0, quantidade_necessaria - self.get_estoque(produto_codigo)),
            'componentes': []
        }
        
        # Se é kit, explodir componentes
        if self.is_kit(produto_codigo):
            componentes = self.get_componentes(produto_codigo)
            for comp in componentes:
                qtd_comp = comp['quantidade'] * tree['faltante']
                # RECURSÃO: explodir componente
                tree['componentes'].append(
                    self.explode_kit(comp['codigo'], qtd_comp)
                )
        
        return tree
```

**Entregável**: Sistema completo de BOM + Ordem de Produção

---

## 🤔 QUAL VOCÊ PREFERE?

**Responda qual opção quer que eu implemente:**

- [ ] **A) RÁPIDA** - Ver estoque no app (2-3h)
- [ ] **B) MÉDIA** - Estoque + Ruptura (1 dia)
- [ ] **C) COMPLETA** - Tudo acima + BOM (2-3 dias)
- [ ] **D) CUSTOMIZADA** - Diga o que quer especificamente

**Estou pronto para começar! 🚀**
