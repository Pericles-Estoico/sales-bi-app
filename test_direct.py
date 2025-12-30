import pandas as pd
import requests

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

print("=" * 80)
print("🧪 TESTE DIRETO DE ACESSO ÀS PLANILHAS")
print("=" * 80)

gids = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'detalhes': 961459380,
}

for nome, gid in gids.items():
    url = f"{BASE_URL}&gid={gid}"
    print(f"\n🔍 Testando {nome} (gid={gid})...")
    print(f"   URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            # Tentar ler como CSV
            df = pd.read_csv(url)
            print(f"   ✅ SUCESSO! {len(df)} linhas, {len(df.columns)} colunas")
            print(f"   Colunas: {list(df.columns[:5])}")
            print(f"   Primeira linha: {df.iloc[0].to_dict()}")
        else:
            print(f"   ❌ ERRO HTTP {response.status_code}")
            print(f"   Response: {response.text[:200]}")
    
    except Exception as e:
        print(f"   ❌ EXCEÇÃO: {e}")

print("\n" + "=" * 80)
