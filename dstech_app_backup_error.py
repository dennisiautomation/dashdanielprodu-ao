#!/usr/bin/env python3
"""
DSTech Dashboard - Aplicação Principal
Sistema completo de monitoramento industrial com dados reais
"""

import dash
from dash import dcc, html, Input, Output, State, callback_context, dash_table
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
    create_trend_analysis_chart, get_client_performance_comparison,
    create_smart_client_analysis
)

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

class DatabaseManager:
    """Gerenciador de conexão com PostgreSQL"""
    
    def __init__(self):
        self.config = DB_CONFIG
    
    def get_connection(self):
        try:
            return psycopg2.connect(**self.config)
        except Exception as e:
            print(f"Erro ao conectar com banco: {e}")
            return None
    
    def execute_query(self, query, params=None):
        conn = self.get_connection()
        if conn:
            try:
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
        ], width=3, lg=3, md=4, sm=6, xs=10)  # Responsivo e mais estreito
    ], justify="center", className="min-vh-100 align-items-center")
], fluid=True, style={'background': 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'})

# Layout principal do dashboard
def create_main_layout():
    return dbc.Container([
        # Header moderno
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Div([
                        html.Img(src="/assets/logodstech.png", 
                                style={'height': '50px', 'width': 'auto', 'margin-right': '15px'}),
                        html.Div([
                            html.H1("DSTech Dashboard", className="text-primary mb-0", 
                                   style={'font-weight': 'bold'}),
                            html.P("Sistema de Monitoramento Industrial", className="text-muted mb-0")
                        ])
                    ], style={'display': 'flex', 'align-items': 'center'})
                ])
            ], width=8),
            dbc.Col([
                html.Div([
                    dbc.Badge(f"Online", color="success", className="me-2"),
                    dbc.Button("Sair", id="logout-button", color="outline-danger", size="sm")
                ], className="text-end")
            ], width=4)
        ], className="mb-4", style={'padding': '1rem 0', 'border-bottom': '2px solid #e9ecef'}),
        
        # Filtros modernos
        dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("📅 Período de Análise:", className="fw-bold"),
                        dcc.DatePickerRange(
                            id='date-picker',
                            start_date=datetime.now() - timedelta(days=7),
                            end_date=datetime.now(),
                            display_format='DD/MM/YYYY',
                            style={'width': '100%'}
                        )
                    ], width=4),
                    dbc.Col([
                        dbc.Label("🔄 Controles:", className="fw-bold"),
                        html.Div([
                            dbc.Button("Atualizar Dados", id="refresh-button", 
                                     color="success", size="sm", className="me-2"),
                            dbc.Button("🌙 Modo Escuro", id="dark-mode-toggle", 
                                     color="secondary", size="sm")
                        ])
                    ], width=4),
                    dbc.Col([
                        html.Div([
                            html.P("📊 Status do Sistema", className="fw-bold mb-1"),
                            html.Div(id="last-update", className="text-muted small")
                        ])
                    ], width=4)
                ])
            ])
        ], className="mb-4", style={'background': '#f8f9fa'}),
        
        # Tabs principais com ícones
        dbc.Tabs([
            dbc.Tab(label="📊 Resumo Executivo", tab_id="resumo"),
            dbc.Tab(label="📈 Análise de Tendências", tab_id="tendencias"),
            dbc.Tab(label="🚨 Monitoramento de Alarmes", tab_id="alarmes"),
            dbc.Tab(label="🏭 Análise de Produção", tab_id="producao"),
            dbc.Tab(label="📋 Relatórios Detalhados", tab_id="relatorios"),
            dbc.Tab(label="⚙️ Configurações", tab_id="config")
        ], id="main-tabs", active_tab="resumo", className="mb-4"),
        
        # Conteúdo das tabs
        html.Div(id="tab-content"),
        
        # Componentes auxiliares
        dcc.Interval(id='interval-component', interval=60*1000, n_intervals=0)
        
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
        if username in USERS and USERS[username] == password_hash:
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
              [Input('main-tabs', 'active_tab'),
               Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def render_tab_content(active_tab, start_date, end_date, refresh_clicks, n_intervals):
    
    if active_tab == "resumo":
        return create_resumo_tab(start_date, end_date)
    elif active_tab == "tendencias":
        return create_tendencias_tab(start_date, end_date)
    elif active_tab == "alarmes":
        return create_alarmes_tab(start_date, end_date)
    elif active_tab == "producao":
        return create_producao_tab(start_date, end_date)
    elif active_tab == "relatorios":
        return create_relatorios_tab(start_date, end_date)
    elif active_tab == "config":
        return create_config_tab()
    
    return html.Div("Selecione uma aba")

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

@app.callback(Output('alarm-analysis-chart', 'figure'),
              [Input('date-picker', 'start_date'),
               Input('date-picker', 'end_date'),
               Input('refresh-button', 'n_clicks'),
               Input('interval-component', 'n_intervals')])
def update_alarm_analysis_chart(start_date, end_date, n_clicks, n_intervals):
    return create_alarm_analysis_chart(start_date, end_date)

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

# Callback para atualizar KPIs dinamicamente
@app.callback(
    [Output('kg-hoje-value', 'children'),
     Output('ciclos-hoje-value', 'children'),
     Output('agua-hoje-value', 'children'),
     Output('agua-ratio-value', 'children'),
     Output('quimicos-hoje-value', 'children'),
     Output('quimicos-ratio-value', 'children'),
     Output('alarmes-ativos-value', 'children'),
     Output('producao-semanal-value', 'children'),
     Output('ciclos-semana-value', 'children'),
     Output('eficiencia-media-value', 'children'),
     Output('media-ciclo-value', 'children')],
    [Input('date-picker', 'start_date'),
     Input('date-picker', 'end_date')],
    prevent_initial_call=False
)
def update_kpis(start_date, end_date):
    """Atualiza os KPIs baseado nos filtros selecionados"""
    
    print(f"🔄 CALLBACK KPIs EXECUTADO! start_date={start_date}, end_date={end_date}")
    
    # Converter strings de data para objetos date
    if start_date:
        filter_start = datetime.fromisoformat(start_date).date()
    else:
        filter_start = datetime.now().date()
        
    if end_date:
        filter_end = datetime.fromisoformat(end_date).date()
    else:
        filter_end = datetime.now().date()
    
    print(f"📅 Atualizando KPIs - Datas: {filter_start} a {filter_end}")
    
    # Obter KPIs atualizados (sem filtro de cliente)
    kpis = get_operational_kpis(filter_start, filter_end, None)
    print(f"📊 KPIs obtidos: {kpis['quilos_lavados_hoje']} kg")
    
    # Retornar valores formatados
    return (
        f"{kpis['quilos_lavados_hoje']} kg",
        f"Ciclos: {kpis['ciclos_hoje']}",
        f"{kpis['litros_agua_hoje']} L",
        f"{kpis['litros_por_kg_hoje']:.1f} L/kg",
        f"{kpis['kg_quimicos_hoje']:.1f} kg",
        f"{kpis['kg_quimicos_por_kg_hoje']:.3f} kg/kg",
        str(kpis['alarmes_ativos']),
        f"{kpis['quilos_lavados_semana']} kg",
        f"Ciclos: {kpis['ciclos_semana']}",
        f"{kpis['eficiencia_media']:.1f}%",
        f"{(kpis['quilos_lavados_hoje_raw']/kpis['ciclos_hoje'] if kpis['ciclos_hoje'] > 0 else 0):.1f} kg"
    )

# Callback para atualizar análise inteligente de clientes
@app.callback(
    Output('smart-client-analysis', 'children'),
    [Input('production-client-filter', 'value'),
     Input('production-period-filter', 'value'),
     Input('analysis-type-filter', 'value')]
)
def update_smart_analysis(client_filter, period_filter, analysis_type):
    """Atualiza a análise inteligente baseado nos filtros"""
    
    print(f"🔍 DEBUG: update_smart_analysis chamado - Cliente: {client_filter}, Período: {period_filter}, Tipo: {analysis_type}")
    
    # Calcular período
    if period_filter in ['7', '15', '30', '60']:
        days = int(period_filter)
        end_date = datetime.now().date()
        start_date = (datetime.now() - timedelta(days=days)).date()
    else:
        # Default para 30 dias
        end_date = datetime.now().date()
        start_date = (datetime.now() - timedelta(days=30)).date()
    
    print(f"Atualizando análise inteligente - Cliente: {client_filter}, Período: {period_filter}, Tipo: {analysis_type}")
    
    try:
        # Gerar análise inteligente
        result = create_smart_client_analysis(start_date, end_date, client_filter)
        
        if result is None:
            print("⚠️ create_smart_client_analysis retornou None")
            return html.Div([
                dbc.Alert("Análise não disponível no momento", color="warning")
            ])
            
        print(f"✅ Análise inteligente gerada com sucesso: {type(result)}")
        return result
        
    except Exception as e:
        print(f"❌ Erro ao atualizar análise inteligente: {e}")
        import traceback
        traceback.print_exc()
        return html.Div([
            dbc.Alert(f"Erro ao carregar análise: {str(e)}", color="danger")
        ])

# Callback para exportação de relatório
@app.callback(Output('download-report', 'data'),
              [Input('export-report-btn', 'n_clicks')],
              [State('export-format-dropdown', 'value'),
               State('report-period-dropdown', 'value')],
              prevent_initial_call=True)
def export_report(n_clicks, export_format, period_days):
    if n_clicks:
        import json
        import pandas as pd
        from datetime import datetime, timedelta
        import io
        import base64
        
        # Gerar relatório com período específico
        report = generate_executive_report()
        chemical_details = get_chemical_details()
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if export_format == 'txt':
            # Criar conteúdo do relatório em texto
            report_content = f"""# RELATÓRIO EXECUTIVO - DSTECH LAVANDERIA
Gerado em: {report['timestamp']}
Período: Últimos {period_days} dias

## RESUMO DE PRODUÇÃO
- Produção Hoje: {report['production_summary']['daily_production']} kg ({report['production_summary']['daily_cycles']} ciclos)
- Produção Semanal: {report['production_summary']['weekly_production']} kg ({report['production_summary']['weekly_cycles']} ciclos)
- Eficiência Média: {report['production_summary']['efficiency']}

## RESUMO DE CONSUMOS
- Água Hoje: {report['consumption_summary']['water_today']} L ({report['consumption_summary']['water_per_kg']})
- Químicos Hoje: {report['consumption_summary']['chemicals_today']} ({report['consumption_summary']['chemicals_per_kg']})

## DETALHAMENTO DE QUÍMICOS (Últimos 7 dias)
"""
            for chem in chemical_details:
                report_content += f"- {chem['tipo_quimico']}: {chem['quantidade_kg']:.1f} kg ({chem['ciclos_utilizados']} ciclos)\n"
            
            report_content += f"""

## RESUMO DE ALARMES
- Alarmes Ativos: {report['alarms_summary']['active_alarms']}
- Total do Mês: {report['alarms_summary']['total_month']}
- Críticos/Altos: {report['alarms_summary']['critical_high']}
- Tempo Médio de Resolução: {report['alarms_summary']['avg_resolution']}

## RECOMENDAÇÕES
"""
            for i, rec in enumerate(report['recommendations'], 1):
                report_content += f"{i}. {rec}\n"
            
            filename = f"relatorio_executivo_{timestamp}.txt"
            return dict(content=report_content, filename=filename)
            
        elif export_format == 'excel':
            # Criar Excel com múltiplas abas
            output = io.BytesIO()
            
            # Dados de produção
            prod_data = {
                'Métrica': ['Produção Hoje (kg)', 'Ciclos Hoje', 'Produção Semanal (kg)', 'Ciclos Semana', 'Eficiência Média'],
                'Valor': [report['production_summary']['daily_production'], 
                         report['production_summary']['daily_cycles'],
                         report['production_summary']['weekly_production'],
                         report['production_summary']['weekly_cycles'],
                         report['production_summary']['efficiency']]
            }
            
            # Dados de consumo
            cons_data = {
                'Métrica': ['Água Hoje (L)', 'Água por Kg', 'Químicos Hoje', 'Químicos por Kg'],
                'Valor': [report['consumption_summary']['water_today'],
                         report['consumption_summary']['water_per_kg'],
                         report['consumption_summary']['chemicals_today'],
                         report['consumption_summary']['chemicals_per_kg']]
            }
            
            # Dados de químicos detalhados
            if chemical_details:
                chem_data = {
                    'Tipo de Químico': [chem['tipo_quimico'] for chem in chemical_details],
                    'Quantidade (kg)': [round(chem['quantidade_kg'], 2) for chem in chemical_details],
                    'Ciclos Utilizados': [chem['ciclos_utilizados'] for chem in chemical_details],
                    'Média por Ciclo (kg)': [round(chem['media_por_ciclo'], 3) for chem in chemical_details]
                }
            else:
                chem_data = {'Tipo de Químico': ['Sem dados'], 'Quantidade (kg)': [0], 'Ciclos Utilizados': [0], 'Média por Ciclo (kg)': [0]}
            
            # Dados de alarmes
            alarm_data = {
                'Métrica': ['Alarmes Ativos', 'Total do Mês', 'Críticos/Altos', 'Tempo Médio Resolução'],
                'Valor': [report['alarms_summary']['active_alarms'],
                         report['alarms_summary']['total_month'],
                         report['alarms_summary']['critical_high'],
                         report['alarms_summary']['avg_resolution']]
            }
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame(prod_data).to_excel(writer, sheet_name='Produção', index=False)
                pd.DataFrame(cons_data).to_excel(writer, sheet_name='Consumos', index=False)
                pd.DataFrame(chem_data).to_excel(writer, sheet_name='Químicos', index=False)
                pd.DataFrame(alarm_data).to_excel(writer, sheet_name='Alarmes', index=False)
                pd.DataFrame({'Recomendações': report['recommendations']}).to_excel(writer, sheet_name='Recomendações', index=False)
            
            filename = f"relatorio_executivo_{timestamp}.xlsx"
            return dict(content=base64.b64encode(output.getvalue()).decode(), filename=filename, base64=True)
            
        elif export_format == 'pdf':
            # Criar HTML com layout profissional para PDF
            chemicals_html = ""
            if chemical_details:
                chemicals_html = "<h2 style='color: #2c3e50; border-bottom: 2px solid #3498db;'>DETALHAMENTO DE QUÍMICOS (Últimos 7 dias)</h2><table style='width: 100%; border-collapse: collapse; margin: 20px 0;'><tr style='background-color: #3498db; color: white;'><th style='padding: 10px; border: 1px solid #ddd;'>Tipo</th><th style='padding: 10px; border: 1px solid #ddd;'>Quantidade (kg)</th><th style='padding: 10px; border: 1px solid #ddd;'>Ciclos</th><th style='padding: 10px; border: 1px solid #ddd;'>Média/Ciclo</th></tr>"
                for chem in chemical_details:
                    chemicals_html += f"<tr><td style='padding: 8px; border: 1px solid #ddd;'>{chem['tipo_quimico']}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: right;'>{chem['quantidade_kg']:.1f}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: center;'>{chem['ciclos_utilizados']}</td><td style='padding: 8px; border: 1px solid #ddd; text-align: right;'>{chem['media_por_ciclo']:.3f}</td></tr>"
                chemicals_html += "</table>"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset='UTF-8'>
                <title>Relatório Executivo - DSTech</title>
                <style>
                    body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #2c3e50; line-height: 1.6; }}
                    .header {{ text-align: center; margin-bottom: 40px; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 10px; }}
                    .header h1 {{ margin: 0; font-size: 28px; font-weight: bold; }}
                    .header p {{ margin: 5px 0; font-size: 14px; opacity: 0.9; }}
                    .section {{ margin: 30px 0; padding: 20px; background: #f8f9fa; border-radius: 8px; border-left: 4px solid #3498db; }}
                    .section h2 {{ color: #2c3e50; margin-top: 0; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
                    .metrics {{ display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }}
                    .metric {{ background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; min-width: 200px; }}
                    .metric-value {{ font-size: 24px; font-weight: bold; color: #3498db; }}
                    .metric-label {{ font-size: 12px; color: #7f8c8d; text-transform: uppercase; }}
                    ul {{ list-style-type: none; padding: 0; }}
                    li {{ background: white; margin: 8px 0; padding: 12px; border-radius: 5px; border-left: 3px solid #3498db; }}
                    .recommendations {{ background: #e8f5e8; border-left-color: #27ae60; }}
                    .recommendations li {{ border-left-color: #27ae60; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: white; }}
                    th {{ background: #3498db; color: white; padding: 12px; text-align: left; }}
                    td {{ padding: 10px; border-bottom: 1px solid #ecf0f1; }}
                    tr:nth-child(even) {{ background: #f8f9fa; }}
                    .footer {{ text-align: center; margin-top: 40px; padding: 20px; background: #34495e; color: white; border-radius: 8px; }}
                </style>
            </head>
            <body>
                <div class='header'>
                    <h1>🏢 RELATÓRIO EXECUTIVO - DSTECH LAVANDERIA</h1>
                    <p><strong>Gerado em:</strong> {report['timestamp']}</p>
                    <p><strong>Período de Análise:</strong> Últimos {period_days} dias</p>
                </div>
                
                <div class='section'>
                    <h2>🏢 RESUMO DE PRODUÇÃO</h2>
                    <div class='metrics'>
                        <div class='metric'>
                            <div class='metric-value'>{report['production_summary']['daily_production']}</div>
                            <div class='metric-label'>kg Produzidos Hoje</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['production_summary']['daily_cycles']}</div>
                            <div class='metric-label'>Ciclos Hoje</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['production_summary']['weekly_production']}</div>
                            <div class='metric-label'>kg Esta Semana</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['production_summary']['efficiency']}</div>
                            <div class='metric-label'>Eficiência Média</div>
                        </div>
                    </div>
                </div>
                
                <div class='section'>
                    <h2>💧 RESUMO DE CONSUMOS</h2>
                    <ul>
                        <li><strong>Água Hoje:</strong> {report['consumption_summary']['water_today']} L ({report['consumption_summary']['water_per_kg']})</li>
                        <li><strong>Químicos Hoje:</strong> {report['consumption_summary']['chemicals_today']} ({report['consumption_summary']['chemicals_per_kg']})</li>
                    </ul>
                </div>
                
                {chemicals_html}
                
                <div class='section'>
                    <h2>🚨 RESUMO DE ALARMES</h2>
                    <div class='metrics'>
                        <div class='metric'>
                            <div class='metric-value' style='color: #e74c3c;'>{report['alarms_summary']['active_alarms']}</div>
                            <div class='metric-label'>Alarmes Ativos</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['alarms_summary']['total_month']}</div>
                            <div class='metric-label'>Total do Mês</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['alarms_summary']['critical_high']}</div>
                            <div class='metric-label'>Críticos/Altos</div>
                        </div>
                        <div class='metric'>
                            <div class='metric-value'>{report['alarms_summary']['avg_resolution']}</div>
                            <div class='metric-label'>Tempo Médio Resolução</div>
                        </div>
                    </div>
                </div>
                
                <div class='section recommendations'>
                    <h2>💡 RECOMENDAÇÕES</h2>
                    <ul>
                        """ + '\n'.join([f"<li><strong>{i+1}.</strong> {rec}</li>" for i, rec in enumerate(report['recommendations'])]) + f"""
                    </ul>
                </div>
                
                <div class='footer'>
                    <p>🔧 DSTech Industrial Dashboard | Relatório gerado automaticamente</p>
                    <p>Para mais informações, acesse o dashboard em tempo real</p>
                </div>
            </body>
            </html>
            """
            
            filename = f"relatorio_executivo_{timestamp}.html"
            return dict(content=html_content, filename=filename)
    
    return None

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
    
    # Título da seção sem filtros desnecessários
    header_section = dbc.Row([
        dbc.Col([
            html.H2("📊 Resumo Executivo", className="text-primary mb-3"),
            html.P("Indicadores principais de performance operacional", className="text-muted mb-4")
        ], width=12)
    ], className="mb-4")
    
    # Cards de KPIs com dados reais melhorados
    kpi_cards = html.Div([
        # Primeira linha de KPIs
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("🔄 Carregando...", className="text-primary mb-0", id="kg-hoje-value"),
                            html.P("📦 Quilos Lavados Hoje", className="mb-0 text-muted"),
                            html.Small("Aguarde...", className="text-primary", id="ciclos-hoje-value")
                        ])
                    ])
                ], style={'border-left': '4px solid #28a745'})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-info mb-0", id="agua-hoje-value"),
                            html.P("💧 Água Usada Hoje", className="mb-0 text-muted"),
                            html.Small("...", className="text-primary", id="agua-ratio-value")
                        ])
                    ])
                ], style={'border-left': '4px solid #17a2b8'})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-purple mb-0", id="quimicos-hoje-value"),
                            html.P("🧪 Químicos Hoje", className="mb-0 text-muted"),
                            html.Small("...", className="text-primary", id="quimicos-ratio-value")
                        ])
                    ])
                ], style={'border-left': '4px solid #6f42c1'})
            ], width=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-danger mb-0", id="alarmes-ativos-value"),
                            html.P("🚨 Alarmes Ativos", className="mb-0 text-muted"),
                            html.Small("Últimas 24h", className="text-primary")
                        ])
                    ])
                ], style={'border-left': '4px solid #dc3545'})
            ], width=3)
        ], className="mb-3"),
        
        # Segunda linha de KPIs
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-primary mb-0", id="producao-semanal-value"),
                            html.P("📈 Produção Semanal", className="mb-0 text-muted"),
                            html.Small("...", className="text-primary", id="ciclos-semana-value")
                        ])
                    ])
                ], style={'border-left': '4px solid #007bff'})
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-warning mb-0", id="eficiencia-media-value"),
                            html.P("⚡ Eficiência Média", className="mb-0 text-muted"),
                            html.Small("Últimos 7 dias", className="text-primary")
                        ])
                    ])
                ], style={'border-left': '4px solid #ffc107'})
            ], width=4),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Div([
                            html.H3("...", className="text-secondary mb-0", id="media-ciclo-value"),
                            html.P("🔄 Média por Ciclo", className="mb-0 text-muted"),
                            html.Small("Hoje", className="text-primary")
                        ])
                    ])
                ], style={'border-left': '4px solid #6c757d'})
            ], width=4)
        ], className="mb-4")
    ])
    
    # Gráficos principais com dados reais
    charts_row = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("⚡ Eficiência Operacional", className="mb-0")
                ]),
                dbc.CardBody([
                    dcc.Graph(id='efficiency-chart', figure=create_efficiency_chart(), style={'height': '400px'})
                ])
            ])
        ], width=6),
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("💧 Consumo de Água por Kg", className="mb-0")
                ]),
                dbc.CardBody([
                    dcc.Graph(id='water-chart', figure=create_water_consumption_chart(), style={'height': '400px'})
                ])
            ])
        ], width=6)
    ], className="mb-4")
    
    # Segunda linha de gráficos
    charts_row2 = dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("🧪 Consumo de Químicos por Kg", className="mb-0")
                ]),
                dbc.CardBody([
                    dcc.Graph(id='chemical-chart', figure=create_chemical_consumption_chart(), style={'height': '400px'})
                ])
            ])
        ], width=12)
    ])
    
    return html.Div([header_section, kpi_cards, charts_row, charts_row2])

def create_alarmes_tab(start_date, end_date):
    """Aba de monitoramento de alarmes"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("🔝 Top 10 Alarmes Mais Frequentes", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id='top-alarms-chart', figure=create_top_alarms_chart(), style={'height': '500px'})
                    ])
                ])
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("⚠️ Alarmes Ativos", className="mb-0")
                    ]),
                    dbc.CardBody([
                        create_active_alarms_table()
                    ])
                ])
            ], width=6)
        ], className="mb-4"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Análise de Alarmes por Área", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id='alarm-analysis-chart', figure=create_alarm_analysis_chart(), style={'height': '500px'})
                    ])
                ])
            ], width=12)
        ])
    ])

def create_tendencias_tab(start_date, end_date):
    """Aba de análise de tendências dos sensores"""
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("🌡️ Tendência de Temperatura", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_temperature_trend_chart(start_date, end_date), style={'height': '500px'})
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Análise Completa de Sensores", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_sensors_trend_chart(start_date, end_date), style={'height': '600px'})
                    ])
                ])
            ], width=12)
        ])
    ])

def create_producao_tab(start_date, end_date):
    """Aba de análise de produção com comparativos avançados"""
    
    # Obter insights operacionais
    try:
        insights = get_operational_insights(start_date, end_date)
    except:
        insights = []
    
    return html.Div([
        # Instruções e controles de filtro
        dbc.Row([
            dbc.Col([
                dbc.Alert([
                    html.H5("💡 Como usar a Análise Inteligente:", className="alert-heading mb-2"),
                    html.P([
                        "1. ", html.Strong("Selecione um cliente"), " específico ou mantenha 'Todos' para análise geral"
                    ], className="mb-1"),
                    html.P([
                        "2. ", html.Strong("Escolha o período"), " de análise (recomendado: 30 dias para insights completos)"
                    ], className="mb-1"),
                    html.P([
                        "3. ", html.Strong("Defina o tipo de análise:"), " Comparativo (padrão), Tendência ou Performance Individual"
                    ], className="mb-1"),
                    html.P([
                        "4. ", html.Strong("A análise será atualizada automaticamente"), " com insights e recomendações"
                    ], className="mb-0")
                ], color="info", className="mb-3")
            ], width=12)
        ]),
        
        # Controles de filtro
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("🎛️ Configurações da Análise", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label("👥 Cliente para Análise:", className="form-label fw-bold"),
                                html.Small("Selecione um cliente específico ou todos", className="text-muted d-block mb-2"),
                                dcc.Dropdown(
                                    id='production-client-filter',
                                    options=[
                                        {'label': '🏢 Todos os Clientes', 'value': 'all'},
                                        {'label': '🏠 Cliente Interno', 'value': '0'},
                                        {'label': '🏪 Cliente A', 'value': '2'},
                                        {'label': '🏬 Cliente B', 'value': '5'},
                                        {'label': '🏭 Cliente C', 'value': '13'},
                                        {'label': '🏢 Cliente D', 'value': '41'}
                                    ],
                                    value='all',
                                    clearable=False
                                )
                            ], width=4),
                            dbc.Col([
                                html.Label("📅 Período de Análise:", className="form-label fw-bold"),
                                html.Small("Quanto mais dados, melhor a análise", className="text-muted d-block mb-2"),
                                dcc.Dropdown(
                                    id='production-period-filter',
                                    options=[
                                        {'label': '📊 Últimos 7 dias', 'value': '7'},
                                        {'label': '📈 Últimos 15 dias', 'value': '15'},
                                        {'label': '📉 Últimos 30 dias (Recomendado)', 'value': '30'},
                                        {'label': '📋 Últimos 60 dias', 'value': '60'}
                                    ],
                                    value='30',
                                    clearable=False
                                )
                            ], width=4),
                            dbc.Col([
                                html.Label("🔍 Tipo de Análise:", className="form-label fw-bold"),
                                html.Small("Escolha o foco da análise", className="text-muted d-block mb-2"),
                                dcc.Dropdown(
                                    id='analysis-type-filter',
                                    options=[
                                        {'label': '📊 Comparativo entre Clientes', 'value': 'comparison'},
                                        {'label': '📈 Análise de Tendências', 'value': 'trend'},
                                        {'label': '🎯 Performance Detalhada', 'value': 'individual'}
                                    ],
                                    value='comparison',
                                    clearable=False
                                )
                            ], width=4)
                        ])
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        # Insights Operacionais - DINÂMICOS
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("💡 Insights Operacionais", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id='operational-insights', children=[
                            dbc.Alert("Carregando insights...", color="info")
                        ])
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        # GRÁFICOS MOVIDOS PARA ANTES DA TABELA
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📈 Análise de Tendência Temporal", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(
                            id='trend-analysis-chart', 
                            style={'height': '500px'}
                        )
                    ])
                ])
            ], width=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Comparativo de Clientes", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(
                            id='client-comparison-chart',
                            style={'height': '500px'}
                        )
                    ])
                ])
            ], width=4)
        ], className="mb-4"),
        
        # Análise Inteligente de Performance - APÓS OS GRÁFICOS
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📈 Análise Inteligente de Performance", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id='smart-client-analysis')
                    ])
                ])
            ], width=12)
        ], className="mb-4"),
        
        # Métricas Detalhadas
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📋 Métricas Detalhadas", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div(id='detailed-metrics', children=[
                            html.P("📊 Carregando métricas detalhadas...", className="text-muted")
                        ])
                    ])
                ])
            ], width=12)
        ])
    ])

def create_relatorios_tab(start_date, end_date):
    """Aba de relatórios executivos"""
    
    # Gerar relatório executivo
    report = generate_executive_report()
    
    return html.Div([
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📈 Relatório Executivo", className="mb-0")
                    ]),
                    dbc.CardBody([
                        html.Div([
                            html.H6(f"📅 Gerado em: {report['timestamp']}", className="text-muted mb-3"),
                            
                            # Resumo de Produção
                            html.H5("🏭 Resumo de Produção", className="text-primary mb-2"),
                            html.Ul([
                                html.Li(f"Produção Hoje: {report['production_summary']['daily_production']} kg ({report['production_summary']['daily_cycles']} ciclos)"),
                                html.Li(f"Produção Semanal: {report['production_summary']['weekly_production']} kg ({report['production_summary']['weekly_cycles']} ciclos)"),
                                html.Li(f"Eficiência Média: {report['production_summary']['efficiency']}")
                            ], className="mb-3"),
                            
                            # Resumo de Consumos
                            html.H5("💧 Resumo de Consumos", className="text-info mb-2"),
                            html.Ul([
                                html.Li(f"Água Hoje: {report['consumption_summary']['water_today']} L ({report['consumption_summary']['water_per_kg']})"),
                                html.Li(f"Químicos Hoje: {report['consumption_summary']['chemicals_today']} ({report['consumption_summary']['chemicals_per_kg']})")
                            ], className="mb-3"),
                            
                            # Resumo de Alarmes
                            html.H5("🚨 Resumo de Alarmes", className="text-warning mb-2"),
                            html.Ul([
                                html.Li(f"Alarmes Ativos: {report['alarms_summary']['active_alarms']}"),
                                html.Li(f"Total do Mês: {report['alarms_summary']['total_month']}"),
                                html.Li(f"Críticos/Altos: {report['alarms_summary']['critical_high']}"),
                                html.Li(f"Tempo Médio de Resolução: {report['alarms_summary']['avg_resolution']}")
                            ], className="mb-3"),
                            
                            # Recomendações
                            html.H5("💡 Recomendações", className="text-success mb-2"),
                            html.Ul([
                                html.Li(rec) for rec in report['recommendations']
                            ], className="mb-3"),
                            
                            html.Div([
                                dbc.Row([
                                    dbc.Col([
                                        html.Label("Formato de Exportação:", className="form-label mb-2"),
                                        dcc.Dropdown(
                                            id='export-format-dropdown',
                                            options=[
                                                {'label': '📄 PDF', 'value': 'pdf'},
                                                {'label': '📊 Excel', 'value': 'excel'},
                                                {'label': '📝 Texto', 'value': 'txt'}
                                            ],
                                            value='pdf',
                                            clearable=False,
                                            className="mb-3"
                                        )
                                    ], width=6),
                                    dbc.Col([
                                        html.Label("Período do Relatório:", className="form-label mb-2"),
                                        dcc.Dropdown(
                                            id='report-period-dropdown',
                                            options=[
                                                {'label': 'Últimos 7 dias', 'value': '7'},
                                                {'label': 'Últimos 15 dias', 'value': '15'},
                                                {'label': 'Últimos 30 dias', 'value': '30'},
                                                {'label': 'Últimos 60 dias', 'value': '60'}
                                            ],
                                            value='30',
                                            clearable=False,
                                            className="mb-3"
                                        )
                                    ], width=6)
                                ]),
                                dbc.ButtonGroup([
                                    dbc.Button("💾 Exportar Relatório", id="export-report-btn", color="primary"),
                                    dbc.Button("🔄 Atualizar", id="refresh-report-btn", color="secondary", outline=True)
                                ], className="mb-3"),
                                dcc.Download(id="download-report")
                            ])
                        ])
                    ])
                ])
            ], width=8),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.H5("📊 Gráficos Resumo", className="mb-0")
                    ]),
                    dbc.CardBody([
                        dcc.Graph(figure=create_efficiency_chart(), style={'height': '300px'}),
                        html.Hr(),
                        dcc.Graph(figure=create_water_consumption_chart(), style={'height': '300px'})
                    ])
                ])
            ], width=4)
        ])
    ])

def create_config_tab():
    """Aba de configurações"""
    return dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.CardHeader([
                    html.H5("⚙️ Informações do Sistema", className="mb-0")
                ]),
                dbc.CardBody([
                    html.Div([
                        html.P(f"🔧 Versão: 1.0.0"),
                        html.P(f"💾 Banco: PostgreSQL"),
                        html.P(f"🔄 Sincronização: Ativa"),
                        html.P(f"📆 Status: Operacional"),
                        html.Hr(),
                        html.P(f"📈 Registros TREND: 810.043"),
                        html.P(f"🚨 Registros Alarmes: 92.550"),
                        html.P(f"⏰ Última Atualização: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                    ])
                ])
            ])
        ], width=6)
    ])

# Callbacks para Análise de Produção Dinâmica
@app.callback(
    [Output('operational-insights', 'children'),
     Output('trend-analysis-chart', 'figure'),
     Output('client-comparison-chart', 'figure'),
     Output('smart-client-analysis', 'children'),
     Output('detailed-metrics', 'children')],
    [Input('production-client-filter', 'value'),
     Input('production-period-filter', 'value'),
     Input('analysis-type-filter', 'value')]
)
def update_production_analysis(client_filter, period_days, analysis_type):
    """Atualiza toda a análise de produção dinamicamente"""
    try:
        from datetime import datetime, timedelta
        
        # Calcular datas
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=int(period_days))
        
        # 1. Insights Operacionais
        insights = get_operational_insights(start_date, end_date)
        insights_components = [
            dbc.Alert([
                html.H6(insight['title'], className="alert-heading mb-2"),
                html.P(insight['message'], className="mb-1"),
                html.Small(insight['detail'], className="text-muted")
            ], color={
                'success': 'success',
                'info': 'info', 
                'warning': 'warning',
                'danger': 'danger'
            }.get(insight['type'], 'info'), className="mb-2")
            for insight in insights[:4]
        ] if insights else [dbc.Alert("Nenhum insight disponível para o período selecionado", color="info")]
        
        # 2. Gráfico de Tendência
        client_id = None if client_filter == 'all' else int(client_filter)
        trend_chart = create_trend_analysis_chart(client_id=client_id, days=int(period_days))
        
        # 3. Gráfico de Comparação de Clientes
        comparison_chart = create_client_comparison_dashboard(start_date, end_date)
        
        # 4. Análise Inteligente
        smart_analysis = create_smart_client_analysis(start_date, end_date, client_filter)
        
        # 5. Métricas Detalhadas
        df = get_client_performance_comparison(start_date, end_date)
        if not df.empty:
            if client_filter != 'all':
                df = df[df['client_id'] == int(client_filter)]
            
            total_production = df['total_kg'].sum()
            total_water = df['total_water_liters'].sum()
            avg_efficiency = df['water_efficiency_l_per_kg'].mean()
            total_clients = len(df)
            
            metrics_components = [
                dbc.Row([
                    dbc.Col([
                        html.H4(f"{total_production:,.0f} kg", className="text-primary mb-0"),
                        html.Small("Produção Total", className="text-muted")
                    ], width=6),
                    dbc.Col([
                        html.H4(f"{total_water:,.0f} L", className="text-info mb-0"),
                        html.Small("Água Consumida", className="text-muted")
                    ], width=6)
                ], className="mb-3"),
                dbc.Row([
                    dbc.Col([
                        html.H4(f"{avg_efficiency:.1f} L/kg", className="text-warning mb-0"),
                        html.Small("Eficiência Média", className="text-muted")
                    ], width=6),
                    dbc.Col([
                        html.H4(f"{total_clients}", className="text-success mb-0"),
                        html.Small("Clientes Ativos", className="text-muted")
                    ], width=6)
                ])
            ]
        else:
            metrics_components = [dbc.Alert("Sem dados para o período selecionado", color="info")]
        
        return insights_components, trend_chart, comparison_chart, smart_analysis, metrics_components
        
    except Exception as e:
        error_msg = f"Erro ao atualizar análise: {str(e)}"
        error_alert = dbc.Alert(error_msg, color="danger")
        empty_fig = go.Figure().add_annotation(text="Erro ao carregar dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return [error_alert], empty_fig, empty_fig, error_alert, [error_alert]

# Callback para modo escuro
@app.callback(
    [Output('app-container', 'className'),
     Output('dark-mode-toggle', 'children')],
    [Input('dark-mode-toggle', 'n_clicks')],
    [State('app-container', 'className')],
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
