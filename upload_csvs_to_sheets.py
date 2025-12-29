#!/usr/bin/env python3
"""
Script para fazer upload dos CSVs para Google Sheets
Cria novas abas SIMPLES (sem fórmulas) com os dados dos CSVs

REQUISITOS:
    pip install gspread oauth2client pandas

USO:
    python upload_csvs_to_sheets.py
"""

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import os
import sys

# ID da planilha Config_BI_Final_MatrizBCG
SPREADSHEET_ID = "1qoUk6AsNXLpHyzRrZplM4F5573zN9hUwQTNVUF3UC8E"

# Mapeamento: arquivo CSV -> nome da nova aba
CSV_TO_SHEET_MAPPING = {
    "Config_BI_Final_MatrizBCG - 2. Análise por CNPJ.csv": "CNPJ_SIMPLES",
    "Config_BI_Final_MatrizBCG - 3. Análise Executiva.csv": "EXECUTIVA_SIMPLES",
    "Config_BI_Final_MatrizBCG - 4. Preços Marketplaces.csv": "PRECOS_SIMPLES",
    "Config_BI_Final_MatrizBCG - 5. Matriz BCG.csv": "BCG_SIMPLES",
    "Config_BI_Final_MatrizBCG - 7. Giro de Produtos.csv": "GIRO_SIMPLES",
    "Config_BI_Final_MatrizBCG - 8. Oportunidades.csv": "OPORTUNIDADES_SIMPLES",
}


def upload_csv_to_sheet(csv_path, sheet_name, spreadsheet):
    """Faz upload de um CSV para uma nova aba no Google Sheets"""
    
    print(f"\n📤 Fazendo upload: {os.path.basename(csv_path)} → {sheet_name}")
    
    # Lê o CSV
    try:
        df = pd.read_csv(csv_path)
        print(f"   ✅ CSV lido: {len(df)} linhas, {len(df.columns)} colunas")
    except Exception as e:
        print(f"   ❌ Erro ao ler CSV: {e}")
        return None
    
    # Verifica se a aba já existe
    try:
        worksheet = spreadsheet.worksheet(sheet_name)
        print(f"   ⚠️  Aba '{sheet_name}' já existe. Limpando...")
        worksheet.clear()
    except gspread.exceptions.WorksheetNotFound:
        print(f"   ➕ Criando nova aba: {sheet_name}")
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=20)
    
    # Converte DataFrame para lista de listas
    data = [df.columns.tolist()] + df.values.tolist()
    
    # Faz upload
    try:
        worksheet.update(data, 'A1')
        print(f"   ✅ Upload concluído! {len(data)} linhas enviadas")
        
        # Pega o GID da aba
        gid = worksheet.id
        print(f"   🔑 GID da aba: {gid}")
        
        return gid
        
    except Exception as e:
        print(f"   ❌ Erro ao fazer upload: {e}")
        return None


def main():
    """Função principal"""
    
    print("="*80)
    print("🚀 UPLOAD DE CSVs PARA GOOGLE SHEETS")
    print("="*80)
    
    # Diretório com os CSVs
    csv_dir = "/home/user/uploaded_files"
    
    # Verifica se tem credenciais
    creds_path = os.path.expanduser("~/.config/gspread/service_account.json")
    
    if not os.path.exists(creds_path):
        print("\n❌ ERRO: Arquivo de credenciais não encontrado!")
        print(f"   Esperado em: {creds_path}")
        print("\n📋 PARA CONFIGURAR:")
        print("   1. Vá em: https://console.cloud.google.com/")
        print("   2. Crie uma Service Account")
        print("   3. Baixe o JSON e salve em:")
        print(f"      {creds_path}")
        print("\n💡 OU use a OPÇÃO MANUAL (veja README)")
        return
    
    # Conecta no Google Sheets
    try:
        print(f"\n🔐 Carregando credenciais de: {creds_path}")
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        
        print(f"✅ Autenticado com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro ao autenticar: {e}")
        return
    
    # Abre a planilha
    try:
        print(f"\n📊 Abrindo planilha: {SPREADSHEET_ID}")
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        print(f"✅ Planilha aberta: {spreadsheet.title}")
        
    except Exception as e:
        print(f"❌ Erro ao abrir planilha: {e}")
        return
    
    # Faz upload de cada CSV
    gids = {}
    
    for csv_filename, sheet_name in CSV_TO_SHEET_MAPPING.items():
        csv_path = os.path.join(csv_dir, csv_filename)
        
        if not os.path.exists(csv_path):
            print(f"\n⚠️  AVISO: Arquivo não encontrado: {csv_filename}")
            continue
        
        gid = upload_csv_to_sheet(csv_path, sheet_name, spreadsheet)
        
        if gid:
            gids[sheet_name] = gid
    
    # Mostra resumo
    print("\n" + "="*80)
    print("📋 RESUMO DOS GIDs")
    print("="*80)
    
    for sheet_name, gid in gids.items():
        print(f"  {sheet_name.ljust(25)} → gid={gid}")
    
    print("\n" + "="*80)
    print(f"✅ CONCLUÍDO! {len(gids)} abas criadas/atualizadas")
    print("="*80)
    
    # Gera código Python para atualizar app.py
    print("\n📝 CÓDIGO PARA ATUALIZAR app.py:")
    print("-"*80)
    print("URLS = {")
    
    mapping = {
        'CNPJ_SIMPLES': 'cnpj',
        'EXECUTIVA_SIMPLES': 'executiva',
        'PRECOS_SIMPLES': 'precos',
        'BCG_SIMPLES': 'bcg',
        'GIRO_SIMPLES': 'giro',
        'OPORTUNIDADES_SIMPLES': 'oportunidades'
    }
    
    for sheet_name, gid in gids.items():
        key = mapping.get(sheet_name, sheet_name.lower())
        print(f"    '{key}': f\"{{BASE_URL}}&gid={gid}\",  # {sheet_name}")
    
    print("}")
    print("-"*80)


if __name__ == "__main__":
    main()
