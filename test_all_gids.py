import pandas as pd
import requests

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

GIDS = {
    'produtos': 1037607798,
    'kits': 1569485799,
    'dashboard': 749174572,
    'detalhes': 961459380,
    'cnpj': 1218055125,
    'bcg': 1589145111,
    'precos': 1141986740,
    'giro': 364031804,
    'oportunidades': 563501913,
}

print("=" * 80)
print("🧪 TESTE DE TODOS OS GIDS")
print("=" * 80)

funcionando = []
com_erro = []

for nome, gid in GIDS.items():
    url = f"{BASE_URL}&gid={gid}"
    print(f"\n🔍 {nome} (gid={gid})...")
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            df = pd.read_csv(url)
            print(f"   ✅ OK - {len(df)} linhas, colunas: {list(df.columns[:3])}")
            funcionando.append(nome)
        else:
            print(f"   ❌ HTTP {response.status_code}")
            com_erro.append(nome)
    except Exception as e:
        print(f"   ❌ ERRO: {e}")
        com_erro.append(nome)

print("\n" + "=" * 80)
print("📊 RESUMO:")
print(f"✅ Funcionando ({len(funcionando)}): {', '.join(funcionando)}")
print(f"❌ Com erro ({len(com_erro)}): {', '.join(com_erro)}")
print("=" * 80)
