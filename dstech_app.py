#!/usr/bin/env python3
"""
DSTech Dashboard - Aplicação Principal
Sistema completo de monitoramento industrial com dados reais
"""

import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
import psycopg2
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import hashlib
import json

# Importar módulos personalizados
from dstech_charts import *
from advanced_analytics import (
    create_client_comparison_dashboard, get_operational_insights, 
    create_trend_analysis_chart, create_smart_client_analysis
)
from advanced_analytics import get_client_performance_comparison as aa_get_client_performance_comparison

# Carregar variáveis de ambiente
load_dotenv('.env_dstech')

# Detectar ambiente (produção ou desenvolvimento)
IS_PRODUCTION = os.getenv('DEBUG', 'True').lower() == 'false'

# Configuração do banco PostgreSQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'dstech_dashboard'),
    'user': os.getenv('POSTGRES_USERNAME', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres123')
}

# ==== Alias de Clientes: helpers usando schema 'app' no Postgres espelho ====
def ensure_alias_table_and_migrate():
    """Cria schema app e tabela app.client_alias e migra dados antigos de 'clientes' se existirem."""
    try:
        conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        conn.autocommit = True
        cur = conn.cursor()
        # Criar schema app
        cur.execute("CREATE SCHEMA IF NOT EXISTS app")
        # Criar tabela app.client_alias
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app.client_alias (
                client_id INTEGER PRIMARY KEY,
                alias TEXT NOT NULL
            )
            """
        )
        # Migrar dados da tabela antiga 'clientes' se existir
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'clientes' AND table_schema = 'public'
            )
        """)
        exists_old = cur.fetchone()[0]
        if exists_old:
            # Inserir os que não existem ainda
            cur.execute(
                """
                INSERT INTO app.client_alias (client_id, alias)
                SELECT c.client_id, c.client_name
                FROM public.clientes c
                ON CONFLICT (client_id) DO NOTHING
                """
            )
        cur.close(); conn.close()
    except Exception as e:
        print(f"❌ Erro ao garantir/migrar tabela de alias: {e}")

def get_client_mappings():
    """Busca aliases atuais (client_id → alias) em app.client_alias."""
    try:
        conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        cur = conn.cursor()
        cur.execute("SELECT client_id, alias FROM app.client_alias ORDER BY client_id ASC")
        rows = cur.fetchall()
        cur.close(); conn.close()
        return rows
    except Exception as e:
        print(f"❌ Erro ao carregar aliases: {e}")
        return []

def upsert_client_mapping(client_id: int, alias: str):
    """Insere ou atualiza alias do cliente em app.client_alias."""
    try:
        conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO app.client_alias (client_id, alias)
            VALUES (%s, %s)
            ON CONFLICT (client_id) DO UPDATE SET alias = EXCLUDED.alias
            """,
            (client_id, alias)
        )
        cur.close(); conn.close()
        return True, "Alias salvo com sucesso"
    except Exception as e:
        print(f"❌ Erro ao salvar alias: {e}")
        return False, str(e)

# Garantir tabela/exec migracao na inicialização
ensure_alias_table_and_migrate()

def get_client_catalog():
    """Lista IDs de cliente existentes nas cargas e alias (se houver)."""
    try:
        conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT CAST(rc."C1" AS INTEGER) AS client_id
            FROM "Rel_Carga" rc
            WHERE rc."C1" IS NOT NULL
            ORDER BY client_id ASC
            """
        )
        ids = [r[0] for r in cur.fetchall()]
        # Buscar aliases (app.client_alias)
        cur.execute("SELECT client_id, alias FROM app.client_alias")
        alias_map = {cid: name for cid, name in cur.fetchall()}
        cur.close(); conn.close()
        return [(cid, alias_map.get(cid)) for cid in ids]
    except Exception as e:
        print(f"❌ Erro ao listar IDs de clientes: {e}")
        return []

# Sistema de usuários simples com arquivo JSON
USERS_FILE = 'users.json'

def load_users():
    """Carrega usuários do arquivo JSON"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        else:
            # Usuários padrão
            default_users = {
                'admin': {
                    'password': hashlib.md5('admin123'.encode()).hexdigest(),
                    'role': 'admin',
                    'created': datetime.now().isoformat()
                },
                'operador': {
                    'password': hashlib.md5('operador123'.encode()).hexdigest(),
                    'role': 'operator',
                    'created': datetime.now().isoformat()
                },
                'supervisor': {
                    'password': hashlib.md5('supervisor123'.encode()).hexdigest(),
                    'role': 'supervisor',
                    'created': datetime.now().isoformat()
                }
            }
            save_users(default_users)
            return default_users
    except Exception as e:
        print(f"Erro ao carregar usuários: {e}")
        return {}

def save_users(users):
    """Salva usuários no arquivo JSON"""
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        print(f"Erro ao salvar usuários: {e}")

def add_user(username, password, role='operator'):
    """Adiciona novo usuário"""
    users = load_users()
    if username in users:
        return False, "Usuário já existe"
    
    users[username] = {
        'password': hashlib.md5(password.encode()).hexdigest(),
        'role': role,
        'created': datetime.now().isoformat()
    }
    save_users(users)
    return True, "Usuário criado com sucesso"

def validate_user(username, password):
    """Valida credenciais do usuário"""
    users = load_users()
    if username in users:
        hashed_password = hashlib.md5(password.encode()).hexdigest()
        return users[username]['password'] == hashed_password
    return False

def validate_login(username, password):
    """Valida credenciais de login"""
    return validate_user(username, password)

# Carregar usuários na inicialização
USERS = load_users()

def generate_executive_report(start_date=None, end_date=None):
    """Gera relatório executivo dinâmico baseado no período selecionado"""
    if start_date is None:
        start_date = datetime.now() - timedelta(days=7)
    if end_date is None:
        end_date = datetime.now()

    # Converter strings para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))

    # Normalizar para limites inclusivo/inclusivo via end_exclusive
    start_dt = start_date
    end_dt = end_date
    end_exclusive = end_dt + timedelta(days=1)

    # Consultas reais
    try:
        # Produção usando Rel_Diario (C4) para consistência com dashboard
        # Água e ciclos mantidos de Sts_Dados
        prod_query = """
            SELECT 
                COALESCE(SUM("C4"), 0) AS total_kg
            FROM "Rel_Diario"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
        """
        
        cycles_water_query = """
            SELECT 
                COALESCE(SUM("D2"), 0) AS total_cycles,
                COALESCE(SUM("D1") * 1000, 0) AS total_water_liters
            FROM "Sts_Dados"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
        """
        
        prod_df = db.execute_query(prod_query, (start_dt, end_exclusive))
        cycles_water_df = db.execute_query(cycles_water_query, (start_dt, end_exclusive))

        total_kg = float(prod_df.iloc[0]['total_kg']) if not prod_df.empty else 0.0
        total_cycles = int(cycles_water_df.iloc[0]['total_cycles']) if not cycles_water_df.empty else 0
        total_water_liters = float(cycles_water_df.iloc[0]['total_water_liters']) if not cycles_water_df.empty else 0.0

        # Agora usando Rel_Diario (C4) para produção no relatório, mantendo consistência com dashboard

        # Químicos do período (somatório de Q1..Q5, ajuste conforme seus campos)
        chem_query = """
            SELECT 
                COALESCE(SUM(COALESCE("Q1",0) + COALESCE("Q2",0) + COALESCE("Q3",0) + COALESCE("Q4",0) + COALESCE("Q5",0)), 0) AS total_chemicals
            FROM "Rel_Quimico"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
        """
        chem_df = db.execute_query(chem_query, (start_dt, end_exclusive))
        total_chemicals = float(chem_df.iloc[0]['total_chemicals']) if not chem_df.empty else 0.0

        # Alarmes do período e ativos (otimizado)
        alarms_period_query = """
            SELECT COUNT(*) AS period_alarms
            FROM "ALARMHISTORY"
            WHERE "Al_Start_Time" >= %s AND "Al_Start_Time" < %s
        """
        alarms_active_query = """
            SELECT COUNT(*) AS active_alarms
            FROM "ALARMHISTORY"
            WHERE "Al_Norm_Time" IS NULL 
              AND "Al_Start_Time" >= CURRENT_DATE
        """
        alarms_period_df = db.execute_query(alarms_period_query, (start_dt, end_exclusive))
        alarms_active_df = db.execute_query(alarms_active_query)
        period_alarms = int(alarms_period_df.iloc[0]['period_alarms']) if not alarms_period_df.empty else 0
        active_alarms = int(alarms_active_df.iloc[0]['active_alarms']) if not alarms_active_df.empty else 0

        # Cálculos solicitados
        peso_medio = round((total_kg / total_cycles), 2) if total_cycles > 0 else 0.0
        agua_por_kg = round((total_water_liters / total_kg), 2) if total_kg > 0 else 0.0
        chemicals_per_kg = round((total_chemicals / total_kg), 4) if total_kg > 0 else 0.0

        # Média diária de produção
        days_diff = (end_dt.date() - start_dt.date()).days + 1
        daily_avg = round(total_kg / days_diff, 0) if days_diff > 0 else 0

        # Placeholders onde não há especificação
        efficiency_label = "—"  # sem fórmula especificada aqui
        critical_high = "—"
        avg_resolution = "—"

        return {
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'period_days': days_diff,
            'production_summary': {
                'period_production': f"{total_kg:,.0f}",
                'period_cycles': total_cycles,
                'daily_avg': f"{daily_avg:,.0f}",
                'efficiency': efficiency_label,
                'avg_weight': f"{peso_medio:,.2f} kg"  # informação extra útil
            },
            'consumption_summary': {
                'water_period': f"{total_water_liters:,.0f}",
                'water_per_kg': f"{agua_por_kg:.2f} L/kg",
                'chemicals_period': f"{total_chemicals:,.2f}",
                'chemicals_per_kg': f"{chemicals_per_kg:.4f} kg/kg"
            },
            'alarms_summary': {
                'avg_resolution': "—"
            },
            'recommendations': []
        }
    
    except Exception as e:
        print(f"Erro ao gerar relatório executivo: {e}")
        return {
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'period_days': 0,
            'production_summary': {
                'period_production': "0",
                'period_cycles': 0,
                'daily_avg': "0",
                'efficiency': "—",
                'avg_weight': "0 kg"
            },
            'consumption_summary': {
                'water_period': "0",
                'water_per_kg': "0 L/kg",
                'chemicals_period': "0",
                'chemicals_per_kg': "0 kg/kg"
            },
            'alarms_summary': {
                'avg_resolution': "—"
            },
            'recommendations': []
        }

def build_report_datasets(start_dt: datetime, end_dt: datetime):
    """Monta DataFrames detalhados para exportação (Excel/PDF-HTML) no período informado.
    Retorna um dicionário com:
      - summary (dict)
      - production_by_client (DataFrame)
      - daily_production (DataFrame)
      - water_chemicals_daily (DataFrame)
      - alarms_daily (DataFrame)
    """
    try:
        # Normalizar fim exclusivo para facilitar filtros inclusivos no dia final
        end_exclusive = (end_dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        # 1) Sumário executivo já existente
        summary = generate_executive_report(start_dt, end_dt)

        # 2) Produção por cliente COM alias dos nomes salvos
        prod_client_sql = """
            SELECT 
                CAST(rc."C1" AS INTEGER) AS client_id,
                COALESCE(ca.alias, 'Cliente ' || CAST(rc."C1" AS TEXT)) AS client_display,
                COUNT(*) AS total_cargas,
                COALESCE(SUM(rc."C2"), 0) AS total_kg,
                COALESCE(AVG(NULLIF(rc."C2", 0)), 0) AS peso_medio_kg
            FROM "Rel_Carga" rc
            LEFT JOIN app.client_alias ca ON CAST(rc."C1" AS INTEGER) = ca.client_id
            WHERE rc."Time_Stamp" >= %s AND rc."Time_Stamp" < %s
            GROUP BY rc."C1", ca.alias
            ORDER BY total_kg DESC
        """
        prod_client_df = db.execute_query(prod_client_sql, (start_dt, end_exclusive))

        # 3) Produção diária (kg e cargas)
        daily_prod_sql = """
            SELECT 
                "Time_Stamp"::date AS dia,
                COUNT(*) AS cargas,
                COALESCE(SUM("C2"), 0) AS kg
            FROM "Rel_Carga"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
            GROUP BY "Time_Stamp"::date
            ORDER BY dia
        """
        daily_prod_df = db.execute_query(daily_prod_sql, (start_dt, end_exclusive))

        # 4) Água corrigida (Rel_Diario) e Químicos (Rel_Quimico) por dia
        water_daily_sql = """
            SELECT 
                "Time_Stamp"::date AS dia,
                COALESCE(SUM("C4"), 0) AS kg,
                COALESCE(COUNT(*), 0) AS ciclos,
                COALESCE(SUM("C2") * 1000, 0) AS agua_litros
            FROM "Rel_Diario"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
            GROUP BY "Time_Stamp"::date
            ORDER BY dia
        """
        water_daily_df = db.execute_query(water_daily_sql, (start_dt, end_exclusive))

        chemicals_daily_sql = """
            SELECT 
                "Time_Stamp"::date AS dia,
                COALESCE(SUM(COALESCE("Q1",0) + COALESCE("Q2",0) + COALESCE("Q3",0) + COALESCE("Q4",0) + COALESCE("Q5",0)), 0) AS quimicos
            FROM "Rel_Quimico"
            WHERE "Time_Stamp" >= %s AND "Time_Stamp" < %s
            GROUP BY "Time_Stamp"::date
            ORDER BY dia
        """
        chemicals_daily_df = db.execute_query(chemicals_daily_sql, (start_dt, end_exclusive))

        # Merge água + químicos
        water_chem_daily = pd.merge(water_daily_df, chemicals_daily_df, on='dia', how='outer').sort_values('dia')
        # Derivar métricas por kg se possível
        if not water_chem_daily.empty:
            water_chem_daily['agua_por_kg'] = water_chem_daily.apply(
                lambda r: (float(r['agua_litros']) / float(r['kg'])) if (pd.notnull(r['kg']) and r['kg'] not in [0, 0.0]) else 0.0, axis=1
            )
            water_chem_daily['quimicos_por_kg'] = water_chem_daily.apply(
                lambda r: (float(r['quimicos']) / float(r['kg'])) if (pd.notnull(r['kg']) and r['kg'] not in [0, 0.0]) else 0.0, axis=1
            )

        # 5) Alarmes por dia
        alarms_daily_sql = """
            SELECT 
                DATE("Al_Start_Time") AS dia,
                COUNT(*) AS alarmes
            FROM "ALARMHISTORY"
            WHERE "Al_Start_Time" >= %s AND "Al_Start_Time" < %s
            GROUP BY dia
            ORDER BY dia
        """
        alarms_daily_df = db.execute_query(alarms_daily_sql, (start_dt, end_exclusive))

        return {
            'summary': summary,
            'production_by_client': prod_client_df,
            'daily_production': daily_prod_df,
            'water_chemicals_daily': water_chem_daily,
            'alarms_daily': alarms_daily_df
        }
    except Exception as e:
        print(f"Erro ao montar datasets do relatório: {e}")
        return {
            'summary': generate_executive_report(start_dt, end_dt),
            'production_by_client': pd.DataFrame(),
            'daily_production': pd.DataFrame(),
            'water_chemicals_daily': pd.DataFrame(),
            'alarms_daily': pd.DataFrame()
        }

class DatabaseManager:
    """Gerenciador de conexão com PostgreSQL"""
    
    def __init__(self):
        self.config = DB_CONFIG
    
    def get_connection(self):
        try:
            # Garantir timeout de conexão para evitar travamentos
            cfg = dict(self.config)
            cfg.setdefault('connect_timeout', 5)
            return psycopg2.connect(**cfg)
        except Exception as e:
            print(f"Erro ao conectar com banco: {e}")
            return None
    
    def execute_query(self, query, params=None):
        conn = self.get_connection()
        if conn:
            try:
                # Evitar queries demoradas: statement_timeout 5s
                try:
                    with conn.cursor() as cur:
                        cur.execute("SET statement_timeout TO 5000")
                except Exception as _:
                    pass
                df = pd.read_sql_query(query, conn, params=params)
                conn.close()
                return df
            except Exception as e:
                print(f"Erro ao executar query: {e}")
                conn.close()
                return pd.DataFrame()
        return pd.DataFrame()

# Instância do gerenciador de banco
db = DatabaseManager()

# Inicializar app Dash
app = dash.Dash(__name__, 
                external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
                suppress_callback_exceptions=True,
                title="DSTech Dashboard")

# CSS customizado para melhorar responsividade
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            /* Responsividade geral */
            @media (max-width: 576px) {
                .container-fluid { padding-left: 10px !important; padding-right: 10px !important; }
                .card-body { padding: 1rem !important; }
                .btn { font-size: 0.875rem !important; }
                h1, h2, h3 { font-size: calc(1rem + 1vw) !important; }
                .badge { font-size: 0.75rem !important; }
            }
            
            /* Gráficos na aba específica - mais espaço */
            @media (min-width: 992px) and (max-width: 1199px) {
                #charts-efficiency-chart, #charts-water-chart, #charts-top-alarms-chart {
                    min-height: 450px !important;
                }
                #charts-trend-analysis-chart {
                    min-height: 550px !important;
                }
            }
            
            /* Gráficos responsivos */
            .js-plotly-plot { width: 100% !important; }
            .plotly { width: 100% !important; }
            
            /* Cards responsivos */
            .card { margin-bottom: 1rem; }
            @media (max-width: 768px) {
                .card-body { padding: 0.75rem; }
                .row { margin-left: -5px; margin-right: -5px; }
                .col, [class*="col-"] { padding-left: 5px; padding-right: 5px; }
            }
            
            /* DatePicker responsivo */
            .DateInput { width: 100% !important; }
            .DateRangePickerInput { width: 100% !important; }
            .DateRangePickerInput__withBorder { border-radius: 6px; }
            
            /* Tabelas responsivas */
            .dash-table-container { overflow-x: auto; }
            
            /* Header responsivo */
            @media (max-width: 768px) {
                .text-end { text-align: center !important; margin-top: 1rem; }
                .d-flex { flex-direction: column; align-items: center !important; }
            }
            
            /* Tabs responsivos */
            .nav-tabs { flex-wrap: wrap; }
            .nav-link { font-size: 0.9rem; padding: 0.5rem 0.75rem; }
            @media (max-width: 576px) {
                .nav-link { font-size: 0.8rem; padding: 0.4rem 0.6rem; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

# Layout de login compacto
login_layout = dbc.Container([
    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardBody([
                    html.Div([
                        # Logo e título mais compactos
                        html.Div([
                            html.Img(src="/assets/logodstech.png", 
                                    style={'height': '60px', 'width': 'auto', 'margin-bottom': '15px'})
                        ], className="text-center mb-3"),
                        html.H5("Sistema de Monitoramento Industrial", 
                               className="text-center mb-3", 
                               style={'color': '#2c3e50', 'font-weight': '500'}),
                        
                        # Formulário mais compacto
                        dbc.Form([
                            dbc.Row([
                                dbc.Label("Usuário", html_for="username", className="fw-bold mb-1"),
                                dbc.Input(id="username", type="text", placeholder="Digite seu usuário",
                                         className="mb-2")
                            ]),
                            dbc.Row([
                                dbc.Label("Senha", html_for="password", className="fw-bold mb-1"),
                                dbc.Input(id="password", type="password", placeholder="Digite sua senha",
                                         className="mb-3")
                            ]),
                            dbc.Button("Entrar", id="login-button", color="primary", 
                                     className="w-100",
                                     style={'padding': '8px', 'font-weight': '500'})
                        ]),
                        
                        html.Div(id="login-alert", className="mt-2")
                    ], style={'padding': '20px'})
                ])
            ], style={'box-shadow': '0 4px 8px rgba(0, 0, 0, 0.1)', 'border': 'none', 'border-radius': '8px'})
        ], width=3, lg=3, md=4, sm=6, xs=10)
    ], justify="center", className="min-vh-100 align-items-center")
], fluid=True, style={'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'})

def create_relatorios_tab(start_date, end_date):
    """Aba 'Relatórios' moderna com preview dos dados"""
    # Normalizar datas recebidas
    try:
        if isinstance(start_date, str) and start_date:
            start_dt = datetime.fromisoformat(start_date)
        elif isinstance(start_date, datetime):
            start_dt = start_date
        else:
            start_dt = datetime.now() - timedelta(days=7)
        if isinstance(end_date, str) and end_date:
            end_dt = datetime.fromisoformat(end_date)
        elif isinstance(end_date, datetime):
            end_dt = end_date
        else:
            end_dt = datetime.now()
    except Exception:
        start_dt = datetime.now() - timedelta(days=7)
        end_dt = datetime.now()

    # Gerar dados do relatório para preview
    try:
        report_data = generate_executive_report(start_dt, end_dt)
        datasets = build_report_datasets(start_dt, end_dt)
    except Exception as e:
        print(f"Erro ao gerar preview do relatório: {e}")
        report_data = None
        datasets = None

    return html.Div([
        # Header modernizado com seletor de data e botões
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("📋", style={'font-size': '1.8rem', 'margin-right': '0.75rem'}),
                            html.H4("Relatórios Executivos", className="mb-0", style={'color': 'white'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #6f42c1 0%, #8e44ad 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Span("📅", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                    dbc.Label("Período de Análise", className="fw-bold mb-2", style={'display': 'inline'})
                                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '0.5rem'}),
                                html.Div([
                                    dcc.DatePickerRange(
                                        id='report-date-picker',
                                        start_date=start_dt.date(),
                                        end_date=end_dt.date(),
                                        display_format='DD/MM/YYYY',
                                        style={'width': '100%', 'font-size': '1rem'}
                                    )
                                ], style={'position': 'relative', 'z-index': '9999'})
                            ], xs=12, md=6),
                            dbc.Col([
                                html.Div([
                                    html.Span("⚙️", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                    dbc.Label("Ações", className="fw-bold mb-2", style={'display': 'inline'})
                                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '0.5rem'}),
                                dbc.ButtonGroup([
                                    dbc.Button("⬇️ Excel", id="export-excel-btn", color="success", size="sm", style={'border-radius': '8px 0 0 8px'}),
                                    dbc.Button("🖨️ PDF", id="export-pdf-btn", color="danger", size="sm", style={'border-radius': '0'}),
                                    dbc.Button("🔄 Atualizar", id="refresh-report-btn", color="info", outline=True, size="sm", style={'border-radius': '0 8px 8px 0'})
                                ], className="d-flex w-100")
                            ], xs=12, md=6, className="d-flex flex-column")
                        ])
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(111, 66, 193, 0.15)',
                    'border': 'none'
                })
            ], width=12)
        ], className="mb-4"),


        # Top Clientes
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("🏆 Top 10 Clientes", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id="top-clients-preview", children=[
                            create_top_clients_table(datasets['production_by_client'] if datasets else pd.DataFrame())
                        ])
                    ])
                ])
            ], width=12)
        ]),

        # Downloads
        dcc.Download(id="download-excel-report"),
        dcc.Download(id="download-pdf-report")
    ])

def create_top_clients_table(df):
    """Cria tabela dos top clientes"""
    if df.empty:
        return html.P("Nenhum dado disponível", className="text-muted")
    
    top_10 = df.head(10)
    
    return dbc.Table([
        html.Thead([
            html.Tr([
                html.Th("Cliente"),
                html.Th("Produção (kg)", className="text-end"),
                html.Th("Cargas", className="text-end"),
                html.Th("Peso Médio (kg)", className="text-end")
            ])
        ]),
        html.Tbody([
            html.Tr([
                html.Td(row['client_display']),
                html.Td(f"{row['total_kg']:,.1f}", className="text-end"),
                html.Td(f"{row['total_cargas']}", className="text-end"),
                html.Td(f"{row['peso_medio_kg']:.1f}", className="text-end")
            ]) for _, row in top_10.iterrows()
        ])
    ], striped=True, hover=True, size="sm")

@app.callback(
    Output('download-excel-report', 'data', allow_duplicate=True),
    Input('export-excel-btn', 'n_clicks'),
    State('report-date-picker', 'start_date'),
    State('report-date-picker', 'end_date'),
    prevent_initial_call='initial_duplicate'
)
def export_report_excel(n_clicks, start_date, end_date):
    """Gera um Excel completo com múltiplas abas e formatação básica."""
    from io import BytesIO
    from dash.exceptions import PreventUpdate

    if not n_clicks:
        raise PreventUpdate

    # Normalizar datas
    try:
        start_dt = datetime.fromisoformat(start_date) if isinstance(start_date, str) and start_date else datetime.now() - timedelta(days=7)
        end_dt = datetime.fromisoformat(end_date) if isinstance(end_date, str) and end_date else datetime.now()
    except Exception:
        start_dt = datetime.now() - timedelta(days=7)
        end_dt = datetime.now()

    datasets = build_report_datasets(start_dt, end_dt)

    # Montar Excel em memória com formatação
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Estilos de formatação
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'top',
            'fg_color': '#4472C4',
            'font_color': 'white',
            'border': 1
        })
        
        number_format = workbook.add_format({'num_format': '#,##0.00'})
        integer_format = workbook.add_format({'num_format': '#,##0'})
        cell_format = workbook.add_format({'border': 1})
        
        # Aba 1: Sumário
        summary = datasets['summary']
        summary_rows = [
            {'Métrica': 'Período (dias)', 'Valor': summary.get('period_days')},
            {'Métrica': 'Produção (kg)', 'Valor': summary['production_summary'].get('period_production')},
            {'Métrica': 'Ciclos', 'Valor': summary['production_summary'].get('period_cycles')},
            {'Métrica': 'Média diária (kg)', 'Valor': summary['production_summary'].get('daily_avg')},
            {'Métrica': 'Peso médio (kg)', 'Valor': summary['production_summary'].get('avg_weight')},
            {'Métrica': 'Água (L)', 'Valor': summary['consumption_summary'].get('water_period')},
            {'Métrica': 'Água por kg (L/kg)', 'Valor': summary['consumption_summary'].get('water_per_kg')},
            {'Métrica': 'Químicos (un)', 'Valor': summary['consumption_summary'].get('chemicals_period')},
            {'Métrica': 'Químicos por kg', 'Valor': summary['consumption_summary'].get('chemicals_per_kg')},
            {'Métrica': 'Alarmes no período', 'Valor': summary['alarms_summary'].get('period_alarms')},
            {'Métrica': 'Alarmes ativos', 'Valor': summary['alarms_summary'].get('active_alarms')},
        ]
        summary_df = pd.DataFrame(summary_rows)
        summary_df.to_excel(writer, sheet_name='Resumo', index=False)
        
        # Formatação da aba Resumo
        worksheet = writer.sheets['Resumo']
        worksheet.set_column('A:A', 25, cell_format)
        worksheet.set_column('B:B', 15, number_format)
        for col_num, value in enumerate(summary_df.columns.values):
            worksheet.write(0, col_num, value, header_format)

        # Aba 2: Produção por Cliente
        if isinstance(datasets['production_by_client'], pd.DataFrame):
            df = datasets['production_by_client']
            df.to_excel(writer, sheet_name='Prod_Cliente', index=False)
            worksheet = writer.sheets['Prod_Cliente']
            worksheet.set_column('A:Z', 15, cell_format)
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        # Aba 3: Produção diária
        if isinstance(datasets['daily_production'], pd.DataFrame):
            df = datasets['daily_production']
            df.to_excel(writer, sheet_name='Prod_Diaria', index=False)
            worksheet = writer.sheets['Prod_Diaria']
            worksheet.set_column('A:Z', 15, cell_format)
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        # Aba 4: Água & Químicos diários
        if isinstance(datasets['water_chemicals_daily'], pd.DataFrame):
            df = datasets['water_chemicals_daily']
            df.to_excel(writer, sheet_name='Agua_Quimicos', index=False)
            worksheet = writer.sheets['Agua_Quimicos']
            worksheet.set_column('A:Z', 15, cell_format)
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

        # Aba 5: Alarmes diários
        if isinstance(datasets['alarms_daily'], pd.DataFrame):
            df = datasets['alarms_daily']
            df.to_excel(writer, sheet_name='Alarmes', index=False)
            worksheet = writer.sheets['Alarmes']
            worksheet.set_column('A:Z', 15, cell_format)
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)

    output.seek(0)
    fname = f"relatorio_dstech_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.xlsx"
    return dcc.send_bytes(output.getvalue(), filename=fname)

@app.callback(
    Output('download-pdf-report', 'data', allow_duplicate=True),
    Input('export-pdf-btn', 'n_clicks'),
    State('report-date-picker', 'start_date'),
    State('report-date-picker', 'end_date'),
    prevent_initial_call='initial_duplicate'
)
def export_report_pdfhtml(n_clicks, start_date, end_date):
    """Gera um PDF completo e detalhado com ReportLab."""
    from dash.exceptions import PreventUpdate

    if not n_clicks:
        raise PreventUpdate

    # Normalizar datas
    try:
        start_dt = datetime.fromisoformat(start_date) if isinstance(start_date, str) and start_date else datetime.now() - timedelta(days=7)
        end_dt = datetime.fromisoformat(end_date) if isinstance(end_date, str) and end_date else datetime.now()
    except Exception:
        start_dt = datetime.now() - timedelta(days=7)
        end_dt = datetime.now()

    datasets = build_report_datasets(start_dt, end_dt)
    s = datasets['summary']

    # Gerar PDF detalhado com ReportLab
    from io import BytesIO
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.lib.units import inch
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.widgetbase import Widget
    from reportlab.lib.colors import PCMYKColor, Color

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=50, rightMargin=50, topMargin=50, bottomMargin=50)
    styles = getSampleStyleSheet()
    
    # Estilos customizados
    title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=24, spaceAfter=30, alignment=1)
    heading_style = ParagraphStyle('CustomHeading', parent=styles['Heading2'], fontSize=16, spaceAfter=12, textColor=colors.darkblue)
    
    elements = []

    # === PÁGINA 1: CAPA E RESUMO EXECUTIVO ===
    elements.append(Paragraph("🏭 RELATÓRIO COMPLETO DSTech", title_style))
    elements.append(Paragraph("Sistema de Monitoramento Industrial", styles['Normal']))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"📅 Período de Análise: {start_dt.strftime('%d/%m/%Y')} - {end_dt.strftime('%d/%m/%Y')}", styles['Heading3']))
    elements.append(Paragraph(f"⏰ Relatório gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 30))

    # Resumo executivo detalhado
    elements.append(Paragraph("📊 RESUMO EXECUTIVO", heading_style))
    
    def extract_numeric(value):
        if isinstance(value, str):
            import re
            numbers = re.findall(r'[\d,\.]+', str(value))
            if numbers:
                return float(numbers[0].replace(',', ''))
        return float(value) if value else 0

    prod_kg = extract_numeric(s['production_summary'].get('period_production', 0))
    cycles = s['production_summary'].get('period_cycles', 0)
    water_l = extract_numeric(s['consumption_summary'].get('water_period', 0))
    chemicals_kg = extract_numeric(s['consumption_summary'].get('chemicals_period', 0))
    daily_avg = extract_numeric(s['production_summary'].get('daily_avg', 0))
    avg_weight = extract_numeric(s['production_summary'].get('avg_weight', 0))

    # Cálculos corrigidos
    days_in_period = (end_dt - start_dt).days + 1
    avg_cycles_day = cycles / days_in_period if days_in_period > 0 else 0
    
    # Corrigir eficiências
    water_efficiency = water_l / prod_kg if prod_kg > 0 else 0
    chemicals_efficiency = chemicals_kg / prod_kg if prod_kg > 0 else 0
    
    resumo_data = [
        ["MÉTRICA", "VALOR", "UNIDADE", "OBSERVAÇÕES"],
        ["Produção Total", f"{prod_kg:,.0f}", "kg", f"Período de {days_in_period} dias"],
        ["Ciclos Realizados", f"{cycles:,}", "ciclos", f"Média: {avg_cycles_day:.1f} ciclos/dia"],
        ["Produção Média Diária", f"{daily_avg:,.0f}", "kg/dia", f"Peso médio: {avg_weight:.1f} kg/ciclo"],
        ["Consumo Total de Água", f"{water_l:,.0f}", "L", f"Eficiência: {water_efficiency:.2f} L/kg"],
        ["Consumo Total de Químicos", f"{chemicals_kg:,.1f}", "kg", f"Eficiência: {chemicals_efficiency:.3f} kg/kg"],
        ["Dias no Período", f"{days_in_period}", "dias", f"Análise completa do período"],
    ]
    
    t = Table(resumo_data, colWidths=[3*inch, 1.5*inch, 1*inch, 2*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,0), 10),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.beige),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
    ]))
    elements.append(t)
    
    # Adicionar gráfico de produção diária
    if not datasets['daily_production'].empty:
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("📈 GRÁFICO DE PRODUÇÃO DIÁRIA", heading_style))
        
        # Criar gráfico de linha
        drawing = Drawing(400, 200)
        lp = LinePlot()
        lp.x = 50
        lp.y = 50
        lp.height = 125
        lp.width = 300
        
        # Preparar dados (últimos 30 dias para não sobrecarregar)
        daily_df = datasets['daily_production'].tail(30)
        data = [(i, row['kg']) for i, (_, row) in enumerate(daily_df.iterrows())]
        lp.data = [data]
        
        lp.lines[0].strokeColor = colors.blue
        lp.lines[0].strokeWidth = 2
        lp.xValueAxis.valueMin = 0
        lp.xValueAxis.valueMax = len(data)
        lp.yValueAxis.valueMin = 0
        lp.yValueAxis.valueMax = max([d[1] for d in data]) * 1.1 if data else 1000
        
        drawing.add(lp)
        elements.append(drawing)
    
    elements.append(PageBreak())

    # === PÁGINA 2: PRODUÇÃO POR CLIENTE DETALHADA ===
    elements.append(Paragraph("👥 ANÁLISE DETALHADA DE CLIENTES", heading_style))
    
    if not datasets['production_by_client'].empty:
        # Estatísticas de clientes
        total_clients = len(datasets['production_by_client'])
        top_client = datasets['production_by_client'].iloc[0] if len(datasets['production_by_client']) > 0 else None
        
        elements.append(Paragraph(f"📈 Total de Clientes Ativos: {total_clients}", styles['Normal']))
        if top_client is not None:
            elements.append(Paragraph(f"🏆 Cliente Líder: {top_client['client_display']} ({top_client['total_kg']:,.0f} kg)", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Tabela completa de clientes
        client_data = [["#", "CLIENTE", "PRODUÇÃO (kg)", "CARGAS", "% TOTAL", "MÉDIA/CARGA"]]
        for i, (_, row) in enumerate(datasets['production_by_client'].iterrows(), 1):
            pct_total = (row['total_kg'] / prod_kg * 100) if prod_kg > 0 else 0
            avg_per_load = row['total_kg'] / row['total_cargas'] if row['total_cargas'] > 0 else 0
            client_data.append([
                str(i),
                str(row['client_display'])[:30],
                f"{row['total_kg']:,.0f}",
                f"{row['total_cargas']:,}",
                f"{pct_total:.1f}%",
                f"{avg_per_load:,.0f}"
            ])
        
        client_table = Table(client_data, colWidths=[0.5*inch, 2.5*inch, 1.2*inch, 0.8*inch, 0.8*inch, 1*inch])
        client_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkgreen),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(client_table)
        
        # Adicionar gráfico de pizza dos top 10 clientes
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("🥧 DISTRIBUIÇÃO DOS TOP 10 CLIENTES", heading_style))
        
        drawing = Drawing(400, 200)
        pie = Pie()
        pie.x = 150
        pie.y = 50
        pie.width = 100
        pie.height = 100
        
        # Preparar dados do top 10
        top10 = datasets['production_by_client'].head(10)
        pie_data = []
        pie_labels = []
        
        for _, row in top10.iterrows():
            pie_data.append(row['total_kg'])
            pie_labels.append(str(row['client_display'])[:15])
        
        pie.data = pie_data
        pie.labels = pie_labels
        
        # Cores para o gráfico
        pie.slices.strokeColor = colors.white
        pie.slices.strokeWidth = 1
        
        drawing.add(pie)
        elements.append(drawing)
        
    else:
        elements.append(Paragraph("❌ Sem dados de clientes no período.", styles['Normal']))
    
    elements.append(PageBreak())

    # === PÁGINA 3: PRODUÇÃO DIÁRIA DETALHADA ===
    elements.append(Paragraph("📅 ANÁLISE DE PRODUÇÃO DIÁRIA", heading_style))
    
    if not datasets['daily_production'].empty:
        # Estatísticas diárias
        daily_df = datasets['daily_production'].copy()
        max_day = daily_df.loc[daily_df['kg'].idxmax()] if len(daily_df) > 0 else None
        min_day = daily_df.loc[daily_df['kg'].idxmin()] if len(daily_df) > 0 else None
        
        if max_day is not None and min_day is not None:
            elements.append(Paragraph(f"📊 Estatísticas do Período:", styles['Heading3']))
            elements.append(Paragraph(f"• Melhor dia: {max_day['dia']} ({max_day['kg']:,.0f} kg)", styles['Normal']))
            elements.append(Paragraph(f"• Menor dia: {min_day['dia']} ({min_day['kg']:,.0f} kg)", styles['Normal']))
            elements.append(Paragraph(f"• Variação: {((max_day['kg'] - min_day['kg']) / min_day['kg'] * 100):.1f}%", styles['Normal']))
            elements.append(Spacer(1, 12))
        
        # Tabela de produção diária
        daily_data = [["DATA", "PRODUÇÃO (kg)", "CARGAS", "EFICIÊNCIA"]]
        for _, row in daily_df.iterrows():
            efficiency = (row['kg'] / daily_avg * 100) if daily_avg > 0 else 0
            daily_data.append([
                str(row['dia']),
                f"{row['kg']:,.0f}",
                f"{row['cargas']:,}",
                f"{efficiency:.1f}%"
            ])
        
        daily_table = Table(daily_data, colWidths=[1.5*inch, 1.5*inch, 1*inch, 1.5*inch])
        daily_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkorange),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(daily_table)
    else:
        elements.append(Paragraph("❌ Sem dados de produção diária no período.", styles['Normal']))
    
    elements.append(PageBreak())

    # === PÁGINA 4: CONSUMO DE ÁGUA E QUÍMICOS ===
    elements.append(Paragraph("💧🧪 ANÁLISE DE CONSUMO", heading_style))
    
    if not datasets['water_chemicals_daily'].empty:
        wc_df = datasets['water_chemicals_daily'].copy()
        
        # Estatísticas de consumo
        total_water = wc_df['agua_litros'].sum() if 'agua_litros' in wc_df.columns else 0
        total_chemicals = wc_df['quimicos'].sum() if 'quimicos' in wc_df.columns else 0
        avg_water_day = total_water / len(wc_df) if len(wc_df) > 0 else 0
        avg_chemicals_day = total_chemicals / len(wc_df) if len(wc_df) > 0 else 0
        
        elements.append(Paragraph(f"📊 Resumo de Consumo:", styles['Heading3']))
        elements.append(Paragraph(f"• Água total: {total_water:,.0f} L", styles['Normal']))
        elements.append(Paragraph(f"• Químicos total: {total_chemicals:,.0f} kg", styles['Normal']))
        elements.append(Paragraph(f"• Média diária água: {avg_water_day:,.0f} L/dia", styles['Normal']))
        elements.append(Paragraph(f"• Média diária químicos: {avg_chemicals_day:,.0f} kg/dia", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Tabela de consumo diário
        wc_data = [["DATA", "PRODUÇÃO (kg)", "ÁGUA (L)", "QUÍMICOS (kg)", "CICLOS", "EFIC. ÁGUA", "EFIC. QUÍMICOS"]]
        for _, row in wc_df.iterrows():
            water_eff = (row.get('agua_litros', 0) / avg_water_day * 100) if avg_water_day > 0 else 0
            chem_eff = (row.get('quimicos', 0) / avg_chemicals_day * 100) if avg_chemicals_day > 0 else 0
            wc_data.append([
                str(row['dia']),
                f"{row.get('kg', 0):,.0f}",
                f"{row.get('agua_litros', 0):,.0f}",
                f"{row.get('quimicos', 0):,.0f}",
                f"{row.get('ciclos', 0):,}",
                f"{row.get('agua_por_kg', 0):.2f} L/kg",
                f"{row.get('quimicos_por_kg', 0):.3f} kg/kg"
            ])
        
        wc_table = Table(wc_data, colWidths=[1*inch, 1*inch, 1*inch, 1*inch, 0.8*inch, 1*inch, 1*inch])
        wc_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.teal),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,0), 8),
            ('FONTSIZE', (0,1), (-1,-1), 7),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(wc_table)
        
        # Adicionar gráfico de barras de consumo
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("📊 GRÁFICO DE CONSUMO DIÁRIO", heading_style))
        
        drawing = Drawing(400, 200)
        bc = VerticalBarChart()
        bc.x = 50
        bc.y = 50
        bc.height = 125
        bc.width = 300
        
        # Preparar dados (últimos 15 dias para legibilidade)
        wc_sample = wc_df.tail(15)
        agua_data = [row.get('agua_litros', 0) for _, row in wc_sample.iterrows()]
        quimicos_data = [row.get('quimicos', 0) * 100 for _, row in wc_sample.iterrows()]  # Escalar químicos
        
        bc.data = [agua_data, quimicos_data]
        bc.bars[0].fillColor = colors.lightblue
        bc.bars[1].fillColor = colors.orange
        
        bc.valueAxis.valueMin = 0
        max_agua = max(agua_data) if agua_data else 0
        max_quimicos = max(quimicos_data) if quimicos_data else 0
        bc.valueAxis.valueMax = max(max_agua, max_quimicos) * 1.1 if max(max_agua, max_quimicos) > 0 else 1000
        bc.categoryAxis.categoryNames = [f"D{i+1}" for i in range(len(agua_data))]
        
        drawing.add(bc)
        elements.append(drawing)
        
    else:
        elements.append(Paragraph("❌ Sem dados de consumo no período.", styles['Normal']))
    
    elements.append(PageBreak())

    # === PÁGINA 5: ALARMES E EVENTOS ===
    elements.append(Paragraph("🚨 ANÁLISE DE ALARMES E EVENTOS", heading_style))
    
    if not datasets['alarms_daily'].empty:
        alarms_df = datasets['alarms_daily'].copy()
        
        # Estatísticas de alarmes
        total_alarms = alarms_df['alarmes'].sum() if 'alarmes' in alarms_df.columns else 0
        avg_alarms_day = total_alarms / len(alarms_df) if len(alarms_df) > 0 else 0
        max_alarms_day = alarms_df['alarmes'].max() if 'alarmes' in alarms_df.columns else 0
        
        elements.append(Paragraph(f"📊 Resumo de Alarmes:", styles['Heading3']))
        elements.append(Paragraph(f"• Total de alarmes: {total_alarms:,}", styles['Normal']))
        elements.append(Paragraph(f"• Média diária: {avg_alarms_day:.1f} alarmes/dia", styles['Normal']))
        elements.append(Paragraph(f"• Pico máximo: {max_alarms_day:,} alarmes/dia", styles['Normal']))
        elements.append(Spacer(1, 12))
        
        # Tabela de alarmes diários
        alarm_data = [["DATA", "TOTAL ALARMES", "CRÍTICOS", "AVISOS", "STATUS"]]
        for _, row in alarms_df.iterrows():
            total_day = row.get('alarmes', 0)
            status = "🔴 Alto" if total_day > avg_alarms_day * 1.5 else "🟡 Médio" if total_day > avg_alarms_day else "🟢 Baixo"
            alarm_data.append([
                str(row['dia']),
                f"{total_day:,}",
                f"{int(total_day * 0.2):,}",  # Estimativa de críticos
                f"{int(total_day * 0.8):,}",  # Estimativa de avisos
                status
            ])
        
        alarm_table = Table(alarm_data, colWidths=[1.5*inch, 1.2*inch, 1*inch, 1*inch, 1.3*inch])
        alarm_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkred),
            ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTNAME', (0,1), (-1,-1), 'Helvetica'),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ]))
        elements.append(alarm_table)
    else:
        elements.append(Paragraph("✅ Nenhum alarme registrado no período.", styles['Normal']))
    
    elements.append(PageBreak())

    # === PÁGINA 6: CONCLUSÕES E RECOMENDAÇÕES ===
    elements.append(Paragraph("📋 CONCLUSÕES E RECOMENDAÇÕES", heading_style))
    
    elements.append(Spacer(1, 20))
    
    # Recomendações
    elements.append(Paragraph("💡 Recomendações:", styles['Heading3']))
    elements.append(Paragraph("• Monitorar continuamente a eficiência de produção", styles['Normal']))
    elements.append(Paragraph("• Otimizar o consumo de água e químicos", styles['Normal']))
    elements.append(Paragraph("• Implementar manutenção preventiva baseada em dados", styles['Normal']))
    elements.append(Paragraph("• Analisar padrões de alarmes para melhorias", styles['Normal']))
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph("📋 Relatório gerado automaticamente pelo Sistema DSTech", styles['Normal']))
    elements.append(Paragraph(f"🔗 Dados extraídos do período {start_dt.strftime('%d/%m/%Y')} a {end_dt.strftime('%d/%m/%Y')}", styles['Normal']))

    # Gerar PDF
    doc.build(elements)
    buf.seek(0)
    fname = f"relatorio_completo_dstech_{start_dt.strftime('%Y%m%d')}_{end_dt.strftime('%Y%m%d')}.pdf"
    return dcc.send_bytes(buf.getvalue(), filename=fname)


# Callback para atualizar relatório
@app.callback(
    Output('report-content', 'children'),
    [Input('report-date-picker', 'start_date'),
     Input('report-date-picker', 'end_date')]
)
def update_report_content(start_date, end_date):
    if not start_date or not end_date:
        return html.Div("Selecione um período para gerar o relatório.", className="alert alert-info")
    
    try:
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)
    except:
        return html.Div("Datas inválidas.", className="alert alert-danger")
    
    datasets = build_report_datasets(start_dt, end_dt)
    s = datasets['summary']
    
    def extract_numeric_html(value):
        if isinstance(value, str):
            import re
            numbers = re.findall(r'[\d,\.]+', str(value))
            if numbers:
                return float(numbers[0].replace(',', ''))
        return float(value) if value else 0

    prod_kg = extract_numeric_html(s['production_summary'].get('period_production', 0))
    cycles = s['production_summary'].get('period_cycles', 0)
    water_l = extract_numeric_html(s['consumption_summary'].get('water_period', 0))
    chemicals_kg = extract_numeric_html(s['consumption_summary'].get('chemicals_period', 0))
    
    html_doc = f"""
        <!DOCTYPE html>
        <html lang="pt-br">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0">
          <title>Relatório Executivo DSTech - {start_dt.strftime('%d/%m/%Y')} a {end_dt.strftime('%d/%m/%Y')}</title>
          <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; }}
            body {{ 
              font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
              line-height: 1.6; 
              color: #2c3e50; 
              background: #f8f9fa;
              padding: 20px;
            }}
            .container {{ 
              max-width: 1200px; 
              margin: 0 auto; 
              background: white; 
              border-radius: 12px; 
              box-shadow: 0 4px 6px rgba(0,0,0,0.1);
              overflow: hidden;
            }}
            .header {{ 
              background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
              color: white;
              padding: 30px;
              text-align: center;
            }}
            .header h1 {{ 
              font-size: 2.5rem; 
              margin-bottom: 10px; 
              font-weight: 300;
            }}
            .header .period {{ 
              font-size: 1.1rem; 
              opacity: 0.9;
            }}
            .content {{ padding: 30px; }}
            .metrics-grid {{ 
              display: grid; 
              grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
              gap: 20px; 
              margin: 30px 0;
            }}
            .metric-card {{ 
              background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
              color: white;
              padding: 25px;
              border-radius: 12px;
              text-align: center;
              box-shadow: 0 4px 15px rgba(0,0,0,0.1);
              transition: transform 0.3s ease;
            }}
            .metric-card:hover {{ transform: translateY(-5px); }}
            .metric-card.production {{ background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }}
            .metric-card.water {{ background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); }}
            .metric-card.chemicals {{ background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); }}
            .metric-card.cycles {{ background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); color: #2c3e50; }}
            .metric-value {{ 
              font-size: 2.2rem; 
              font-weight: bold; 
              margin-bottom: 8px;
              text-shadow: 0 2px 4px rgba(0,0,0,0.2);
            }}
            .metric-label {{ 
              font-size: 0.95rem; 
              opacity: 0.9;
              text-transform: uppercase;
              letter-spacing: 1px;
            }}
            .section {{ 
              margin: 40px 0;
              background: #f8f9fa;
              border-radius: 8px;
              overflow: hidden;
            }}
            .section-header {{ 
              background: #495057;
              color: white;
              padding: 15px 25px;
              font-size: 1.3rem;
              font-weight: 600;
            }}
            .section-content {{ padding: 25px; }}
            table {{ 
              width: 100%; 
              border-collapse: collapse; 
              background: white;
              border-radius: 8px;
              overflow: hidden;
              box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            th {{ 
              background: #343a40;
              color: white;
              padding: 15px 12px;
              text-align: left;
              font-weight: 600;
              font-size: 0.9rem;
              text-transform: uppercase;
              letter-spacing: 0.5px;
            }}
            td {{ 
              padding: 12px;
              border-bottom: 1px solid #dee2e6;
              font-size: 0.95rem;
            }}
            tr:nth-child(even) {{ background-color: #f8f9fa; }}
            tr:hover {{ background-color: #e9ecef; }}
            .no-data {{ 
              color: #6c757d; 
              font-style: italic; 
              text-align: center; 
              padding: 40px;
              background: #f8f9fa;
              border-radius: 8px;
            }}
            .summary-table {{ margin-top: 20px; }}
            .summary-table th {{ background: #17a2b8; }}
            .footer {{ 
              margin-top: 40px;
              padding: 20px;
              text-align: center;
              color: #6c757d;
              border-top: 1px solid #dee2e6;
            }}
            @media print {{ 
              body {{ background: white; padding: 0; }}
              .container {{ box-shadow: none; }}
              .metric-card {{ break-inside: avoid; }}
            }}
            @media (max-width: 768px) {{
              .metrics-grid {{ grid-template-columns: 1fr; }}
              .header h1 {{ font-size: 2rem; }}
              .content {{ padding: 20px; }}
            }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="header">
              <h1>🏭 Relatório Executivo DSTech</h1>
              <div class="period">📅 Período: {start_dt.strftime('%d/%m/%Y')} - {end_dt.strftime('%d/%m/%Y')}</div>
              <div class="period">⏰ Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M')}</div>
            </div>
            <div class="content">
              <div class="metrics-grid">
                <div class="metric-card production">
                  <div class="metric-value">{prod_kg:,.0f}</div>
                  <div class="metric-label">📦 Quilos Produzidos</div>
                </div>
                <div class="metric-card cycles">
                  <div class="metric-value">{cycles:,}</div>
                  <div class="metric-label">🔄 Ciclos Realizados</div>
                </div>
                <div class="metric-card water">
                  <div class="metric-value">{water_l:,.0f}</div>
                  <div class="metric-label">💧 Litros de Água</div>
                </div>
                <div class="metric-card chemicals">
                  <div class="metric-value">{chemicals_kg:,.0f}</div>
                  <div class="metric-label">🧪 Quilos de Químicos</div>
                </div>
              </div>
              
              <div class="section">
                <div class="section-header">📊 Resumo Executivo Detalhado</div>
                <div class="section-content">
                  <table class="summary-table">
                    <thead>
                      <tr><th>Métrica</th><th>Valor</th><th>Unidade</th></tr>
                    </thead>
                    <tbody>
                      <tr><td>🏭 Produção Total</td><td>{prod_kg:,.0f}</td><td>kg</td></tr>
                      <tr><td>🔄 Ciclos Realizados</td><td>{cycles:,}</td><td>ciclos</td></tr>
                      <tr><td>📈 Produção Média Diária</td><td>{extract_numeric_html(s['production_summary'].get('daily_avg', 0)):,.0f}</td><td>kg/dia</td></tr>
                      <tr><td>⚖️ Peso Médio por Ciclo</td><td>{extract_numeric_html(s['production_summary'].get('avg_weight', 0)):,.1f}</td><td>kg/ciclo</td></tr>
                      <tr><td>💧 Consumo Total de Água</td><td>{water_l:,.0f}</td><td>L</td></tr>
                      <tr><td>🌊 Eficiência Hídrica</td><td>{s['consumption_summary'].get('water_per_kg', '0 L/kg')}</td><td>-</td></tr>
                      <tr><td>🧪 Consumo Total de Químicos</td><td>{chemicals_kg:,.0f}</td><td>kg</td></tr>
                      <tr><td>⚗️ Eficiência Química</td><td>{s['consumption_summary'].get('chemicals_per_kg', '0 kg/kg')}</td><td>-</td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
              
              <div class="section">
                <div class="section-header">👥 Produção por Cliente</div>
                <div class="section-content">
                  {df_html(datasets['production_by_client'])}
                </div>
              </div>
              
              <div class="section">
                <div class="section-header">📅 Produção Diária</div>
                <div class="section-content">
                  {df_html(datasets['daily_production'])}
                </div>
              </div>
              
              <div class="section">
                <div class="section-header">💧🧪 Consumo Diário (Água & Químicos)</div>
                <div class="section-content">
                  {df_html(datasets['water_chemicals_daily'])}
                </div>
              </div>
              
              <div class="section">
                <div class="section-header">👥 Top 10 Clientes</div>
                <div class="section-content">
                  {df_html(datasets['production_by_client'].head(10))}
                </div>
              </div>
              
              <div class="footer">
                <p>📋 Relatório gerado automaticamente pelo sistema DSTech</p>
                <p>🕒 {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}</p>
              </div>
            </div>
          </div>
        </body>
        </html>
    """
    
    def df_html(df):
        if isinstance(df, pd.DataFrame) and not df.empty:
            df_formatted = df.copy()
            for col in df_formatted.columns:
                if df_formatted[col].dtype in ['float64', 'int64']:
                    df_formatted[col] = df_formatted[col].apply(lambda x: f"{x:,.2f}" if isinstance(x, float) else f"{x:,}")
            return df_formatted.to_html(index=False, classes='table', escape=False)
        return '<p class="no-data">Sem dados no período.</p>'
    
    return html.Div([
        html.Div([
            html.H1("🏭 Relatório Executivo DSTech", className="text-center mb-4"),
            html.P(f"📅 Período: {start_dt.strftime('%d/%m/%Y')} - {end_dt.strftime('%d/%m/%Y')}", className="text-center text-muted mb-4"),
            
            # Métricas principais
            dbc.Row([
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H3(f"{prod_kg:,.0f}", className="text-primary"),
                            html.P("📦 Quilos Produzidos", className="mb-0")
                        ])
                    ], className="mb-3")
                ], md=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H3(f"{cycles:,}", className="text-info"),
                            html.P("🔄 Ciclos Realizados", className="mb-0")
                        ])
                    ], className="mb-3")
                ], md=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H3(f"{water_l:,.0f}", className="text-success"),
                            html.P("💧 Litros de Água", className="mb-0")
                        ])
                    ], className="mb-3")
                ], md=3),
                dbc.Col([
                    dbc.Card([
                        dbc.CardBody([
                            html.H3(f"{chemicals_kg:,.0f}", className="text-warning"),
                            html.P("🧪 Quilos de Químicos", className="mb-0")
                        ])
                    ], className="mb-3")
                ], md=3),
            ]),
            
            # Tabela de resumo
            html.H4("📊 Resumo Detalhado", className="mt-4 mb-3"),
            dbc.Table([
                html.Thead([
                    html.Tr([
                        html.Th("Métrica"),
                        html.Th("Valor"),
                        html.Th("Unidade")
                    ])
                ]),
                html.Tbody([
                    html.Tr([html.Td("🏭 Produção Total"), html.Td(f"{prod_kg:,.0f}"), html.Td("kg")]),
                    html.Tr([html.Td("🔄 Ciclos Realizados"), html.Td(f"{cycles:,}"), html.Td("ciclos")]),
                    html.Tr([html.Td("💧 Consumo de Água"), html.Td(f"{water_l:,.0f}"), html.Td("L")]),
                    html.Tr([html.Td("🧪 Consumo de Químicos"), html.Td(f"{chemicals_kg:,.0f}"), html.Td("kg")]),
                    html.Tr([html.Td("🌊 Eficiência Hídrica"), html.Td(s['consumption_summary'].get('water_per_kg', '0 L/kg')), html.Td("-")]),
                    html.Tr([html.Td("⚗️ Eficiência Química"), html.Td(s['consumption_summary'].get('chemicals_per_kg', '0 kg/kg')), html.Td("-")]),
                ])
            ], striped=True, bordered=True, hover=True),
            
            # Top 10 Clientes
            html.H4("👥 Top 10 Clientes por Produção", className="mt-4 mb-3"),
            html.Div(id="client-table-content")
        ], className="container-fluid p-4")
    ])

def create_config_tab():
    """Aba de configuração mínima (placeholder)."""
    return html.Div([
        html.H5("Configurações"),
        html.P("Ajustes do sistema em breve.")
    ])
# Layout principal do dashboard
def create_main_layout():
    return dbc.Container([
        # Header moderno e melhorado
        dbc.Row([
            dbc.Col([
                html.Div([
                    # Logo e título principal
                    html.Div([
                        html.Img(src="/assets/logodstech.png", 
                                style={'height': '45px', 'width': 'auto', 'margin-right': '15px'}),
                        html.Div([
                            html.H2("Dashboard Industrial", 
                                   style={
                                       'font-weight': '600', 
                                       'font-size': 'clamp(1.1rem, 3vw, 1.8rem)',
                                       'color': '#2c3e50',
                                       'margin': '0',
                                       'text-shadow': '0 1px 2px rgba(0,0,0,0.1)'
                                   }),
                            html.P("Sistema de Monitoramento Avançado", 
                                  style={
                                      'font-size': 'clamp(0.8rem, 1.8vw, 1rem)',
                                      'color': '#7f8c8d',
                                      'margin': '0',
                                      'font-weight': '400'
                                  })
                        ])
                    ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'center', 'flex-wrap': 'wrap'})
                ])
            ], xs=12, sm=7, md=8, lg=8, xl=8),
            
            # Status e controles
            dbc.Col([
                html.Div([
                    # Indicadores de status
                    html.Div([
                        dbc.Badge("🟢 Sistema Online", color="success", className="me-2 px-3 py-2", 
                                 style={'font-size': '0.9rem', 'font-weight': '500'}),
                        html.Span(id='last-update-header', 
                                 style={'font-size': '0.8rem', 'color': '#6c757d'})
                    ], className="mb-2"),
                    
                    # Botão de ação
                    html.Div([
                        dbc.Button("🚪 Sair", id="logout-button", 
                                  color="outline-danger", size="sm",
                                  style={'border-radius': '20px'})
                    ])
                ], className="text-end")
            ], xs=12, sm=5, md=4, lg=4, xl=4)
        ], className="mb-4", style={
            'padding': '1.2rem 1.5rem', 
            'background': 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 50%, #e9ecef 100%)',
            'border-radius': '15px',
            'box-shadow': '0 4px 20px rgba(0,0,0,0.08)',
            'margin-bottom': '2rem',
            'border': '1px solid rgba(255,255,255,0.8)'
        }),
        
        # Elementos globais ocultos para callbacks (mantém IDs existentes)
        html.Div([
            dcc.DatePickerRange(
                id='date-picker',
                start_date=datetime.now() - timedelta(days=7),
                end_date=datetime.now(),
                display_format='DD/MM/YYYY'
            ),
            html.Button(id='refresh-button'),
            html.Div(id='last-update')
        ], style={'display': 'none'}),
        
        # Tabs principais com design premium
        dbc.Tabs([
            dbc.Tab(label="📊 Resumo Executivo", tab_id="resumo", 
                   tab_style={
                       'border-radius': '12px 12px 0 0', 
                       'margin-right': '8px',
                       'border': '1px solid #dee2e6',
                       'background': 'linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%)'
                   }),
            dbc.Tab(label="📊 Gráficos", tab_id="alarmes",
                   tab_style={
                       'border-radius': '12px 12px 0 0', 
                       'margin-right': '8px',
                       'border': '1px solid #dee2e6',
                       'background': 'linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%)'
                   }),
            dbc.Tab(label="📋 Relatórios", tab_id="relatorios",
                   tab_style={
                       'border-radius': '12px 12px 0 0', 
                       'margin-right': '8px',
                       'border': '1px solid #dee2e6',
                       'background': 'linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%)'
                   }),
            dbc.Tab(label="⚙️ Configurações", tab_id="config",
                   tab_style={
                       'border-radius': '12px 12px 0 0',
                       'border': '1px solid #dee2e6',
                       'background': 'linear-gradient(180deg, #ffffff 0%, #f8f9fa 100%)'
                   })
        ], id="main-tabs", active_tab="resumo", className="mb-4", 
           style={
               'box-shadow': '0 3px 15px rgba(0,0,0,0.08)',
               'background': '#ffffff',
               'border-radius': '12px',
               'padding': '0.5rem'
           }),
        
        # Conteúdo das tabs com container elegante
        html.Div(id="tab-content", style={
            'background': '#ffffff',
            'border-radius': '12px',
            'box-shadow': '0 2px 12px rgba(0,0,0,0.06)',
            'padding': '1.5rem',
            'margin-top': '1rem',
            'border': '1px solid rgba(0,0,0,0.05)'
        }),
        
        # Componentes auxiliares
        dcc.Interval(id='interval-component', interval=1800*1000, n_intervals=0)  # 30 minutos
        
    ], fluid=True)

# Layout da aplicação
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    dcc.Store(id='session-store'),
    dcc.Store(id='data-store'),
    html.Div(id='page-content')
])

# Callbacks principais
@app.callback(Output('page-content', 'children'),
              Input('url', 'pathname'),
              State('session-store', 'data'))
def display_page(pathname, session_data):
    if session_data and session_data.get('authenticated'):
        return create_main_layout()
    else:
        return login_layout

@app.callback([Output('session-store', 'data'),
               Output('login-alert', 'children'),
               Output('url', 'pathname')],
              Input('login-button', 'n_clicks'),
              [State('username', 'value'),
               State('password', 'value')])
def login_user(n_clicks, username, password):
    if n_clicks and username and password:
        password_hash = hashlib.md5(password.encode()).hexdigest()
        if username in USERS and USERS[username]['password'] == password_hash:
            return {'authenticated': True, 'username': username}, '', '/dashboard'
        else:
            alert = dbc.Alert("❌ Usuário ou senha incorretos!", color="danger")
            return {}, alert, '/'
    return {}, '', '/'

@app.callback([Output('session-store', 'data', allow_duplicate=True),
               Output('url', 'pathname', allow_duplicate=True)],
              Input('logout-button', 'n_clicks'),
              prevent_initial_call=True)
def logout_user(n_clicks):
    if n_clicks:
        return {}, '/'
    return {}, '/dashboard'

@app.callback(Output('last-update', 'children'),
              Input('interval-component', 'n_intervals'))
def update_timestamp(n):
    return f"Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"

# Callback principal para conteúdo das tabs
@app.callback(Output('tab-content', 'children'),
              [Input('main-tabs', 'active_tab')],
              [State('date-picker', 'start_date'),
               State('date-picker', 'end_date'),
               State('refresh-button', 'n_clicks'),
               State('interval-component', 'n_intervals')])
def render_tab_content(active_tab, start_date, end_date, refresh_clicks, n_intervals):
    try:
        print(f"🔄 CALLBACK TAB EXECUTADO! active_tab={active_tab}, start_date={start_date}, end_date={end_date}")
        
        # Valores padrão se None
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=7)).isoformat()
        if end_date is None:
            end_date = datetime.now().isoformat()
            
        if active_tab == "resumo":
            return create_resumo_tab(start_date, end_date)
        elif active_tab == "alarmes":
            return create_alarmes_tab(start_date, end_date)
        elif active_tab == "relatorios":
            return create_relatorios_tab(start_date, end_date)
    except Exception as e:
        print(f"❌ ERRO NO CALLBACK TAB: {str(e)}")
        return html.Div([
            dbc.Alert([
                html.H4("⚠️ Erro ao Carregar Conteúdo", className="alert-heading"),
                html.P(f"Erro: {str(e)}"),
                html.P("Tente atualizar a página ou selecionar outra aba.")
            ], color="danger")
        ])
        
    if active_tab == "config":
        return create_config_tab()
    
    return html.Div("Selecione uma aba")

# Sincroniza o DatePicker visível com o global oculto usado pelos callbacks
@app.callback(
    [Output('date-picker', 'start_date'), Output('date-picker', 'end_date')],
    [Input('visible-date-picker', 'start_date'), Input('visible-date-picker', 'end_date')]
)
def sync_visible_datepicker_to_global(start_date, end_date):
    return start_date, end_date

# Atualiza os rótulos do período selecionado (não afeta os KPIs de 'Hoje')
@app.callback(
    [Output('kg-periodo-label', 'children', allow_duplicate=True),
     Output('agua-periodo-label', 'children', allow_duplicate=True),
     Output('quimicos-periodo-label', 'children', allow_duplicate=True),
     Output('eficiencia-periodo-label2', 'children', allow_duplicate=True)],
    [Input('visible-date-picker', 'start_date'),
     Input('visible-date-picker', 'end_date')],
    prevent_initial_call='initial_duplicate'
)
def update_period_labels(start_date, end_date):
    try:
        from datetime import datetime
        if start_date and end_date:
            if isinstance(start_date, str):
                start_dt = datetime.fromisoformat(str(start_date))
            else:
                start_dt = start_date
            if isinstance(end_date, str):
                end_dt = datetime.fromisoformat(str(end_date))
            else:
                end_dt = end_date
            label = f"{start_dt.strftime('%d/%m/%Y')} a {end_dt.strftime('%d/%m/%Y')}"
        else:
            label = "Últimos 7 dias"
        return label, label, label, label
    except Exception:
        return "Últimos 7 dias", "Últimos 7 dias", "Últimos 7 dias", "Últimos 7 dias"

# Callbacks para gráficos de tendências
@app.callback(Output('temp-trend-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_temp_trend_chart(start_date, end_date, n_clicks, n_intervals):
    return create_temperature_trend_chart(start_date, end_date)

@app.callback(Output('sensors-trend-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_sensors_trend_chart(start_date, end_date, n_clicks, n_intervals):
    return create_sensors_trend_chart(start_date, end_date)

# Callbacks para gráficos com filtros de data
@app.callback(Output('efficiency-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_efficiency_chart(start_date, end_date, n_clicks, n_intervals):
    return create_efficiency_chart(start_date, end_date)

@app.callback(Output('water-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_water_chart(start_date, end_date, n_clicks, n_intervals):
    return create_water_consumption_chart(start_date, end_date)

# Callbacks para gráficos na aba Gráficos - COM FILTRO PRÓPRIO
@app.callback(Output('charts-efficiency-chart', 'figure'),
              [Input('charts-date-picker', 'start_date'),
               Input('charts-date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_charts_efficiency_chart(start_date, end_date, n_clicks, n_intervals):
    return create_efficiency_chart(start_date, end_date)

@app.callback(Output('charts-water-chart', 'figure'),
              [Input('charts-date-picker', 'start_date'),
               Input('charts-date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_charts_water_chart(start_date, end_date, n_clicks, n_intervals):
    return create_water_consumption_chart(start_date, end_date)

@app.callback(Output('charts-trend-analysis-chart', 'figure'),
              [Input('charts-date-picker', 'start_date'),
               Input('charts-date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_charts_trend_analysis_chart(start_date, end_date, n_clicks, n_intervals):
    return create_trend_analysis_chart(start_date, end_date)

@app.callback(Output('charts-top-alarms-chart', 'figure'),
              [Input('charts-date-picker', 'start_date'),
               Input('charts-date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_charts_top_alarms_chart(start_date, end_date, n_clicks, n_intervals):
    return create_top_alarms_chart(start_date, end_date)

@app.callback(Output('charts-active-alarms-table', 'children'),
              [Input('charts-date-picker', 'start_date'),
               Input('charts-date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_charts_active_alarms_table(start_date, end_date, n_clicks, n_intervals):
    return create_active_alarms_table()

@app.callback(Output('chemical-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_chemical_chart(start_date, end_date, n_clicks, n_intervals):
    return create_chemical_consumption_chart(start_date, end_date)

@app.callback(Output('top-alarms-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_top_alarms_chart(start_date, end_date, n_clicks, n_intervals):
    return create_top_alarms_chart(start_date, end_date)

# (Removido) Callback de análise de alarmes - card não existe mais

@app.callback(Output('production-client-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_production_client_chart(start_date, end_date, n_clicks, n_intervals):
    return create_production_by_client_chart(start_date, end_date)

@app.callback(Output('production-program-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_production_program_chart(start_date, end_date, n_clicks, n_intervals):
    return create_production_by_program_chart(start_date, end_date)

# Callbacks para filtros de produção
# Callback para mostrar/ocultar date-picker personalizado
@app.callback(Output('custom-date-container', 'style'),
              Input('period-filter-dropdown', 'value'))
def toggle_custom_date_picker(period_value):
    if period_value == 'custom':
        return {'display': 'block'}
    return {'display': 'none'}

@app.callback([Output('client-analysis-chart', 'figure'),
               Output('production-client-chart', 'figure', allow_duplicate=True),
               Output('production-program-chart', 'figure', allow_duplicate=True)],
              [Input('client-filter-dropdown', 'value'),
               Input('period-filter-dropdown', 'value'),
               Input('refresh-production-btn', 'n_clicks'),
               Input('production-date-picker', 'start_date'),
               Input('production-date-picker', 'end_date')],
              prevent_initial_call=True)
def update_production_charts(client_filter, period_filter, n_clicks, custom_start, custom_end):
    print(f"DEBUG: Filtros recebidos - Cliente: {client_filter}, Período: {period_filter}")
    
    # Calcular datas baseado no período
    if period_filter and period_filter != 'custom':
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=int(period_filter))
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')
        print(f"DEBUG: Datas calculadas - Início: {start_date}, Fim: {end_date}")
    elif period_filter == 'custom' and custom_start and custom_end:
        # Usar datas personalizadas
        start_date = custom_start
        end_date = custom_end
        print(f"DEBUG: Datas personalizadas - Início: {start_date}, Fim: {end_date}")
    else:
        # Padrão: últimos 30 dias
        from datetime import datetime, timedelta
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=30)
        start_date = start_date.strftime('%Y-%m-%d')
        end_date = end_date.strftime('%Y-%m-%d')
        print(f"DEBUG: Datas padrão - Início: {start_date}, Fim: {end_date}")
    
    # Atualizar gráficos com filtros
    try:
        client_analysis = create_client_analysis_chart(client_filter if client_filter != 'all' else None)
        production_client = create_production_by_client_chart(start_date, end_date, client_filter if client_filter != 'all' else None)
        production_program = create_production_by_program_chart(start_date, end_date, client_filter if client_filter != 'all' else None)
        print("DEBUG: Gráficos atualizados com sucesso")
        return client_analysis, production_client, production_program
    except Exception as e:
        print(f"ERRO: {str(e)}")
        # Retornar gráficos padrão em caso de erro
        return create_client_analysis_chart(), create_production_by_client_chart(), create_production_by_program_chart()



# Função para obter detalhes dos químicos
def get_chemical_details():
    """Obtém detalhes dos químicos utilizados da tabela Rel_Quimico"""
    query = """
    SELECT 
        'Químico Q1 (Detergente Principal)' as tipo_quimico,
        SUM("Q1") as quantidade_total,
        COUNT(*) as registros,
        AVG("Q1") as media_por_registro
    FROM "Rel_Quimico" 
    WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '7 days'
      AND "Q1" > 0
    
    UNION ALL
    
    SELECT 
        'Químico Q2 (Detergente Secundário)' as tipo_quimico,
        SUM("Q2") as quantidade_total,
        COUNT(*) as registros,
        AVG("Q2") as media_por_registro
    FROM "Rel_Quimico" 
    WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '7 days'
      AND "Q2" > 0
    
    UNION ALL
    
    SELECT 
        'Químico Q3 (Alvejante)' as tipo_quimico,
        SUM("Q3") as quantidade_total,
        COUNT(*) as registros,
        AVG("Q3") as media_por_registro
    FROM "Rel_Quimico" 
    WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '7 days'
      AND "Q3" > 0
    
    UNION ALL
    
    SELECT 
        'Químico Q4 (Amaciante)' as tipo_quimico,
        SUM("Q4") as quantidade_total,
        COUNT(*) as registros,
        AVG("Q4") as media_por_registro
    FROM "Rel_Quimico" 
    WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '7 days'
      AND "Q4" > 0
    
    UNION ALL
    
    SELECT 
        'Químico Q5 (Neutralizante)' as tipo_quimico,
        SUM("Q5") as quantidade_total,
        COUNT(*) as registros,
        AVG("Q5") as media_por_registro
    FROM "Rel_Quimico" 
    WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '7 days'
      AND "Q5" > 0
    
    ORDER BY quantidade_total DESC
    """
    
    try:
        df = execute_query(query)
        if df.empty:
            return []
        
        # Converter para formato esperado pelos relatórios
        result = []
        for _, row in df.iterrows():
            result.append({
                'tipo_quimico': row['tipo_quimico'],
                'quantidade_kg': row['quantidade_total'] / 1000,  # Converter para kg se necessário
                'ciclos_utilizados': row['registros'],
                'media_por_ciclo': row['media_por_registro'] / 1000 if row['media_por_registro'] else 0
            })
        
        return result
    except Exception as e:
        print(f"Erro ao obter detalhes dos químicos: {e}")
        return []

# Callback para atualizar rótulos dinâmicos dos KPIs (somente IDs existentes)
@app.callback(
    [
        Output('kg-periodo-label', 'children'),
        Output('agua-periodo-label', 'children'),
        Output('quimicos-periodo-label', 'children'),
        Output('eficiencia-periodo-label2', 'children')
    ],
    [
        Input('date-picker', 'start_date'),
        Input('date-picker', 'end_date')
    ]
)
def update_kpi_labels(start_date, end_date):
    """Atualiza os rótulos dos KPIs baseado no filtro de data ativo"""
    
    if start_date and end_date:
        # Filtro personalizado ativo
        from datetime import datetime
        try:
            start_dt = datetime.fromisoformat(start_date).date()
            end_dt = datetime.fromisoformat(end_date).date()
            
            if start_dt == end_dt:
                periodo_label = f"Dia {start_dt.strftime('%d/%m/%Y')}"
            else:
                periodo_label = f"{start_dt.strftime('%d/%m')} a {end_dt.strftime('%d/%m/%Y')}"
        except:
            periodo_label = "Período selecionado"
    else:
        # Filtro padrão
        periodo_label = "Últimos 7 dias"
    
    return periodo_label, periodo_label, periodo_label, periodo_label

# Callback para atualizar KPIs do período selecionado
@app.callback(
    [
        Output('kg-periodo-value', 'children'),
        Output('agua-periodo-value', 'children'),
        Output('quimicos-periodo-value', 'children'),
        Output('eficiencia-periodo-value', 'children')
    ],
    [
        Input('visible-date-picker', 'start_date'),
        Input('visible-date-picker', 'end_date')
    ],
    prevent_initial_call=False
)
def update_periodo_kpis(start_date, end_date):
    """Atualiza os KPIs do período selecionado"""
    
    print(f"📅 CALLBACK PERÍODO EXECUTADO! start_date={start_date}, end_date={end_date}")
    
    # Converter strings de data para objetos date
    if start_date:
        filter_start = datetime.fromisoformat(start_date).date()
    else:
        filter_start = None
        
    if end_date:
        filter_end = datetime.fromisoformat(end_date).date()
    else:
        filter_end = None
    
    # Obter KPIs atualizados
    try:
        kpis = get_operational_kpis(filter_start, filter_end, None)
        print(f"📊 KPIs Período obtidos: {kpis.get('quilos_lavados_periodo', '0')} kg")
    except Exception as e:
        print(f"❌ Erro ao obter KPIs do período: {e}")
        kpis = {}
    
    # Retornar valores do período selecionado
    return (
        f"{kpis.get('quilos_lavados_periodo', '0')} kg",
        f"{kpis.get('litros_agua_periodo', '0')} L",
        f"{kpis.get('ml_quimicos_periodo', 0):.0f} ml",
        f"{kpis.get('eficiencia_media', 0):.1f}%"
    )

# Callback para atualizar KPIs de hoje (dia atual)
@app.callback(
    [
        Output('kg-hoje-value', 'children'),
        Output('agua-hoje-value', 'children'),
        Output('alarmes-ativos-value', 'children'),
        # Novos outputs para os KPIs adicionais
        Output('batchs-hoje-value', 'children'),
        Output('peso-medio-hoje-value', 'children'),
        Output('consumo-medio-hoje-value', 'children'),
        Output('eficiencia-hoje-value', 'children'),
        # Novos outputs para alarmes
        Output('top5-alarms-today', 'children'),
        Output('top5-alarms-period', 'children')
    ],
    [
        Input('visible-date-picker', 'start_date'),
        Input('visible-date-picker', 'end_date')
    ],
    prevent_initial_call=False
)
def update_kpis(start_date, end_date):
    """Atualiza os KPIs de HOJE (dia atual) - sempre independente do filtro"""
    
    print(f"🔄 CALLBACK HOJE EXECUTADO! (ignora filtros para mostrar sempre o dia atual)")
    
    # Obter KPIs sempre sem filtro para mostrar dados de HOJE
    try:
        kpis = get_operational_kpis(None, None, None)  # Sem filtro = dados de hoje
        print(f"📊 KPIs HOJE obtidos: {kpis.get('quilos_lavados_hoje', '0')} kg")
    except Exception as e:
        print(f"❌ Erro ao obter KPIs de hoje: {e}")
        kpis = {}
    
    # Calcular alarmes do dia (00:00 até agora) diretamente no banco
    try:
        dbm = DatabaseManager()
        from datetime import datetime, timedelta
        today = datetime.now().date()
        start_today = datetime.combine(today, datetime.min.time())
        end_today = datetime.combine(today + timedelta(days=1), datetime.min.time())
        alarms_today_df = dbm.execute_query(
            'SELECT COUNT(DISTINCT "Al_Message") AS cnt FROM "ALARMHISTORY" WHERE "Al_Start_Time" >= %s AND "Al_Start_Time" < %s AND "Al_Norm_Time" IS NULL',
            (start_today, end_today)
        )
        alarms_today = int(alarms_today_df.iloc[0]['cnt']) if not alarms_today_df.empty else 0
    except Exception:
        alarms_today = kpis.get('alarmes_ativos', 0)

    # Usar o consumo médio já calculado no KPI (litros_por_kg_hoje)
    consumo_medio = kpis.get('litros_por_kg_hoje', 0.0)

    # Buscar Top 5 Alarmes do Dia
    top5_alarms_today = get_top5_alarms_today()
    
    # Buscar Top 5 Alarmes do Período (usando filtro de data)
    top5_alarms_period = get_top5_alarms_period(start_date, end_date)

    # Retornar sempre dados do dia atual (HOJE)
    return (
        f"{kpis.get('quilos_lavados_hoje', '0')} kg",     # Dia atual
        f"{kpis.get('litros_agua_hoje', '0')} L",        # Dia atual
        str(alarms_today),                                 # Alarmes do dia de hoje
        # Novos KPIs
        f"{kpis.get('ciclos_hoje', 0)}",                # Batchs (quantidade de cargas)
        f"{kpis.get('peso_medio_hoje', 0):.2f} kg",     # Peso Médio
        f"{consumo_medio:.2f} L/kg",                     # Consumo Médio (L/kg)
        f"{kpis.get('eficiencia_media', 0):.1f}%",       # Eficiência
        # Top 5 Alarmes
        top5_alarms_today,                               # Top 5 Alarmes do Dia
        top5_alarms_period                               # Top 5 Alarmes do Período
    )

def get_top5_alarms_today():
    """Busca os top 5 alarmes do dia atual"""
    try:
        dbm = DatabaseManager()
        from datetime import datetime, timedelta
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Alinhar à origem: contar somente linhas de reconhecimento (ack)
        # Requerer que ambos tempos sejam maiores que o início do dia atual
        query = """
        SELECT 
            "Al_Tag",
            "Al_Message" as descricao,
            COUNT(*) as total_ocorrencias,
            MAX("Al_Start_Time") as ultima_ocorrencia
        FROM "ALARMHISTORY" 
        WHERE "Al_Start_Time" > CURRENT_DATE AND "Al_Norm_Time" > CURRENT_DATE
        GROUP BY "Al_Tag", "Al_Message"
        ORDER BY COUNT(*) DESC
        LIMIT 5
        """
        
        df = dbm.execute_query(query)
        
        if df.empty:
            return html.Div([
                html.P("Nenhum alarme registrado hoje", className="text-muted text-center mb-0")
            ])
        
        # Criar lista de alarmes compacta
        alarm_items = []
        for idx, row in df.iterrows():
            ultima = row['ultima_ocorrencia'].strftime('%H:%M') if row['ultima_ocorrencia'] else 'N/A'
            alarm_items.append(
                html.Div([
                    html.Strong(f"{row['total_ocorrencias']}x", className="text-danger me-2"),
                    html.Span(f"{row['descricao']}", className="flex-grow-1"),
                    html.Small(f"{ultima}", className="text-muted ms-2")
                ], className="d-flex align-items-center mb-1 py-1 px-2 border-start border-danger border-2 bg-light small")
            )
        
        return html.Div(alarm_items)
        
    except Exception as e:
        print(f"❌ Erro ao buscar top 5 alarmes do dia: {e}")
        return html.Div([
            html.P("Erro ao carregar alarmes do dia", className="text-danger text-center mb-0")
        ])

def get_top5_alarms_period(start_date, end_date):
    """Busca os top 5 alarmes do período selecionado"""
    try:
        dbm = DatabaseManager()
        from datetime import datetime
        
        # Se não há filtro de data, usar últimos 7 dias
        if not start_date or not end_date:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(days=7)
        else:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        
        # Contar apenas reconhecimentos (acks) dentro do período selecionado
        # Ambos os campos dentro do intervalo [start_dt, end_dt)
        query = """
        SELECT 
            "Al_Tag",
            "Al_Message" as descricao,
            COUNT(*) as total_ocorrencias,
            MAX("Al_Start_Time") as ultima_ocorrencia
        FROM "ALARMHISTORY" 
        WHERE "Al_Start_Time" >= %s AND "Al_Start_Time" < %s
          AND "Al_Norm_Time"  >= %s AND "Al_Norm_Time"  < %s
        GROUP BY "Al_Tag", "Al_Message"
        ORDER BY COUNT(*) DESC
        LIMIT 5
        """
        
        df = dbm.execute_query(query, (start_dt, end_dt, start_dt, end_dt))
        
        if df.empty:
            return html.Div([
                html.P("Nenhum alarme no período", className="text-muted text-center mb-0")
            ])
        
        # Criar lista de alarmes compacta
        alarm_items = []
        for idx, row in df.iterrows():
            ultima = row['ultima_ocorrencia'].strftime('%d/%m %H:%M') if row['ultima_ocorrencia'] else 'N/A'
            alarm_items.append(
                html.Div([
                    html.Span(f"{row['descricao']}", className="flex-grow-1"),
                    html.Small(f"{ultima}", className="text-muted ms-2")
                ], className="d-flex align-items-center mb-1 py-1 px-2 border-start border-warning border-2 bg-light small")
            )
        
        return html.Div(alarm_items)
        
    except Exception as e:
        print(f"❌ Erro ao buscar top 5 alarmes do período: {e}")
        return html.Div([
            html.P("Erro ao carregar alarmes do período", className="text-danger text-center mb-0")
        ])

def get_client_performance_comparison(start_date, end_date):
    """Busca dados de performance por cliente com dados reais e simulados"""
    try:
        db_manager = DatabaseManager()
        
        query = """
        SELECT 
            'Cliente ' || CAST("C1" AS TEXT) as client_name,
            CAST("C1" AS INTEGER) as client_id,
            SUM("C2") AS total_kg,
            0 AS total_water_liters,
            0.0 AS water_efficiency_l_per_kg
        FROM "Rel_Carga"
        WHERE "Time_Stamp" >= %s AND "Time_Stamp" <= %s
          AND "C2" > 0
        GROUP BY "C1"
        ORDER BY total_kg DESC
        LIMIT 50
        """
        
        df = db_manager.execute_query(query, (start_date, end_date))
        return df
        
    except Exception as e:
        print(f"Erro ao buscar dados de clientes: {e}")
        # Em caso de erro, retornar DataFrame vazio para não exibir nomes falsos
        import pandas as pd
        return pd.DataFrame(columns=['client_name', 'client_id', 'total_kg', 'total_water_liters', 'water_efficiency_l_per_kg'])


# Funções para criar conteúdo das tabs
def create_resumo_tab(start_date, end_date, client_filter='all'):
    """Aba de resumo executivo com KPIs reais"""
    
    # KPIs serão preenchidos pelo callback - usar placeholders
    kpis = {
        'quilos_lavados_hoje': '...',
        'ciclos_hoje': 0,
        'litros_agua_hoje': '...',
        'litros_por_kg_hoje': 0,
        'kg_quimicos_hoje': 0,
        'kg_quimicos_por_kg_hoje': 0,
        'alarmes_ativos': '...',
        'quilos_lavados_semana': '...',
        'ciclos_semana': 0,
        'eficiencia_media': 0,
        'quilos_lavados_hoje_raw': 0
    }
    
    # Normalizar datas recebidas para popular o DatePicker visível sem resetar
    try:
        if isinstance(start_date, str) and start_date:
            start_dt_vis = datetime.fromisoformat(start_date)
        elif isinstance(start_date, datetime):
            start_dt_vis = start_date
        else:
            start_dt_vis = datetime.now() - timedelta(days=7)
        if isinstance(end_date, str) and end_date:
            end_dt_vis = datetime.fromisoformat(end_date)
        elif isinstance(end_date, datetime):
            end_dt_vis = end_date
        else:
            end_dt_vis = datetime.now()
    except Exception:
        start_dt_vis = datetime.now() - timedelta(days=7)
        end_dt_vis = datetime.now()

    # Seção sem título desnecessário
    header_section = html.Div()  # Vazio, sem título
    
    # Cards de KPIs com dados reais melhorados
    kpi_cards = html.Div([
        # Primeira linha de KPIs - Produção e Água
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("📦", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("🔄 Carregando...", className="text-primary mb-0", id="kg-hoje-value"),
                                    html.P("Quilos Lavados Hoje", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #28a745',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(40, 167, 69, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f8fff9 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=3, xl=3),  # Responsivo: mobile=1col, tablet=2col, desktop=4col
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("💧", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-info mb-0", id="agua-hoje-value"),
                                    html.P("Água Usada Hoje", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #17a2b8',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(23, 162, 184, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f0fbff 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=3, xl=3),  # Responsivo: mobile=1col, tablet=2col, desktop=4col
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("🧺", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-success mb-0", id="batchs-hoje-value"),
                                    html.P("Batchs (Cargas)", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #ffc107',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(255, 193, 7, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #fffbf0 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=3, xl=3),  # Responsivo: mobile=1col, tablet=2col, desktop=4col
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("🚨", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-danger mb-0", id="alarmes-ativos-value"),
                                    html.P("Alarmes Ativos", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #dc3545',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(220, 53, 69, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #fff5f5 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=3, xl=3)  # Responsivo: mobile=1col, tablet=2col, desktop=4col
        ], className="mb-3"),
        
        # Segunda linha de KPIs - Indicadores de Performance
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("⚖️", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-warning mb-0", id="peso-medio-hoje-value"),
                                    html.P("Peso Médio", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #ffc107',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(255, 193, 7, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #fffbf0 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=4, xl=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("💧", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-info mb-0", id="consumo-medio-hoje-value"),
                                    html.P("Consumo Médio (L/kg)", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #17a2b8',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(23, 162, 184, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f0fbff 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=4, xl=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("⚡", style={'font-size': '2rem', 'margin-right': '0.5rem'}),
                                html.Div([
                                    html.H3("...", className="text-success mb-0", id="eficiencia-hoje-value"),
                                    html.P("Eficiência", className="mb-0 text-muted", style={'font-weight': '500'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Hoje (dia atual)", className="text-primary", style={'font-weight': '500'})
                        ])
                    ])
                ], style={
                    'border-left': '4px solid #28a745',
                    'border-radius': '12px',
                    'box-shadow': '0 4px 15px rgba(40, 167, 69, 0.1)',
                    'transition': 'transform 0.2s ease',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f8fff9 100%)'
                }, className="h-100")
            ], xs=12, sm=6, md=6, lg=4, xl=4)
        ], className="mb-3"),
        
        # Top 5 Alarmes do Dia - RESUMO EXECUTIVO (versão discreta)
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("⚠️", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                            html.H6("Top 5 Alarmes do Dia", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #6c757d 0%, #5a6268 100%)',
                        'color': 'white',
                        'border': 'none',
                        'padding': '0.5rem 1rem'
                    }),
                    dbc.CardBody([
                        html.Div(id='top5-alarms-today')
                    ], style={'padding': '1rem'})
                ], style={
                    'border-radius': '8px',
                    'box-shadow': '0 2px 8px rgba(108, 117, 125, 0.1)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], xs=12, sm=12, md=12, lg=12, xl=12)
        ], className="mb-3"),
        
        # Seção de Período modernizada
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("📅", style={'font-size': '1.8rem', 'margin-right': '0.75rem'}),
                                html.H4("Período de Análise", className="mb-0", style={'color': '#495057'})
                            ], style={'display': 'flex', 'align-items': 'center', 'justify-content': 'center', 'margin-bottom': '1rem'}),
                            dcc.DatePickerRange(
                                id='visible-date-picker',
                                start_date=start_dt_vis.date(),
                                end_date=end_dt_vis.date(),
                                display_format='DD/MM/YYYY',
                                style={'width': '100%', 'font-size': '1rem'}
                            )
                        ])
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'border': '2px solid #e9ecef',
                    'box-shadow': '0 4px 15px rgba(0, 0, 0, 0.08)',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%)',
                    'height': '100%'
                }, className="h-100")
            ], xs=12, sm=12, md=6, lg=4, xl=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("📊", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Top 5 Alarmes do Período", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #fd7e14 0%, #e55a00 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        html.Div(id='top5-alarms-period')
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(253, 126, 20, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden',
                    'height': '100%'
                }, className="h-100")
            ], xs=12, sm=12, md=6, lg=8, xl=8)
        ], className="mb-4"),
        
        # Cards do Período Selecionado - modernizados
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("📦", style={'font-size': '1.8rem', 'margin-right': '0.5rem', 'opacity': '0.8'}),
                                html.Div([
                                    html.H3("...", className="text-success mb-0", id="kg-periodo-value"),
                                    html.P("Quilos Lavados", className="mb-0 text-muted", style={'font-weight': '500', 'font-size': '0.9rem'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Últimos 7 dias", className="text-success", id="kg-periodo-label", style={'font-weight': '600', 'font-size': '0.75rem'})
                        ])
                    ], style={'padding': '1rem'})
                ], style={
                    'border-left': '4px solid #28a745',
                    'border-radius': '8px',
                    'box-shadow': '0 2px 8px rgba(40, 167, 69, 0.12)',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f8fff9 100%)',
                    'border-style': 'solid'
                })
            ], xs=12, sm=6, md=6, lg=3, xl=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("💧", style={'font-size': '1.8rem', 'margin-right': '0.5rem', 'opacity': '0.8'}),
                                html.Div([
                                    html.H3("...", className="text-info mb-0", id="agua-periodo-value"),
                                    html.P("Água Usada", className="mb-0 text-muted", style={'font-weight': '500', 'font-size': '0.9rem'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Últimos 7 dias", className="text-info", id="agua-periodo-label", style={'font-weight': '600', 'font-size': '0.75rem'})
                        ])
                    ], style={'padding': '1rem'})
                ], style={
                    'border-left': '4px solid #17a2b8',
                    'border-radius': '8px',
                    'box-shadow': '0 2px 8px rgba(23, 162, 184, 0.12)',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f0fbff 100%)',
                    'border-style': 'solid'
                })
            ], xs=12, sm=6, md=6, lg=3, xl=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("🧪", style={'font-size': '1.8rem', 'margin-right': '0.5rem', 'opacity': '0.8'}),
                                html.Div([
                                    html.H3("...", className="text-purple mb-0", id="quimicos-periodo-value"),
                                    html.P("Químicos", className="mb-0 text-muted", style={'font-weight': '500', 'font-size': '0.9rem'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Últimos 7 dias", className="text-purple", id="quimicos-periodo-label", style={'font-weight': '600', 'font-size': '0.75rem'})
                        ])
                    ], style={'padding': '1rem'})
                ], style={
                    'border-left': '4px solid #6f42c1',
                    'border-radius': '8px',
                    'box-shadow': '0 2px 8px rgba(111, 66, 193, 0.12)',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #f8f6ff 100%)',
                    'border-style': 'solid'
                })
            ], xs=12, sm=6, md=6, lg=3, xl=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("⚡", style={'font-size': '1.8rem', 'margin-right': '0.5rem', 'opacity': '0.8'}),
                                html.Div([
                                    html.H3("...", className="text-warning mb-0", id="eficiencia-periodo-value"),
                                    html.P("Eficiência Média", className="mb-0 text-muted", style={'font-weight': '500', 'font-size': '0.9rem'})
                                ], style={'flex': '1'})
                            ], style={'display': 'flex', 'align-items': 'center'}),
                            html.Small("Últimos 7 dias", className="text-warning", id="eficiencia-periodo-label2", style={'font-weight': '600', 'font-size': '0.75rem'})
                        ])
                    ], style={'padding': '1rem'})
                ], style={
                    'border-left': '4px solid #ffc107',
                    'border-radius': '8px',
                    'box-shadow': '0 2px 8px rgba(255, 193, 7, 0.12)',
                    'background': 'linear-gradient(135deg, #ffffff 0%, #fffbf0 100%)',
                    'border-style': 'solid'
                })
            ], xs=12, sm=6, md=6, lg=3, xl=3)
        ], className="mb-4")
    ])
        # Seção de Produção (migrada da aba Produção) - Tabela de clientes
    producao_section = html.Div([
        # Tabela de métricas por cliente (clientes reais)
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("📋", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Produção por Cliente", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #6f42c1 0%, #8e44ad 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        html.Div(id='client-metrics-table')
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(111, 66, 193, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], width=12)
        ], className="mb-4"),
    ])

    return html.Div([header_section, kpi_cards, producao_section])

def create_alarmes_tab(start_date, end_date):
    """Aba de gráficos com filtro de período - RESPONSIVA"""
    return html.Div([
        # Header da seção
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Span("📊", style={'font-size': '2rem', 'margin-right': '0.75rem'}),
                    html.H3("Gráficos e Análises", className="mb-0", style={'color': '#495057'})
                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '1.5rem'})
            ], width=12)
        ]),
        
        # Filtro de Período de Análise para a aba Gráficos
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("📅", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Período de Análise", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #6c757d 0%, #495057 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dcc.DatePickerRange(
                            id='charts-date-picker',
                            start_date=start_date,
                            end_date=end_date,
                            display_format='DD/MM/YYYY',
                            style={'width': '100%', 'z-index': '9999', 'position': 'relative'},
                            className='mb-0'
                        )
                    ], style={'padding': '1rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(108, 117, 125, 0.15)',
                    'border': 'none',
                    'overflow': 'visible',
                    'z-index': '1000',
                    'position': 'relative'
                })
            ], width=12)
        ], className="mb-4"),
        
        # Gráficos principais - Eficiência e Consumo de Água
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("⚡", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Eficiência Operacional", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #28a745 0%, #20c997 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dcc.Graph(id='charts-efficiency-chart', 
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '400px'})
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(40, 167, 69, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], xs=12, sm=12, md=12, lg=12, xl=6, className="mb-4"),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("💧", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Eficiência Hídrica - Tendência", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #17a2b8 0%, #20c997 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dcc.Graph(id='charts-water-chart',
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '400px'})
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(23, 162, 184, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], xs=12, sm=12, md=12, lg=12, xl=6)
        ], className="mb-4"),
        
        # Gráfico de Tendência Temporal
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("📈", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Análise de Tendência Temporal", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #28a745 0%, #20c997 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dcc.Graph(id='charts-trend-analysis-chart',
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '550px'})
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(40, 167, 69, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], width=12)
        ], className="mb-4"),
        
        # Gráficos de Alarmes
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("🔝", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Top 10 Alarmes", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #dc3545 0%, #e74c3c 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dcc.Graph(id='charts-top-alarms-chart',
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '400px'})
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(220, 53, 69, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], xs=12, sm=12, md=12, lg=12, xl=6, className="mb-4"),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("⚠️", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Alarmes Ativos", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #ffc107 0%, #f39c12 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        html.Div(id='charts-active-alarms-table')
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(255, 193, 7, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], xs=12, sm=12, md=12, lg=12, xl=6)
        ], className="mb-3")
    ])

# (Removed legacy create_relatorios_tab override)

def create_tendencias_tab(start_date, end_date):
    """Aba de análise de tendências dos sensores - RESPONSIVA"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("🌡️ Temperatura", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_temperature_trend_chart(start_date, end_date), 
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '400px'})
                    ])
                ])
            ], xs=12, sm=12, md=12, lg=12, xl=12)
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Sensores Completo", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_sensors_trend_chart(start_date, end_date),
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '400px'})
                    ])
                ])
            ], xs=12, sm=12, md=12, lg=12, xl=12)
        ])
    ])

def create_producao_tab(start_date, end_date):
    """Aba de análise de produção - conteúdo movido para Resumo"""
    return html.Div([
        dbc.Alert("Conteúdo de Produção movido para a aba Resumo.", color="info")
    ])

def create_executive_dashboard_chart(start_date, end_date):
    """Cria gráfico executivo completo cruzando todos os KPIs principais"""
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go
    
    # Converter strings para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    # Gerar dados simulados para o período
    days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=i) for i in range(days)]
    
    # Dados simulados realistas
    kg_roupas = [1200 + (i * 50) + (i % 3 * 100) for i in range(days)]
    agua_litros = [kg * 3.2 + (i % 2 * 200) for i, kg in enumerate(kg_roupas)]
    quimicos_kg = [kg * 0.004 + (i % 4 * 0.1) for i, kg in enumerate(kg_roupas)]
    eficiencia = [92 + (i % 5 * 2) - (i % 7 * 1) for i in range(days)]
    alarmes = [max(0, 5 - (i % 6)) for i in range(days)]
    
    # Criar subplots com eixos secundários
    fig = make_subplots(
        rows=2, cols=2,
        specs=[
            [{'secondary_y': True}, {'secondary_y': True}],
            [{'secondary_y': True}, {'type': 'indicator'}]
        ],
        vertical_spacing=0.18,
        horizontal_spacing=0.15
    )
    
    # Gráfico 1: Produção vs Eficiência
    fig.add_trace(
        go.Scatter(
            x=dates, y=kg_roupas,
            name='Kg Roupas',
            line=dict(color='#2E86AB', width=3),
            fill='tonexty'
        ),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=eficiencia,
            name='Eficiência (%)',
            line=dict(color='#A23B72', width=2, dash='dot'),
            yaxis='y2'
        ),
        row=1, col=1, secondary_y=True
    )
    
    # Gráfico 2: Água vs Químicos
    fig.add_trace(
        go.Bar(
            x=dates, y=agua_litros,
            name='Água (L)',
            marker_color='#F18F01',
            opacity=0.7
        ),
        row=1, col=2
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=quimicos_kg,
            name='Químicos (kg)',
            line=dict(color='#C73E1D', width=3),
            mode='lines+markers',
            yaxis='y4'
        ),
        row=1, col=2, secondary_y=True
    )
    
    # Gráfico 3: Alarmes vs Produção
    fig.add_trace(
        go.Scatter(
            x=dates, y=alarmes,
            name='Alarmes',
            line=dict(color='#E74C3C', width=2),
            fill='tozeroy',
            fillcolor='rgba(231, 76, 60, 0.2)'
        ),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(
            x=dates, y=[kg/50 for kg in kg_roupas],  # Escalar para visualização
            name='Produção (x50)',
            line=dict(color='#27AE60', width=2, dash='dash'),
            yaxis='y6'
        ),
        row=2, col=1, secondary_y=True
    )
    
    # Gráfico 4: Indicadores Consolidados
    total_kg = sum(kg_roupas)
    total_agua = sum(agua_litros)
    total_quimicos = sum(quimicos_kg)
    media_eficiencia = sum(eficiencia) / len(eficiencia)
    total_alarmes = sum(alarmes)
    
    fig.add_trace(
        go.Indicator(
            mode = "gauge+number+delta",
            value = media_eficiencia,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Eficiência Média (%)"},
            delta = {'reference': 90},
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "#2E86AB"},
                'steps': [
                    {'range': [0, 70], 'color': "#FFE5E5"},
                    {'range': [70, 85], 'color': "#FFF3CD"},
                    {'range': [85, 100], 'color': "#D4EDDA"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 95
                }
            }
        ),
        row=2, col=2
    )
    
    # Configurar layout responsivo
    fig.update_layout(
        height=700,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5,
            font=dict(size=10)
        ),
        margin=dict(t=60, b=40, l=40, r=40),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        # Responsividade
        autosize=True,
        font=dict(size=11),
        # Ajustar espaçamento dos títulos dos subplots
        annotations=[
            dict(
                text="Produção vs Eficiência",
                x=0.225, y=0.95,
                xref='paper', yref='paper',
                showarrow=False,
                font=dict(size=12, color='#2C3E50')
            ),
            dict(
                text="Consumo de Água vs Químicos",
                x=0.775, y=0.95,
                xref='paper', yref='paper',
                showarrow=False,
                font=dict(size=12, color='#2C3E50')
            ),
            dict(
                text="Alarmes vs Produção",
                x=0.225, y=0.45,
                xref='paper', yref='paper',
                showarrow=False,
                font=dict(size=12, color='#2C3E50')
            ),
            dict(
                text="Indicadores Consolidados",
                x=0.775, y=0.45,
                xref='paper', yref='paper',
                showarrow=False,
                font=dict(size=12, color='#2C3E50')
            )
        ]
    )
    
    # Configurar eixos
    fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(128,128,128,0.2)')
    
    # Adicionar anotações com totais
    fig.add_annotation(
        text=f"📦 Total: {total_kg:,.0f} kg<br>💧 Água: {total_agua:,.0f} L<br>🧪 Químicos: {total_quimicos:.1f} kg<br>🚨 Alarmes: {total_alarmes}",
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        align="left",
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="#2C3E50",
        borderwidth=1,
        font=dict(size=12, color="#2C3E50")
    )
    
    return fig

def create_relatorios_tab_legacy(start_date, end_date):
    """[LEGACY] Aba de relatórios executivos antiga (não utilizada)."""
    
    # Converter strings para datetime se necessário
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    # Gerar relatório executivo com período dinâmico
    report = generate_executive_report(start_date, end_date)
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📈 Relatório Executivo Simplificado", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div([
                            html.H6(f"📅 Período: {start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}", className="text-muted mb-3"),
                            
                            # Resumo de Produção
                            html.H5("🏭 Produção", className="text-primary mb-2"),
                            html.Ul([
                                html.Li(f"Total: {report['production_summary']['period_production']} kg"),
                                html.Li(f"Ciclos: {report['production_summary']['period_cycles']}"),
                                html.Li(f"Eficiência: {report['production_summary']['efficiency']}")
                            ], className="mb-3"),
                            
                            # Resumo de Consumos
                            html.H5("💧 Consumos", className="text-info mb-2"),
                            html.Ul([
                                html.Li(f"Água: {report['consumption_summary']['water_period']} L"),
                                html.Li(f"Químicos: {report['consumption_summary']['chemicals_period']}")
                            ], className="mb-3"),
                            
                            # Resumo de Alarmes
                            html.H5("🚨 Alarmes", className="text-warning mb-2"),
                            html.Ul([
                                html.Li(f"Total: {report['alarms_summary']['period_alarms']}"),
                                html.Li(f"Ativos: {report['alarms_summary']['active_alarms']}")
                            ], className="mb-3"),
                            
                            # (Removidos controles legados de exportação duplicados)
                        ])
                    ])
                ])
            ], xs=12, sm=12, md=12, lg=8, xl=8, className="mb-3 mb-lg-0"),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Gráficos Resumo", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_efficiency_chart(),
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '300px'}),
                        html.Hr(),
                        dcc.Graph(figure=create_water_consumption_chart(),
                                 config={'responsive': True, 'displayModeBar': False},
                                 style={'height': '300px'})
                    ])
                ])
            ], xs=12, sm=12, md=12, lg=4, xl=4)
        ])
    ])

def create_config_tab():
    """Aba de configurações modernizada"""
    # Catálogo do SQL (IDs em Rel_Carga) + alias quando houver
    catalog = get_client_catalog()
    options = [{
        'label': f"{cid} - {alias}" if alias else str(cid),
        'value': cid
    } for cid, alias in catalog]
    # Tabela de visualização do que será exibido hoje
    if catalog:
        table_rows = [html.Tr([html.Td(str(cid)), html.Td(alias or str(cid))]) for cid, alias in catalog]
        table_component = dbc.Table([
            html.Thead(html.Tr([html.Th("ID (SQL)"), html.Th("Nome exibido (alias ou ID)")])) ,
            html.Tbody(table_rows)
        ], bordered=True, hover=True, responsive=True, striped=True, className="table-sm")
    else:
        table_component = dbc.Alert("Sem clientes detectados em Rel_Carga.", color="info")

    return html.Div([
        # Header da seção
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Span("⚙️", style={'font-size': '2rem', 'margin-right': '0.75rem'}),
                    html.H3("Configurações do Sistema", className="mb-0", style={'color': '#495057'})
                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '1.5rem'})
            ], width=12)
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("🔧", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Informações do Sistema", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #17a2b8 0%, #138496 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        html.Div([
                            html.Div([
                                html.Span("🔧", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                html.Strong("Versão: "),
                                html.Span("1.0.0")
                            ], style={'margin-bottom': '0.75rem', 'display': 'flex', 'align-items': 'center'}),
                            html.Div([
                                html.Span("💾", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                html.Strong("Banco: "),
                                html.Span("PostgreSQL")
                            ], style={'margin-bottom': '0.75rem', 'display': 'flex', 'align-items': 'center'}),
                            html.Div([
                                html.Span("🔄", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                html.Strong("Sincronização: "),
                                html.Span("Ativa", style={'color': '#28a745', 'font-weight': '600'})
                            ], style={'margin-bottom': '0.75rem', 'display': 'flex', 'align-items': 'center'}),
                            html.Div([
                                html.Span("📆", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                html.Strong("Status: "),
                                html.Span("Operacional", style={'color': '#28a745', 'font-weight': '600'})
                            ], style={'margin-bottom': '1rem', 'display': 'flex', 'align-items': 'center'}),
                            html.Hr(style={'margin': '1rem 0', 'border-color': '#dee2e6'}),
                            html.Div([
                                html.Span("⏰", style={'font-size': '1.2rem', 'margin-right': '0.5rem'}),
                                html.Strong("Última Atualização: "),
                                html.Span(datetime.now().strftime('%d/%m/%Y %H:%M'))
                            ], style={'display': 'flex', 'align-items': 'center'})
                        ])
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(23, 162, 184, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.Span("👥", style={'font-size': '1.5rem', 'margin-right': '0.5rem'}),
                            html.H5("Clientes - Nomes por ID", className="mb-0", style={'display': 'inline'})
                        ], style={'display': 'flex', 'align-items': 'center'})
                    ], style={
                        'background': 'linear-gradient(135deg, #6f42c1 0%, #5a32a3 100%)',
                        'color': 'white',
                        'border': 'none'
                    }),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Span("🔍", style={'font-size': '1rem', 'margin-right': '0.5rem'}),
                                    dbc.Label("Selecione um ID já mapeado", className="fw-bold", style={'display': 'inline'})
                                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '0.5rem'}),
                                dcc.Dropdown(id='client-id-select', options=options, placeholder='Escolha um ID (opcional)', optionHeight=32)
                            ], md=6),
                            dbc.Col([
                                html.Div([
                                    html.Span("✏️", style={'font-size': '1rem', 'margin-right': '0.5rem'}),
                                    dbc.Label("Ou informe um novo ID", className="fw-bold", style={'display': 'inline'})
                                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '0.5rem'}),
                                dbc.Input(id='client-id-manual', type='number', placeholder='Ex.: 25')
                            ], md=6)
                        ], className='g-2 mb-3'),
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.Span("🏷️", style={'font-size': '1rem', 'margin-right': '0.5rem'}),
                                    dbc.Label("Alias (nome para exibir aqui)", className="fw-bold", style={'display': 'inline'})
                                ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '0.5rem'}),
                                dbc.Input(id='client-name-input', type='text', placeholder='Ex.: Cliente XYZ (opcional)')
                            ], md=12)
                        ], className='g-2 mb-3'),
                        dbc.ButtonGroup([
                            dbc.Button("💾 Salvar Alias", id='save-client-name-btn', color='success', size="sm"),
                            dbc.Button("🗑️ Remover Todos", id='clear-all-aliases-btn', color='danger', outline=True, size="sm")
                        ], className='mb-3 w-100'),
                        html.Div(id='client-name-feedback'),
                        html.Div(id='client-alias-bulk-feedback'),
                        html.Hr(style={'margin': '1rem 0', 'border-color': '#dee2e6'}),
                        html.Div([
                            html.Span("📋", style={'font-size': '1.1rem', 'margin-right': '0.5rem'}),
                            html.H6("Clientes (ID do SQL → Nome exibido)", style={'display': 'inline', 'margin': '0'})
                        ], style={'display': 'flex', 'align-items': 'center', 'margin-bottom': '1rem'}),
                        html.Div(id='client-table', children=table_component)
                    ], style={'padding': '1.5rem'})
                ], style={
                    'border-radius': '12px',
                    'box-shadow': '0 6px 20px rgba(111, 66, 193, 0.15)',
                    'border': 'none',
                    'overflow': 'hidden'
                })
            ], width=6)
        ])
    ])

# Callback: Produção (apenas tabela - gráfico movido para aba Gráficos)
@app.callback(
    Output('client-metrics-table', 'children'),
    [Input('date-picker', 'start_date'),
     Input('date-picker', 'end_date')]
)
def update_production_analysis(start_date, end_date):
    """Atualiza tabela de produção por cliente com aliases"""
    try:
        from datetime import datetime
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
        
        # Buscar aliases cadastrados
        dbm = DatabaseManager()
        aliases_query = "SELECT client_id, alias FROM app.client_alias"
        try:
            aliases_df = dbm.execute_query(aliases_query)
            aliases_dict = dict(zip(aliases_df['client_id'], aliases_df['alias'])) if not aliases_df.empty else {}
        except Exception:
            aliases_dict = {}  # Fallback se tabela não existir
        
        df = aa_get_client_performance_comparison(start_dt, end_dt)
        # Fallback: caso a consulta avançada não traga dados, usar a consulta local client_production
        if df.empty:
            try:
                df = get_client_performance_comparison(start_dt, end_dt)
            except Exception:
                pass
        
        if not df.empty:
            # Montar tabela com aliases e melhor layout
            table_rows = []
            for _, row in df.iterrows():
                client_id = row.get('client_id', None)
                if client_id is not None:
                    client_id = int(client_id)  # Converter para int para match com aliases
                    client_display = aliases_dict.get(client_id, row['client_name'])
                else:
                    client_display = row['client_name']
                
                table_rows.append(
                    html.Tr([
                        html.Td([
                            html.Div(client_display, style={'font-weight': 'bold', 'color': '#2c3e50'}),
                            html.Small(f"ID: {client_id}", style={'color': '#6c757d'}) if client_id != client_display else None
                        ]),
                        html.Td([
                            html.Div(f"{row['total_kg']:,.0f}", style={'font-weight': 'bold', 'font-size': '1.1rem'}),
                            html.Small("quilos", style={'color': '#6c757d'})
                        ], style={'text-align': 'right'})
                    ], style={'border-left': '3px solid #007bff'})
                )

            table_component = dbc.Table([
                html.Thead([
                    html.Tr([
                        html.Th([
                            html.I(className="fas fa-user me-2"),
                            "Cliente"
                        ], style={'background': 'linear-gradient(135deg, #007bff, #0056b3)', 'color': 'white', 'border': 'none'}),
                        html.Th([
                            html.I(className="fas fa-weight me-2"),
                            "Produção"
                        ], style={'background': 'linear-gradient(135deg, #007bff, #0056b3)', 'color': 'white', 'border': 'none', 'text-align': 'right'})
                    ])
                ]),
                html.Tbody(table_rows)
            ], hover=True, responsive=True, className="table-sm", style={
                'border-radius': '8px',
                'overflow': 'hidden',
                'box-shadow': '0 2px 8px rgba(0,0,0,0.1)'
            })
        else:
            table_component = dbc.Alert([
                html.I(className="fas fa-info-circle me-2"),
                "Sem dados para o período selecionado"
            ], color="info")

        return table_component

    except Exception as e:
        error_msg = f"Erro ao atualizar análise: {str(e)}"
        return dbc.Alert(error_msg, color="danger")

# Callback para modo escuro - usando page-content ao invés de app-container
@app.callback(
    [Output('page-content', 'className'),
     Output('dark-mode-toggle', 'children')],
    [Input('dark-mode-toggle', 'n_clicks')],
    [State('page-content', 'className')],
    prevent_initial_call=True
)
def toggle_dark_mode(n_clicks, current_class):
    if n_clicks:
        if current_class and 'dark-theme' in current_class:
            # Mudar para modo claro
            new_class = current_class.replace('dark-theme', '').strip()
            button_text = '🌙 Modo Escuro'
        else:
            # Mudar para modo escuro
            new_class = f"{current_class or ''} dark-theme".strip()
            button_text = '☀️ Modo Claro'
        
        return new_class, button_text
    
    return current_class or '', '🌙 Modo Escuro'

# Callback: ao selecionar ID, carregar alias atual no input
@app.callback(
    Output('client-name-input', 'value'),
    Input('client-id-select', 'value'),
    prevent_initial_call=True
)
def load_current_alias(selected_id):
    if not selected_id:
        raise PreventUpdate
    rows = get_client_mappings()
    mapping = {cid: name for cid, name in rows}
    return mapping.get(int(selected_id), '')

# Callback: salvar/atualizar alias e recarregar tabela e dropdown
@app.callback(
    [Output('client-name-feedback', 'children'),
     Output('client-table', 'children', allow_duplicate=True),
     Output('client-id-select', 'options', allow_duplicate=True),
     Output('client-name-input', 'value', allow_duplicate=True),
     Output('client-id-manual', 'value'),
     Output('client-id-select', 'value')],
    Input('save-client-name-btn', 'n_clicks'),
    [State('client-id-select', 'value'), State('client-id-manual', 'value'), State('client-name-input', 'value')],
    prevent_initial_call=True
)
def save_client_name(n_clicks, selected_id, manual_id, alias_value):
    if not n_clicks:
        raise PreventUpdate
    # Prioridade: dropdown se selecionado, senão ID manual
    cid = selected_id if selected_id is not None else manual_id
    if cid is None:
        return [dbc.Alert("❌ Selecione um ID ou informe um novo", color="warning", dismissable=True), dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update]
    cid = int(cid)
    # Alias pode ser vazio -> remove alias? manteremos vazio significando "usar ID" → deletar registro
    if alias_value and str(alias_value).strip():
        ok, msg = upsert_client_mapping(cid, str(alias_value).strip())
    else:
        # Remover alias existente, se houver
        try:
            conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
            conn.autocommit = True
            cur = conn.cursor()
            cur.execute("DELETE FROM app.client_alias WHERE client_id = %s", (cid,))
            cur.close(); conn.close()
            ok, msg = True, "Alias removido; exibindo ID do SQL"
        except Exception as e:
            ok, msg = False, f"Erro ao remover alias: {e}"

    alert = dbc.Alert(("✅ " if ok else "❌ ") + msg, color=("success" if ok else "danger"), dismissable=True)
    # Recarregar catálogo completo (IDs do SQL) com alias atualizados
    catalog = get_client_catalog()
    options = [{'label': f"{cid} - {alias}" if alias else str(cid), 'value': cid} for cid, alias in catalog]
    if catalog:
        table_rows = [html.Tr([html.Td(str(cid)), html.Td(alias or str(cid))]) for cid, alias in catalog]
        table_component = dbc.Table([html.Thead(html.Tr([html.Th("ID (SQL)"), html.Th("Nome exibido (alias ou ID)")])), html.Tbody(table_rows)], bordered=True, hover=True, responsive=True, striped=True, className="table-sm")
    else:
        table_component = dbc.Alert("Sem clientes detectados em Rel_Carga.", color="info")
    # Limpar inputs após salvar
    return [alert, table_component, options, "", None, None]

# Callback: limpar todos os aliases
@app.callback(
    [Output('client-alias-bulk-feedback', 'children'),
     Output('client-table', 'children', allow_duplicate=True),
     Output('client-id-select', 'options', allow_duplicate=True)],
    Input('clear-all-aliases-btn', 'n_clicks'),
    prevent_initial_call=True
)
def clear_all_aliases(n_clicks):
    if not n_clicks:
        raise PreventUpdate
    try:
        conn = psycopg2.connect(host=DB_CONFIG['host'], database=DB_CONFIG['database'], user=DB_CONFIG['user'], password=DB_CONFIG['password'])
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("DELETE FROM app.client_alias")
        cur.close(); conn.close()
        alert = dbc.Alert("✅ Todos os aliases foram removidos. Agora o dashboard exibirá apenas os IDs do SQL.", color="success", dismissable=True)
    except Exception as e:
        alert = dbc.Alert(f"❌ Erro ao remover aliases: {e}", color="danger", dismissable=True)
    # Recarregar catálogo e componentes
    catalog = get_client_catalog()
    options = [{'label': f"{cid} - {alias}" if alias else str(cid), 'value': cid} for cid, alias in catalog]
    if catalog:
        table_rows = [html.Tr([html.Td(str(cid)), html.Td(alias or str(cid))]) for cid, alias in catalog]
        table_component = dbc.Table([html.Thead(html.Tr([html.Th("ID (SQL)"), html.Th("Nome exibido (alias ou ID)")])), html.Tbody(table_rows)], bordered=True, hover=True, responsive=True, striped=True, className="table-sm")
    else:
        table_component = dbc.Alert("Sem clientes detectados em Rel_Carga.", color="info")
    return [alert, table_component, options]

# Callbacks para gerenciamento de usuários
@app.callback(
    [Output('user-management-feedback', 'children'),
     Output('users-list', 'children'),
     Output('new-username', 'value'),
     Output('new-password', 'value')],
    [Input('add-user-btn', 'n_clicks')],
    [State('new-username', 'value'),
     State('new-password', 'value'),
     State('new-user-role', 'value')],
    prevent_initial_call=True
)
def manage_users(n_clicks, username, password, role):
    """Gerencia adição de usuários e lista usuários existentes"""
    feedback = []
    
    if n_clicks and username and password:
        success, message = add_user(username, password, role)
        if success:
            feedback = [dbc.Alert(f"✅ {message}", color="success", dismissable=True)]
            # Recarregar usuários globais
            global USERS
            USERS = load_users()
        else:
            feedback = [dbc.Alert(f"❌ {message}", color="danger", dismissable=True)]
    elif n_clicks:
        feedback = [dbc.Alert("❌ Preencha todos os campos", color="warning", dismissable=True)]
    
    # Lista de usuários
    users = load_users()
    users_list = []
    for username, user_data in users.items():
        role_icon = {
            'admin': '👨‍💻',
            'supervisor': '👨‍💼', 
            'operator': '👤'
        }.get(user_data.get('role', 'operator'), '👤')
        
        users_list.append(
            dbc.ListGroupItem([
                html.Div([
                    html.Strong(f"{role_icon} {username}"),
                    html.Small(f" ({user_data.get('role', 'operator')})", className="text-muted ms-2"),
                    html.Small(f" - Criado: {user_data.get('created', 'N/A')[:10]}", className="text-muted ms-2")
                ])
            ])
        )
    
    users_component = dbc.ListGroup(users_list) if users_list else html.P("Nenhum usuário cadastrado", className="text-muted")
    
    # Limpar campos após sucesso
    clear_username = "" if n_clicks and username and password else username
    clear_password = "" if n_clicks and username and password else password
    
    return feedback, users_component, clear_username, clear_password

# Callback para atualizar relatórios quando período for alterado
@app.callback(
    Output('tab-content', 'children', allow_duplicate=True),
    Input('refresh-report-btn', 'n_clicks'),
    [State('main-tabs', 'active_tab'),
     State('report-date-picker', 'start_date'),
     State('report-date-picker', 'end_date')],
    prevent_initial_call=True
)
def refresh_relatorios_tab(n_clicks, active_tab, start_date, end_date):
    """Re-renderiza a aba de Relatórios com o período selecionado no seletor único."""
    if active_tab == 'relatorios':
        return create_relatorios_tab(start_date, end_date)
    return PreventUpdate

## (Removido callback duplicado de exportação)

# Callback para atualizar gráfico executivo quando datas mudarem
@app.callback(
    Output('executive-dashboard-chart', 'figure'),
    [Input('date-picker', 'start_date'),
     Input('date-picker', 'end_date'),
     Input('refresh-button', 'n_clicks'),
     Input('interval-component', 'n_intervals')]
)
def update_executive_dashboard_chart(start_date, end_date, n_clicks, n_intervals):
    """Atualiza o gráfico executivo quando as datas mudarem"""
    try:
        print(f"📈 ATUALIZANDO GRÁFICO EXECUTIVO! start_date={start_date}, end_date={end_date}")
        
        # Converter strings para datetime se necessário
        if isinstance(start_date, str):
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        if isinstance(end_date, str):
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        
        return create_executive_dashboard_chart(start_date, end_date)
    except Exception as e:
        print(f"❌ ERRO NO GRÁFICO EXECUTIVO: {str(e)}")
        # Retornar gráfico vazio em caso de erro
        import plotly.graph_objects as go
        return go.Figure().add_annotation(
            text="Erro ao carregar gráfico executivo",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False
        )

if __name__ == '__main__':
    port = int(os.getenv('DASH_PORT', 8051))
    print("🚀 Iniciando DSTech Dashboard...")
    print(f"🛠️ Modo: {'PRODUÇÃO' if IS_PRODUCTION else 'DESENVOLVIMENTO'}")
    print(f"📈 Dashboard: http://localhost:{port}")
    print(f"👤 Login: admin / admin123")
    print(f"🔍 Debug: {'Desabilitado' if IS_PRODUCTION else 'Habilitado'}")
    
    app.run(
        debug=not IS_PRODUCTION,
        host='0.0.0.0',
        port=port
    )
