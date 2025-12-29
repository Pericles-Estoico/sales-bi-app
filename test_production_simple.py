"""
Teste simplificado - apenas importação direta.
"""

import pandas as pd

print("=" * 80)
print("🧪 TESTE SIMPLIFICADO - VERIFICAÇÃO DE ESTRUTURA")
print("=" * 80)

# Carregar dados base
print("\n📦 Carregando dados base...")

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

df_produtos = pd.read_csv(f"{BASE_URL}&gid=1037607798")
print(f"✅ Produtos carregados: {len(df_produtos)}")
print(f"   Colunas: {list(df_produtos.columns)}")

df_kits = pd.read_csv(f"{BASE_URL}&gid=1569485799")
print(f"\n✅ Kits carregados: {len(df_kits)}")
print(f"   Colunas: {list(df_kits.columns)}")

# Exemplo de decomposição de kit
print("\n" + "=" * 80)
print("🔬 TESTE DE DECOMPOSIÇÃO DE KIT")
print("=" * 80)

primeiro_kit = df_kits.iloc[0]
print(f"\n📦 KIT: {primeiro_kit['Código Kit']}")
print(f"🧩 SKUs: {primeiro_kit['SKUs Componentes']}")
print(f"🔢 Qtds: {primeiro_kit['Qtd Componentes']}")

# Decompor
skus = str(primeiro_kit['SKUs Componentes']).split(';')
qtds = str(primeiro_kit['Qtd Componentes']).split(';')

print(f"\n✅ Decomposição:")
for sku, qtd in zip(skus, qtds):
    print(f"   - {sku.strip()} × {qtd.strip()}")

# Carregar vendas exemplo
print("\n" + "=" * 80)
print("📤 CARREGAR VENDAS EXEMPLO")
print("=" * 80)

df_vendas = pd.read_excel('/home/user/uploaded_files/exemplo de vendas.xlsx')
print(f"\n✅ Vendas carregadas: {len(df_vendas)}")
print(f"   Colunas: {list(df_vendas.columns)}")
print(f"   Total unidades: {df_vendas['quantidade'].sum()}")

print(f"\n📋 Primeiros 10 produtos:")
print(df_vendas.head(10).to_string(index=False))

# Verificar se algum é kit
print("\n" + "=" * 80)
print("🔍 VERIFICAR KITS NAS VENDAS")
print("=" * 80)

kits_vendidos = 0
produtos_vendidos = 0

for codigo in df_vendas['código']:
    if codigo in df_kits['Código Kit'].values:
        kits_vendidos += 1
    else:
        produtos_vendidos += 1

print(f"\n✅ Análise:")
print(f"   Kits vendidos: {kits_vendidos}")
print(f"   Produtos vendidos: {produtos_vendidos}")

print("\n" + "=" * 80)
print("✅ TESTE DE ESTRUTURA COMPLETO!")
print("=" * 80)
