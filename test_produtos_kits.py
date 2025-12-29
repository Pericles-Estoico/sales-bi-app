import pandas as pd
import requests

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

# PRODUTOS - itens que vendemos
print("=" * 80)
print("📦 ABA PRODUTOS - ITENS QUE VENDEMOS")
print("=" * 80)

url_produtos = f"{BASE_URL}&gid=1037607798"
df_produtos = pd.read_csv(url_produtos)

print(f"\n✅ Total de produtos: {len(df_produtos)}")
print(f"\n📋 Colunas encontradas: {list(df_produtos.columns)}")
print(f"\n🔍 Primeiros 15 produtos:")
print(df_produtos.head(15).to_string(index=False))

# KITS - agrupamento de produtos separados por ;
print("\n" + "=" * 80)
print("🎁 ABA KITS - AGRUPAMENTO DE PRODUTOS (SEPARADOS POR ;)")
print("=" * 80)

url_kits = f"{BASE_URL}&gid=1569485799"
df_kits = pd.read_csv(url_kits)

print(f"\n✅ Total de kits: {len(df_kits)}")
print(f"\n📋 Colunas encontradas: {list(df_kits.columns)}")
print(f"\n🔍 Primeiros 10 kits:")
print(df_kits.head(10).to_string(index=False))

# Exemplo de decomposição de um KIT
print("\n" + "=" * 80)
print("🔬 EXEMPLO DE DECOMPOSIÇÃO DE KIT")
print("=" * 80)

# Pegar o primeiro kit válido
primeiro_kit = df_kits.iloc[0]
print(f"\n📦 KIT: {primeiro_kit.iloc[0]}")
print(f"🧩 SKUs Componentes: {primeiro_kit.iloc[1]}")
print(f"🔢 Quantidades: {primeiro_kit.iloc[2]}")
print(f"💰 Preço Venda: {primeiro_kit.iloc[3]}")

# Decompor
skus = str(primeiro_kit.iloc[1]).split(';')
qtds = str(primeiro_kit.iloc[2]).split(';')

print(f"\n🔧 DECOMPOSIÇÃO:")
for i, (sku, qtd) in enumerate(zip(skus, qtds), 1):
    print(f"  {i}. SKU: {sku.strip()} → Quantidade: {qtd.strip()}")

# Estatísticas
print("\n" + "=" * 80)
print("📊 ESTATÍSTICAS")
print("=" * 80)
print(f"Total de PRODUTOS (itens individuais): {len(df_produtos)}")
print(f"Total de KITS (agrupamentos): {len(df_kits)}")
print(f"Total geral: {len(df_produtos) + len(df_kits)}")
