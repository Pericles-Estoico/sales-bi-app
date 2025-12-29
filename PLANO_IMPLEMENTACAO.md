# 🚀 PLANO DE IMPLEMENTAÇÃO - Opção B (Média)

**Data Início**: 29/12/2024  
**Prazo**: 1 dia  
**Créditos**: Otimizado (mínimo necessário)

---

## 📋 REQUISITOS CONFIRMADOS

### 1. Dados Existentes
- ✅ **Vendas reais**: 01/12 a 26/12/2024 na planilha BCG
- ✅ **Não misturar** com dados de teste
- ✅ **Estoque atual**: Planilha template_estoque (gid=1456159896)

### 2. Integrações
| Planilha | Leitura | Escrita | Propósito |
|----------|---------|---------|-----------|
| **Config_BI_Final_MatrizBCG** | ✅ | ✅ | Análise BCG + Preços |
| **template_estoque** | ✅ | ✅* | Gestão de Estoque |

*Escrita SOMENTE para:
- Sincronizar produtos faltantes (com estoque zero)
- Via operador manual (não automático)

### 3. Funcionalidades Críticas

#### ✅ Fazer
1. **Ler template_estoque** (somente visualização no app)
2. **Cruzar vendas × estoque** (análise de ruptura)
3. **Detectar produtos faltantes** (BCG → template_estoque)
4. **Gerar Excel para upload** (produtos faltantes formatados)
5. **Normalizar separadores** (vírgula/ponto-vírgula automático)

#### ❌ NÃO Fazer
- ❌ Lançamento automático de entrada/saída de estoque
- ❌ Misturar planilhas (cada uma tem seu propósito)
- ❌ Copiar dados de estoque para BCG
- ❌ Alterar dados de vendas existentes (01-26/12)

---

## 🏗️ ESTRUTURA DE IMPLEMENTAÇÃO

### Arquivo 1: `modules/inventory_integration.py`
**Responsabilidade**: Ler e processar dados de estoque

```python
class InventoryIntegration:
    def __init__(self, estoque_url, bcg_url):
        self.estoque_url = estoque_url
        self.bcg_url = bcg_url
    
    def carregar_estoque(self):
        """Lê template_estoque com normalização automática"""
        # Normaliza vírgula/ponto-vírgula
        # Retorna DataFrame limpo
    
    def produtos_faltantes(self, df_bcg):
        """Identifica produtos em BCG mas não em estoque"""
        # Compara códigos
        # Retorna lista de faltantes
    
    def gerar_excel_para_upload(self, produtos_faltantes):
        """Cria Excel formatado para upload em template_estoque"""
        # Formato correto das colunas
        # Estoque = 0
        # Pronto para upload
```

### Arquivo 2: `modules/rupture_analysis.py`
**Responsabilidade**: Análise de ruptura e cobertura

```python
class RuptureAnalysis:
    def calcular_cobertura(self, df_vendas, df_estoque):
        """
        Calcula dias de cobertura de estoque
        Baseado em vendas reais (01-26/12)
        """
        # Média de vendas por produto/dia
        # Estoque atual / média diária
        # Retorna dias de cobertura
    
    def alertas_criticos(self, cobertura_dias, limite=7):
        """Produtos com menos de X dias de estoque"""
        # 🔴 < 3 dias
        # 🟡 3-7 dias
        # 🟢 > 7 dias
```

### Arquivo 3: Atualização `app.py`
**Adicionar**: Nova aba "📦 Gestão de Estoque"

```python
# Nova aba no tabs
with tabs[8]:  # 📦 Gestão de Estoque
    st.subheader("📦 Gestão de Estoque")
    
    # 1. Carregar estoque
    df_estoque = carregar_estoque_template()
    
    # 2. Análise de ruptura
    df_ruptura = analisar_ruptura(df_vendas, df_estoque)
    
    # 3. Produtos faltantes
    faltantes = detectar_produtos_faltantes(df_bcg, df_estoque)
    
    # 4. Botão de download Excel
    if faltantes:
        excel_file = gerar_excel_faltantes(faltantes)
        st.download_button("📥 Baixar produtos faltantes", excel_file)
```

---

## 📊 NORMALIZAÇÃO DE DADOS

### Problema Identificado
```
Planilha BCG:     "7,24" (vírgula decimal)
Planilha Estoque: "14,9" (vírgula decimal)
```

### Solução
```python
def normalizar_decimal(valor):
    """
    Converte qualquer formato para float
    "7,24" → 7.24
    "14.9" → 14.9
    "1.234,56" → 1234.56
    """
    if pd.isna(valor):
        return 0.0
    
    s = str(valor).strip()
    
    # Detecta separador decimal
    if ',' in s and '.' in s:
        # Formato brasileiro: 1.234,56
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        # Apenas vírgula: 7,24
        s = s.replace(',', '.')
    
    return float(s)
```

---

## 🎯 FLUXO DE SINCRONIZAÇÃO

```
┌─────────────────────────────────────────────────┐
│ 1. USUÁRIO ACESSA ABA "GESTÃO DE ESTOQUE"      │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 2. APP LÊ AMBAS AS PLANILHAS                   │
│    • BCG: Produtos com vendas (01-26/12)       │
│    • template_estoque: Estoque atual           │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 3. ANÁLISE DE COBERTURA                        │
│    Produto A: 120 un estoque / 4 un/dia = 30d  │
│    Produto B: 10 un estoque / 5 un/dia = 2d ⚠️ │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 4. DETECÇÃO DE FALTANTES                       │
│    Produto X: Está em BCG, NÃO em estoque      │
│    Produto Y: Está em BCG, NÃO em estoque      │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 5. GERA EXCEL PARA UPLOAD                      │
│    codigo | nome | categoria | estoque_atual   │
│    X      | ...  | ...       | 0               │
│    Y      | ...  | ...       | 0               │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│ 6. USUÁRIO BAIXA E FAZ UPLOAD MANUAL           │
│    (Não automático, como solicitado)           │
└─────────────────────────────────────────────────┘
```

---

## ⚡ OTIMIZAÇÃO DE CRÉDITOS

### Estratégias Aplicadas

1. **Cache Agressivo**
```python
@st.cache_data(ttl=600)  # 10 minutos
def carregar_estoque_template():
    # Evita leituras repetidas
```

2. **Leitura Única**
```python
# ❌ NÃO fazer múltiplas requests
# ✅ Ler uma vez e processar local
```

3. **Processamento Local**
```python
# ❌ NÃO usar APIs pagas para cálculos simples
# ✅ Pandas/Numpy local (gratuito)
```

4. **Exports Diretos**
```python
# ❌ NÃO criar múltiplos arquivos temporários
# ✅ Gerar Excel em memória (BytesIO)
```

---

## 📅 CRONOGRAMA

### Fase 1: Fundação (2-3h)
- [x] Análise de estruturas
- [ ] Criar `inventory_integration.py`
- [ ] Criar `rupture_analysis.py`
- [ ] Testes unitários

### Fase 2: Integração (2-3h)
- [ ] Atualizar `app.py` com nova aba
- [ ] Implementar leitura de estoque
- [ ] Implementar análise de ruptura
- [ ] Normalização automática

### Fase 3: Exportação (1-2h)
- [ ] Gerar Excel para upload
- [ ] Detectar produtos faltantes
- [ ] Botão de download

### Fase 4: Testes (1-2h)
- [ ] Testar com dados reais (01-26/12)
- [ ] Validar produtos faltantes
- [ ] Verificar formatação Excel
- [ ] Documentação de uso

**TOTAL ESTIMADO**: 6-10 horas

---

## ✅ CRITÉRIOS DE SUCESSO

1. ✅ App mostra estoque atual sem erros
2. ✅ Análise de ruptura com dados reais (01-26/12)
3. ✅ Detecta produtos BCG não presentes em estoque
4. ✅ Gera Excel formatado corretamente para upload
5. ✅ Normaliza separadores automaticamente
6. ✅ Sem quebrar funcionalidades existentes
7. ✅ Commits incrementais documentados

---

## 🚀 PRÓXIMO PASSO IMEDIATO

Começar implementação de `inventory_integration.py`

**AGUARDANDO SUA CONFIRMAÇÃO PARA INICIAR! 👍**
