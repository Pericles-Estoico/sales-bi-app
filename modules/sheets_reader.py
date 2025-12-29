"""
Módulo para leitura de dados do Google Sheets
Suporta dois métodos:
1. Google Sheets API (gspread) - preferencial, lê valores calculados em tempo real
2. CSV Export - fallback, só funciona com abas sem fórmulas complexas
"""

import pandas as pd
import streamlit as st
import requests
from io import StringIO
import gspread
from oauth2client.service_account import ServiceAccountCredentials


class SheetsReader:
    """Leitor inteligente de Google Sheets com fallback"""
    
    def __init__(self, spreadsheet_id):
        self.spreadsheet_id = spreadsheet_id
        self.client = None
        self.spreadsheet = None
        self.use_api = False
        
        # Tenta inicializar Google Sheets API
        self._init_api()
    
    def _init_api(self):
        """Inicializa conexão com Google Sheets API se credenciais estiverem disponíveis"""
        try:
            # Tenta pegar credenciais do Streamlit Secrets
            if hasattr(st, 'secrets') and 'google_sheets' in st.secrets:
                credentials_dict = dict(st.secrets['google_sheets'])
                
                # Remove spreadsheet_id se estiver nas credenciais
                credentials_dict.pop('spreadsheet_id', None)
                
                scope = [
                    'https://spreadsheets.google.com/feeds',
                    'https://www.googleapis.com/auth/drive'
                ]
                
                credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                    credentials_dict, 
                    scope
                )
                
                self.client = gspread.authorize(credentials)
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
                self.use_api = True
                
        except Exception as e:
            self.use_api = False
    
    def read_sheet_by_gid(self, gid, sheet_name=None):
        """
        Lê uma aba do Google Sheets pelo GID
        
        Args:
            gid: ID da aba (número)
            sheet_name: Nome da aba (opcional, usado para API)
        
        Returns:
            pandas.DataFrame
        """
        
        # Método 1: Tentar Google Sheets API (se disponível)
        if self.use_api and sheet_name:
            try:
                df = self._read_via_api(sheet_name)
                if not df.empty:
                    return df
            except Exception:
                pass  # Silenciar erro e tentar CSV
        
        # Método 2: Fallback para CSV export
        return self._read_via_csv_export(gid)
    
    def _read_via_api(self, sheet_name):
        """Lê dados via Google Sheets API (valores calculados em tempo real)"""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            
            # Pega todos os valores (já calculados!)
            data = worksheet.get_all_values()
            
            if not data:
                return pd.DataFrame()
            
            # Cria DataFrame
            df = pd.DataFrame(data[1:], columns=data[0])
            
            return df
            
        except Exception:
            return pd.DataFrame()
    
    def _read_via_csv_export(self, gid):
        """Lê dados via CSV export (fallback)"""
        try:
            url = f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/export?format=csv&gid={gid}"
            
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            
            # Verifica se não é página de erro HTML
            if response.text.startswith('<!DOCTYPE'):
                return pd.DataFrame()
            
            df = pd.read_csv(StringIO(response.text))
            
            return df
            
        except Exception:
            return pd.DataFrame()
    
    def get_status(self):
        """Retorna status da conexão"""
        if self.use_api:
            return {
                'method': 'Google Sheets API',
                'status': '✅ Dados em tempo real',
                'realtime': True
            }
        else:
            return {
                'method': 'CSV Export',
                'status': '⚠️  Fallback (algumas abas podem não funcionar)',
                'realtime': False
            }
