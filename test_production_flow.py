"""
Teste completo do fluxo de relatório de produção.
"""

import pandas as pd
import sys
sys.path.append('.')

from modules.production_analyzer import ProductionAnalyzer
from modules.production_report_generator import ProductionReportGenerator

print("=" * 80)
print("🧪 TESTE DO FLUXO DE RELATÓRIO DE PRODUÇÃO")
print("=" * 80)

# Inicializar
analyzer = ProductionAnalyzer()
report_gen = ProductionReportGenerator()

# Carregar dados base
print("\n📦 Carregando dados base...")

BASE_URL = "https://docs.google.com/spreadsheets/d/1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E/export?format=csv"

df_produtos = pd.read_csv(f"{BASE_URL}&gid=1037607798")
print(f"✅ Produtos carregados: {len(df_produtos)}")

df_kits = pd.read_csv(f"{BASE_URL}&gid=1569485799")
print(f"✅ Kits carregados: {len(df_kits)}")

TEMPLATE_ESTOQUE_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv&gid=0"
df_estoque = pd.read_csv(TEMPLATE_ESTOQUE_URL)
print(f"✅ Estoque carregado: {len(df_estoque)}")

# Configurar analyzer
analyzer.load_produtos(df_produtos)
analyzer.load_kits(df_kits)
analyzer.load_estoque(df_estoque)

# Resetar análise
analyzer.reset_daily_analysis("2025-12-29")

print("\n" + "=" * 80)
print("📤 SIMULANDO UPLOAD 1: MERCADO LIVRE")
print("=" * 80)

# Carregar vendas exemplo
df_vendas_ml = pd.read_excel('/home/user/uploaded_files/exemplo de vendas.xlsx')
print(f"\n📋 Vendas Mercado Livre:")
print(f"   Total SKUs: {len(df_vendas_ml)}")
print(f"   Total Unidades: {df_vendas_ml['quantidade'].sum()}")

# Processar vendas
needs_ml = analyzer.analyze_sales(df_vendas_ml, "Mercado Livre")
needs_ml = analyzer.check_inventory(needs_ml)

print(f"\n✅ Processado!")
print(f"   Produtos analisados: {len(needs_ml)}")
faltantes_ml = sum(1 for n in needs_ml.values() if n.quantidade_faltante > 0)
print(f"   Produtos faltantes: {faltantes_ml}")
total_faltante_ml = sum(n.quantidade_faltante for n in needs_ml.values())
print(f"   Total unidades a produzir: {total_faltante_ml}")

# Simular upload 2: Shopee (com alguns produtos em comum)
print("\n" + "=" * 80)
print("📤 SIMULANDO UPLOAD 2: SHOPEE 1:50 (com produtos em comum)")
print("=" * 80)

# Pegar alguns produtos do ML e adicionar quantidades
df_vendas_shopee = df_vendas_ml.head(20).copy()
df_vendas_shopee['quantidade'] = df_vendas_shopee['quantidade'] * 2  # Dobrar quantidades

print(f"\n📋 Vendas Shopee 1:50:")
print(f"   Total SKUs: {len(df_vendas_shopee)}")
print(f"   Total Unidades: {df_vendas_shopee['quantidade'].sum()}")

# Processar vendas (deve ACUMULAR)
needs_shopee = analyzer.analyze_sales(df_vendas_shopee, "Shopee 1:50")
needs_shopee = analyzer.check_inventory(needs_shopee)

print(f"\n✅ Processado!")
print(f"   Produtos TOTAIS analisados: {len(needs_shopee)}")
faltantes_total = sum(1 for n in needs_shopee.values() if n.quantidade_faltante > 0)
print(f"   Produtos faltantes (acumulado): {faltantes_total}")
total_faltante_acum = sum(n.quantidade_faltante for n in needs_shopee.values())
print(f"   Total unidades a produzir (acumulado): {total_faltante_acum}")

# Verificar acumulação
print("\n" + "=" * 80)
print("🔍 VERIFICAÇÃO DE ACUMULAÇÃO")
print("=" * 80)

# Pegar um produto que aparece nos dois
codigo_exemplo = df_vendas_ml.iloc[0]['código']
if codigo_exemplo in needs_shopee:
    need = needs_shopee[codigo_exemplo]
    print(f"\n📦 Produto exemplo: {codigo_exemplo}")
    print(f"   Quantidade necessária TOTAL: {need.quantidade_necessaria}")
    print(f"   Estoque atual: {need.estoque_atual}")
    print(f"   Quantidade faltante: {need.quantidade_faltante}")
    print(f"   Marketplaces: {', '.join(need.origem_marketplaces)}")
    print(f"   ✅ Acumulação OK!" if len(need.origem_marketplaces) == 2 else "   ❌ Acumulação FALHOU!")

# Gerar relatórios
print("\n" + "=" * 80)
print("📊 GERANDO RELATÓRIOS")
print("=" * 80)

# Relatório por marketplace
print("\n📄 Relatório Mercado Livre...")
excel_ml = report_gen.generate_marketplace_report(
    "Mercado Livre", 
    "2025-12-29", 
    needs_shopee
)
print(f"✅ Gerado: {len(excel_ml.getvalue())} bytes")

# Relatório consolidado
print("\n📄 Relatório Consolidado...")
excel_consolidado = report_gen.generate_daily_consolidated_report(
    "2025-12-29",
    needs_shopee,
    ["Mercado Livre", "Shopee 1:50"]
)
print(f"✅ Gerado: {len(excel_consolidado.getvalue())} bytes")

# Resumo DataFrame
print("\n📊 DataFrame de Resumo:")
df_resumo = report_gen.generate_summary_dataframe(needs_shopee)
print(f"\nTop 10 produtos faltantes:")
print(df_resumo.nlargest(10, '🚨 Faltante')[['Código', 'Qtd Necessária', 'Estoque Atual', '🚨 Faltante', 'Marketplaces']].to_string(index=False))

print("\n" + "=" * 80)
print("✅ TESTE COMPLETO CONCLUÍDO COM SUCESSO!")
print("=" * 80)
