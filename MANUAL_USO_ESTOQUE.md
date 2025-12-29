# 📦 Manual de Uso - Gestão de Estoque

**Versão**: 1.0  
**Data**: 29/12/2024  
**App**: Sales BI Pro

---

## 🎯 Visão Geral

A nova aba **"📦 Gestão de Estoque"** integra dados de vendas (planilha BCG) com dados de estoque (planilha template_estoque) para fornecer insights inteligentes sobre:

✅ **Cobertura de estoque** (quantos dias seu estoque vai durar)  
✅ **Alertas de ruptura** (produtos prestes a acabar)  
✅ **Produtos faltantes** (que existem na BCG mas não no estoque)  
✅ **Sugestões de reposição** (quanto comprar e investir)

---

## 📋 Como Usar

### 1️⃣ Acessar a Aba

1. Abra o app: https://salesholdingsilvabi.streamlit.app/
2. Clique na aba **"📦 Gestão de Estoque"** (última aba)
3. Aguarde o carregamento dos dados (10-15 segundos)

---

### 2️⃣ Visão Geral do Estoque

**O que você vê:**

```
┌─────────────────────────────────────────────┐
│ Total de Produtos │ Com Estoque │ Abaixo │ Valor │
│       250         │     180     │   45   │ R$ XX │
└─────────────────────────────────────────────┘
```

**O que significa:**
- **Total de Produtos**: Quantos produtos estão cadastrados no estoque
- **Com Estoque**: Quantos têm estoque disponível (> 0)
- **Abaixo do Mínimo**: Quantos estão abaixo do estoque mínimo configurado
- **Valor em Estoque**: Valor total investido em estoque (custo × quantidade)

---

### 3️⃣ Análise de Ruptura

#### Como Funciona

O sistema calcula automaticamente:

```
Dias de Cobertura = Estoque Atual ÷ Média de Vendas por Dia
```

**Exemplo:**
- Produto: Body Rendado Branco ML-P
- Estoque atual: 120 unidades
- Média de vendas: 4 unidades/dia
- **Dias de cobertura: 30 dias** ✅

#### Níveis de Alerta

| Alerta | Dias | O que fazer |
|--------|------|-------------|
| 🔴 **Crítico** | < 3 dias | 🚨 COMPRAR URGENTE! |
| 🟡 **Atenção** | 3-7 dias | ⚠️ Programar reposição |
| 🟢 **OK** | > 7 dias | ✅ Estoque saudável |
| ⚪ **Sem Vendas** | - | 💡 Produto parado |

#### Filtrar Produtos

Use os filtros para ver apenas o que interessa:

```
Filtrar por status:
☑️ 🔴 Crítico
☑️ 🟡 Atenção
☐ 🟢 OK
☐ ⚪ Sem Vendas
```

**Dica**: Deixe marcado apenas Crítico e Atenção para focar nos produtos que precisam de ação!

---

### 4️⃣ Previsão de Rupturas (30 dias)

**O que mostra:**
- Quais produtos vão acabar nos próximos 30 dias
- Quando cada um vai acabar (data prevista)
- Quanto você precisa comprar para 30 dias
- Quanto vai custar

**Exemplo de tabela:**

| Produto | Estoque | Dias | Ruptura em | Comprar | Investir |
|---------|---------|------|------------|---------|----------|
| Body ML-P | 20 un | 5 dias | 03/01/2025 | 120 un | R$ 867,00 |
| Body MC-M | 8 un | 2 dias | 31/12/2024 | 100 un | R$ 690,00 |

**Como usar:**
1. Ordene por "Dias de Cobertura" (menor → maior)
2. Veja a data prevista de ruptura
3. Use a coluna "Comprar" para fazer seu pedido
4. Use a coluna "Investir" para planejar o fluxo de caixa

---

### 5️⃣ Sincronização de Produtos

#### Problema que resolve

Você tem produtos cadastrados na **planilha BCG** (com vendas) mas que **NÃO estão no estoque**.

#### Como funciona

1. O sistema compara códigos de produtos entre as duas planilhas
2. Detecta automaticamente produtos faltantes
3. Gera um Excel formatado para você fazer upload manual

#### Passo a Passo

**1. Verifique produtos faltantes**

Se houver produtos faltantes, você verá:

```
⚠️ 15 produtos encontrados na BCG mas não no estoque
```

**2. Clique em "📥 Baixar Excel de Produtos Faltantes"**

O arquivo Excel terá este formato:

| codigo | nome | categoria | estoque_atual | estoque_min | estoque_max | custo_unitario | eh_kit | componentes | quantidades |
|--------|------|-----------|---------------|-------------|-------------|----------------|--------|-------------|-------------|
| 1001-Rendado-Branco-ML-RN | Produto 1001-... | Produtos BCG | 0 | 0 | 0 | 7.24 | | | |

**3. Abra a planilha template_estoque**

Link: https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o

**4. Copie e Cole os dados**

- Abra o Excel baixado
- Selecione todas as linhas de produtos
- Copie (Ctrl+C)
- Cole na planilha template_estoque (última linha vazia)

**5. Ajuste manualmente (se necessário)**

- Atualize o **nome** do produto (deixe mais descritivo)
- Configure **estoque_min** e **estoque_max** adequados
- Se for um kit, marque **eh_kit** = SIM e preencha componentes

✅ Pronto! Na próxima atualização do app, os produtos estarão sincronizados

---

### 6️⃣ Visualização Completa do Estoque

#### Filtros Disponíveis

**Por Categoria:**
```
☑️ Bodys Prontos
☑️ Produtos BCG
☑️ Insumos
```

**Por Status:**
```
○ Todos
● Com estoque
○ Sem estoque
○ Abaixo do mínimo
```

#### O que fazer

Use os filtros para:
- Ver apenas produtos com estoque baixo
- Verificar produtos sem estoque para dar baixa no marketplace
- Revisar categorias específicas
- Exportar dados (copiar tabela)

---

## 🎯 Fluxo de Trabalho Recomendado

### Diariamente (5 minutos)

1. Abra a aba **Gestão de Estoque**
2. Veja os **alertas críticos** (🔴)
3. Anote produtos para compra urgente
4. Comunique equipe de compras

### Semanalmente (15 minutos)

1. Revise **Previsão de Rupturas**
2. Faça pedidos de reposição
3. Verifique **produtos sem vendas** (⚪)
4. Considere ações para produtos parados

### Mensalmente (30 minutos)

1. Faça **sincronização de produtos**
2. Baixe Excel de faltantes
3. Atualize template_estoque
4. Revise estoque_min/max de todos os produtos
5. Analise tendências de vendas × estoque

---

## ⚙️ Configurações Importantes

### Planilha template_estoque

**Colunas obrigatórias:**
- `codigo`: Código único do produto (deve ser igual ao da BCG)
- `nome`: Nome descritivo
- `estoque_atual`: Quantidade em estoque (ATUALIZAR MANUALMENTE!)
- `estoque_min`: Nível mínimo (alerta)
- `estoque_max`: Nível máximo (meta)
- `custo_unitario`: Custo de aquisição

**Entrada e Saída de Estoque:**
- ⚠️ **SEMPRE MANUAL** pelo operador de estoque
- **NÃO** deixe o app alterar automaticamente
- Use o app apenas para **visualização e análise**

---

## 🐛 Soluções de Problemas

### "Erro ao carregar estoque"

**Causa**: Problema de conexão com a planilha  
**Solução**: 
1. Clique em "🔄 Atualizar Dados (Limpar Cache)" no sidebar
2. Aguarde 10 segundos e recarregue a página
3. Verifique se a planilha está compartilhada corretamente

### "Não há dados de vendas suficientes"

**Causa**: Aba "Detalhes" está vazia  
**Solução**:
1. Importe vendas via sidebar (upload de planilha)
2. Ou aguarde processamento de vendas do dia
3. Pelo menos 7 dias de vendas são recomendados

### "Produtos faltantes" sempre aparece

**Causa**: Códigos não correspondem entre planilhas  
**Solução**:
1. Baixe o Excel de faltantes
2. Faça upload na template_estoque
3. Aguarde 10 minutos para cache limpar
4. Atualize a página

### Separadores decimais errados

**NÃO É PROBLEMA!** ✅  
O sistema normaliza automaticamente:
- `7,24` → 7.24
- `14.9` → 14.9
- `1.234,56` → 1234.56

---

## 💡 Dicas Pro

### 1. Use Modo Sandbox para Testes

Ative **"🧪 MODO SIMULAÇÃO"** no sidebar para testar sem alterar dados reais.

### 2. Exporte Relatórios

Você pode:
- Copiar qualquer tabela (Ctrl+C)
- Colar no Excel/Google Sheets
- Criar seus próprios relatórios

### 3. Atalhos de Teclado

- `Ctrl + F`: Buscar na página
- `Ctrl + R`: Recarregar página
- `F5`: Atualizar dados

### 4. Monitore Valor em Estoque

O card **"Valor em Estoque"** mostra quanto capital está imobilizado. Use para:
- Planejar compras
- Negociar prazos com fornecedores
- Decidir promoções de produtos parados

---

## 📞 Suporte

**Dúvidas ou problemas?**

1. Verifique se seguiu todos os passos deste manual
2. Confira as "Soluções de Problemas" acima
3. Entre em contato com o desenvolvedor

**Desenvolvido por:** GenSpark AI Developer  
**Versão do App:** V56 (29/12/2024)

---

## 📝 Changelog

### V56 - 29/12/2024
- ✅ Integração com template_estoque
- ✅ Análise de ruptura com dias de cobertura
- ✅ Detecção de produtos faltantes
- ✅ Exportação de Excel formatado
- ✅ Previsão de rupturas (30 dias)
- ✅ Normalização automática de decimais
- ✅ Filtros avançados

---

**🎉 Aproveite a nova funcionalidade e otimize sua gestão de estoque!**
