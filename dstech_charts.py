"""
DSTech Dashboard - Módulo de Gráficos
Gráficos com dados reais do PostgreSQL baseados no README e reunião
"""

import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import pandas as pd
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv
import numpy as np
from dash import html, dash_table
import dash_bootstrap_components as dbc

# Carregar variáveis de ambiente
load_dotenv('.env_dstech')

# Configurações do banco
PG_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', 'postgres123'),
    'database': os.getenv('POSTGRES_DB', 'dstech_dashboard')
}

def get_db_connection():
    """Cria conexão com PostgreSQL"""
    return psycopg2.connect(**PG_CONFIG, cursor_factory=RealDictCursor)

def execute_query(query, params=None):
    """Executa query e retorna DataFrame usando SQLAlchemy"""
    try:
        # Criar string de conexão SQLAlchemy
        connection_string = f"postgresql://{PG_CONFIG['user']}:{PG_CONFIG['password']}@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}"
        engine = create_engine(connection_string)
        
        df = pd.read_sql_query(query, engine, params=params)
        return df
    except Exception as e:
        print(f"Erro na query: {e}")
        return pd.DataFrame()

# ===== GRÁFICOS PRINCIPAIS BASEADOS NO README E REUNIÃO =====

def create_efficiency_chart(start_date=None, end_date=None):
    """Gráfico de Eficiência Operacional - Fórmula: (production_time / (production_time + downtime)) * 100"""
    
    # Construir filtro de data
    date_filter = "WHERE \"Time_Stamp\" >= CURRENT_DATE - INTERVAL '30 days'"
    if start_date and end_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}' AND \"Time_Stamp\" <= '{end_date}'"
    elif start_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE \"Time_Stamp\" <= '{end_date}'"
    
    query = f"""
    SELECT 
        "Time_Stamp" as timestamp,
        "C1" as production_time,  -- Tempo de produção (minutos)
        "C0" as downtime,         -- Tempo parado (minutos)
        "C4" as production_weight -- Produção em quilos
    FROM "Rel_Diario"
    {date_filter}
    ORDER BY "Time_Stamp" DESC
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de eficiência", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    # Converter para numérico e tratar valores inválidos
    df['production_time'] = pd.to_numeric(df['production_time'], errors='coerce').fillna(0)
    df['downtime'] = pd.to_numeric(df['downtime'], errors='coerce').fillna(0)
    
    # Cálculo da eficiência conforme README
    # Evitar divisão por zero
    total_time = df['production_time'] + df['downtime']
    df['efficiency_calculated'] = ((df['production_time'] / total_time.replace(0, 1)) * 100).round(2)
    
    # Filtrar apenas registros com tempo total > 0
    df = df[total_time > 0]
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['efficiency_calculated'],
        mode='lines+markers',
        name='Eficiência (%)',
        line=dict(color='#2ecc71', width=3),
        marker=dict(size=6)
    ))
    
    # Linha de meta (85%)
    fig.add_hline(y=85, line_dash="dash", line_color="red", 
                  annotation_text="Meta: 85%")
    
    fig.update_layout(
        title="Eficiência Operacional - (Tempo Produção / Tempo Total) x 100",
        xaxis_title="Data/Hora",
        yaxis_title="Eficiência (%)",
        hovermode='x unified',
        template='plotly_white',
        yaxis=dict(range=[0, 100])
    )
    
    return fig

def create_alarm_timeline_by_severity_chart(start_date=None, end_date=None):
    """Timeline de alarmes por dia com pilha por severidade (prioridade).

    Mostra a quantidade diária de alarmes por prioridade (1=Crítico..5=Info).
    """
    # Filtro temporal (padrão: últimos 14 dias)
    if start_date and end_date:
        time_filter = f"WHERE \"Al_Start_Time\" >= '{start_date}' AND \"Al_Start_Time\" <= '{end_date}'"
    elif start_date:
        time_filter = f"WHERE \"Al_Start_Time\" >= '{start_date}'"
    elif end_date:
        time_filter = f"WHERE \"Al_Start_Time\" <= '{end_date}'"
    else:
        time_filter = "WHERE \"Al_Start_Time\" >= CURRENT_DATE - INTERVAL '14 days' AND \"Al_Start_Time\" <= CURRENT_TIMESTAMP"

    query = f"""
    WITH base AS (
        SELECT 
            DATE("Al_Start_Time") AS day,
            COALESCE("Al_Priority", 5) AS priority
        FROM "ALARMHISTORY"
        {time_filter}
    )
    SELECT 
        day,
        priority,
        COUNT(*) AS qty
    FROM base
    GROUP BY day, priority
    ORDER BY day ASC, priority ASC
    """

    df = execute_query(query)
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de alarmes no período",
                                          xref="paper", yref="paper",
                                          x=0.5, y=0.5, showarrow=False)

    # Mapear prioridade para rótulo e cor
    priority_map = {1: 'Crítico', 2: 'Alto', 3: 'Médio', 4: 'Baixo', 5: 'Info'}
    color_map = {
        'Crítico': '#e74c3c',
        'Alto': '#f39c12',
        'Médio': '#f1c40f',
        'Baixo': '#3498db',
        'Info': '#95a5a6'
    }
    df['priority_label'] = df['priority'].map(priority_map).fillna('Info')

    # Pivot para colunas por severidade (período atual)
    pivot = df.pivot_table(index='day', columns='priority_label', values='qty', aggfunc='sum', fill_value=0)
    pivot = pivot.sort_index()

    fig = go.Figure()

    # Determinar datas do período atual
    import pandas as pd
    from datetime import datetime, timedelta
    cur_start = pd.to_datetime(pivot.index.min()).date()
    cur_end = pd.to_datetime(pivot.index.max()).date()
    period_days = (cur_end - cur_start).days + 1

    # Consultar período anterior por severidade
    prev_query = f"""
    WITH base AS (
        SELECT 
            DATE("Al_Start_Time") AS day,
            COALESCE("Al_Priority", 5) AS priority
        FROM "ALARMHISTORY"
        WHERE "Al_Start_Time" >= '{cur_start - timedelta(days=period_days)}' 
          AND "Al_Start_Time" <= '{cur_end - timedelta(days=period_days)}'
    )
    SELECT day, priority, COUNT(*) AS qty FROM base GROUP BY day, priority ORDER BY day ASC, priority ASC
    """
    prev_df = execute_query(prev_query)
    if not prev_df.empty:
        prev_df['priority_label'] = prev_df['priority'].map(priority_map).fillna('Info')
        prev_df['day'] = pd.to_datetime(prev_df['day'])
        prev_df['day_shifted'] = prev_df['day'] + pd.Timedelta(days=period_days)
        prev_pivot = prev_df.pivot_table(index='day_shifted', columns='priority_label', values='qty', aggfunc='sum', fill_value=0)
        prev_pivot = prev_pivot.sort_index()
    else:
        prev_pivot = pd.DataFrame()

    # Adicionar linhas por severidade (Atual e Anterior com linha tracejada)
    for label in ['Crítico', 'Alto', 'Médio', 'Baixo', 'Info']:
        if label in pivot.columns:
            fig.add_trace(
                go.Scatter(
                    x=pivot.index,
                    y=pivot[label],
                    mode='lines+markers',
                    name=f"{label} (Atual)",
                    line=dict(color=color_map.get(label, '#95a5a6'), width=2),
                    marker=dict(size=5),
                    hovertemplate='<b>%{x}</b><br>'+label+' (Atual): %{y} alarmes<extra></extra>'
                )
            )
        if not prev_pivot.empty and label in prev_pivot.columns:
            fig.add_trace(
                go.Scatter(
                    x=prev_pivot.index,
                    y=prev_pivot[label],
                    mode='lines',
                    name=f"{label} (Anterior)",
                    line=dict(color=color_map.get(label, '#95a5a6'), dash='dash', width=2),
                    hovertemplate='<b>%{x}</b><br>'+label+' (Anterior): %{y} alarmes<extra></extra>'
                )
            )

    # (Removida linha única de total anterior; agora há comparação por severidade)

    fig.update_layout(
        title='Timeline de Alarmes por Severidade (Atual vs Anterior)',
        xaxis_title='Dia',
        yaxis_title='Quantidade de Alarmes',
        template='plotly_white',
        hovermode='x unified',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
    )

    return fig

def create_alarm_severity_distribution_chart(start_date=None, end_date=None):
    """Distribuição de Alarmes por Severidade (Prioridade) no período.

    Prioridades (Al_Priority): 1 Crítico, 2 Alto, 3 Médio, 4 Baixo, 5 Info
    """
    # Filtro de período padrão: últimos 7 dias
    if start_date and end_date:
        time_filter = f"WHERE \"Al_Start_Time\" >= '{start_date}' AND \"Al_Start_Time\" <= '{end_date}'"
    elif start_date:
        time_filter = f"WHERE \"Al_Start_Time\" >= '{start_date}'"
    elif end_date:
        time_filter = f"WHERE \"Al_Start_Time\" <= '{end_date}'"
    else:
        time_filter = "WHERE \"Al_Start_Time\" >= CURRENT_DATE - INTERVAL '7 days' AND \"Al_Start_Time\" <= CURRENT_TIMESTAMP"

    query = f"""
    SELECT 
        COALESCE("Al_Priority", 5) as priority,
        COUNT(*) as qty
    FROM "ALARMHISTORY"
    {time_filter}
    GROUP BY COALESCE("Al_Priority", 5)
    ORDER BY priority ASC
    """

    df = execute_query(query)

    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de severidade de alarmes",
                                          xref="paper", yref="paper",
                                          x=0.5, y=0.5, showarrow=False)

    priority_map = {1: 'Crítico', 2: 'Alto', 3: 'Médio', 4: 'Baixo', 5: 'Info'}
    color_map = {
        'Crítico': '#e74c3c',
        'Alto': '#f39c12',
        'Médio': '#f1c40f',
        'Baixo': '#3498db',
        'Info': '#95a5a6'
    }
    df['priority_label'] = df['priority'].map(priority_map).fillna('Info')

    fig = go.Figure(data=[
        go.Pie(
            labels=df['priority_label'],
            values=df['qty'],
            hole=0.45,
            marker=dict(colors=[color_map.get(x, '#95a5a6') for x in df['priority_label']]),
            textinfo='label+percent+value',
            hovertemplate='<b>%{label}</b><br>Quantidade: %{value}<br>Percentual: %{percent}<extra></extra>'
        )
    ])

    fig.update_layout(
        title="Distribuição por Severidade (Últimos 7 dias)",
        template='plotly_white',
        height=380
    )

    return fig

def create_water_consumption_chart(start_date=None, end_date=None):
    """Gráfico de Consumo de Água por Quilo - Fórmula: (water_consumption * 1000) / production_weight"""
    
    # Construir filtro de data
    date_filter = "WHERE \"Time_Stamp\" >= CURRENT_DATE - INTERVAL '30 days' AND \"C4\" > 0"
    if start_date and end_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}' AND \"Time_Stamp\" <= '{end_date}' AND \"C4\" > 0"
    elif start_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}' AND \"C4\" > 0"
    elif end_date:
        date_filter = f"WHERE \"Time_Stamp\" <= '{end_date}' AND \"C4\" > 0"
    
    query = f"""
    SELECT 
        "Time_Stamp" as timestamp,
        "C2" as water_consumption, -- Consumo de água (m³)
        "C4" as production_weight,  -- Produção em quilos
        ("C2" * 1000) as total_water_liters
    FROM "Rel_Diario"
    {date_filter}
    ORDER BY "Time_Stamp" ASC
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de consumo de água", 
                                        xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    # Converter para numérico e tratar divisão por zero
    df['water_consumption'] = pd.to_numeric(df['water_consumption'], errors='coerce').fillna(0)
    df['production_weight'] = pd.to_numeric(df['production_weight'], errors='coerce').fillna(1)
    df['total_water_liters'] = pd.to_numeric(df['total_water_liters'], errors='coerce').fillna(0)
    df['production_weight'] = df['production_weight'].replace(0, 1)
    df['water_per_kg'] = (df['total_water_liters'] / df['production_weight']).round(2)
    
    # Calcular média móvel de 3 pontos
    df['water_per_kg_ma'] = df['water_per_kg'].rolling(window=3, center=True).mean()
    
    # Criar gráfico de barras mais claro para mobile
    fig = go.Figure()
    
    # Adicionar valores como texto nas barras
    fig.add_trace(go.Bar(
        x=df['timestamp'],
        y=df['water_per_kg'],
        name='Eficiência Hídrica',
        marker_color=['#27ae60' if x <= 18 else '#f39c12' if x <= 20 else '#e74c3c' for x in df['water_per_kg']],
        text=[f'{x:.1f}' for x in df['water_per_kg']],
        textposition='outside',
        textfont=dict(size=10, color='black'),
        hovertemplate='<b>%{x}</b><br>Consumo: %{y:.2f} L/kg<extra></extra>'
    ))
    
    # Zona de meta (12-18 L/kg)
    fig.add_hrect(y0=12, y1=18, fillcolor="green", opacity=0.1, 
                  annotation_text="Zona Ideal: 12-18 L/kg", annotation_position="top left")
    
    # Linha de alerta (20 L/kg)
    fig.add_hline(y=20, line_dash="dash", line_color="red", 
                  annotation_text="Alerta: 20 L/kg", annotation_position="right")
    
    # Calcular estatísticas
    avg_consumption = df['water_per_kg'].mean()
    max_consumption = df['water_per_kg'].max()
    min_consumption = df['water_per_kg'].min()
    
    fig.update_layout(
        title=f"Eficiência Hídrica<br><sub>Média: {avg_consumption:.1f} L/kg | Meta: 12-18 L/kg</sub>",
        xaxis_title="Período",
        yaxis_title="Litros por Kg",
        template='plotly_white',
        showlegend=False,
        height=350,
        margin=dict(t=80, b=40, l=40, r=40)
    )
    
    return fig

def create_chemical_consumption_chart(start_date=None, end_date=None):
    """Gráfico de Consumo de Químicos por Quilo - Fórmula: chemical_n / production_weight"""
    
    # Construir filtro de data
    date_filter = "WHERE rq.\"Time_Stamp\" >= CURRENT_DATE - INTERVAL '30 days' AND rd.\"C4\" > 0"
    if start_date and end_date:
        date_filter = f"WHERE rq.\"Time_Stamp\" >= '{start_date}' AND rq.\"Time_Stamp\" <= '{end_date}' AND rd.\"C4\" > 0"
    elif start_date:
        date_filter = f"WHERE rq.\"Time_Stamp\" >= '{start_date}' AND rd.\"C4\" > 0"
    elif end_date:
        date_filter = f"WHERE rq.\"Time_Stamp\" <= '{end_date}' AND rd.\"C4\" > 0"
    
    query = f"""
    SELECT 
        rq."Time_Stamp" as timestamp,
        rq."Q1" as chemical_1,
        rq."Q2" as chemical_2,
        rq."Q3" as chemical_3,
        rq."Q4" as chemical_4,
        rq."Q5" as chemical_5,
        rq."Q6" as chemical_6,
        rq."Q7" as chemical_7,
        rq."Q8" as chemical_8,
        rq."Q9" as chemical_9,
        rd."C4" as production_weight
    FROM "Rel_Quimico" rq
    LEFT JOIN "Rel_Diario" rd ON DATE(rq."Time_Stamp") = DATE(rd."Time_Stamp")
    {date_filter}
    ORDER BY rq."Time_Stamp" DESC
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de químicos", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    # Converter para numérico e tratar valores inválidos
    for i in range(1, 10):  # chemical_1 a chemical_9
        df[f'chemical_{i}'] = pd.to_numeric(df[f'chemical_{i}'], errors='coerce').fillna(0)
    
    df['production_weight'] = pd.to_numeric(df['production_weight'], errors='coerce').fillna(1)
    
    # Cálculos de consumo por quilo conforme README: quimico_n_por_kg = chemical_n / production_weight
    # Evitar divisão por zero
    df['production_weight'] = df['production_weight'].replace(0, 1)
    
    for i in range(1, 10):  # chemical_1 a chemical_9
        df[f'chemical_{i}_per_kg'] = (df[f'chemical_{i}'] / df['production_weight']).round(3)
    
    fig = go.Figure()
    
    # Cores para os 9 químicos
    colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6', 
              '#1abc9c', '#e67e22', '#34495e', '#95a5a6']
    
    # Adicionar traces para todos os 9 químicos conforme README
    for i in range(1, 10):  # chemical_1 a chemical_9
        col_name = f'chemical_{i}_per_kg'
        if col_name in df.columns and df[col_name].sum() > 0:
            fig.add_trace(go.Scatter(
                x=df['timestamp'], 
                y=df[col_name],
                mode='lines+markers', 
                name=f'Químico {i}',
                line=dict(color=colors[i-1], width=2),
                hovertemplate=f'<b>Químico {i}</b><br>Data: %{{x}}<br>Consumo: %{{y:.3f}} ml/kg<extra></extra>'
            ))
    
    fig.update_layout(
        title={
            'text': "📊 Consumo de Químicos por Quilo Produzido",
            'x': 0.5,
            'xanchor': 'center'
        },
        xaxis_title="📅 Data",
        yaxis_title="🧪 Consumo (ml/kg)",
        hovermode='x unified',
        showlegend=True,
        height=450,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(size=12),
        margin=dict(l=50, r=50, t=80, b=50)
    )
    
    return fig

def create_top_alarms_chart(start_date=None, end_date=None):
    """Top 10 Alarmes Mais Frequentes - Respeita período de análise"""
    
    # Construir filtro de data - usar apenas bound inferior para ambos os campos
    if start_date and end_date:
        # Usar apenas limite inferior para ambos os campos (como na origem)
        date_filter = (
            f"WHERE \"Al_Start_Time\" >= '{start_date}' AND \"Al_Norm_Time\" >= '{start_date}'"
        )
        period_label = f"(desde {start_date})"
    elif start_date:
        # Quando apenas início é informado, usar limites inferiores (>=) para ambos os campos
        date_filter = (
            f"WHERE \"Al_Start_Time\" >= '{start_date}' AND \"Al_Norm_Time\" >= '{start_date}'"
        )
        period_label = f"(desde {start_date})"
    elif end_date:
        # Caso raro: apenas fim informado, considerar tudo até o fim para ambos os campos
        date_filter = (
            f"WHERE \"Al_Start_Time\" <= '{end_date} 23:59:59' AND \"Al_Norm_Time\" <= '{end_date} 23:59:59'"
        )
        period_label = f"(até {end_date})"
    else:
        # Padrão: últimos 7 dias usando limite inferior
        date_filter = (
            "WHERE \"Al_Start_Time\" >= CURRENT_DATE - INTERVAL '7 days' "
            "AND \"Al_Norm_Time\" >= CURRENT_DATE - INTERVAL '7 days'"
        )
        period_label = "(últimos 7 dias)"
    
    query = f"""
    SELECT 
        "Al_Tag" as alarm_tag,
        "Al_Message" as alarm_message,
        "Al_Selection" as area,
        COUNT(*) as frequency,
        AVG(EXTRACT(EPOCH FROM ("Al_Norm_Time" - "Al_Start_Time"))/60) as avg_duration_minutes
    FROM "ALARMHISTORY"
    {date_filter}
    GROUP BY "Al_Tag", "Al_Message", "Al_Selection"
    ORDER BY frequency DESC
    LIMIT 10
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de alarmes", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    # Truncar mensagens muito longas
    df['alarm_display'] = df['alarm_tag'] + ': ' + df['alarm_message'].str[:30] + '...'
    
    fig = go.Figure(data=[
        go.Bar(
            x=df['frequency'],
            y=df['alarm_display'],
            orientation='h',
            marker_color='#e74c3c',
            text=df['frequency'],
            textposition='auto',
            hovertemplate='<b>%{y}</b><br>Frequência: %{x}<br>Área: %{customdata[0]}<br>Duração Média: %{customdata[1]:.1f} min<extra></extra>',
            customdata=list(zip(df['area'], df['avg_duration_minutes'].fillna(0)))
        )
    ])
    
    fig.update_layout(
        title=f"Top 10 Alarmes Mais Frequentes {period_label}",
        xaxis_title="Frequência",
        yaxis_title="Alarme",
        template='plotly_white',
        height=400
    )
    
    return fig

# [REMOVIDO] create_alarm_analysis_chart (frequência vs tempo ativo por área) por baixa clareza

def create_production_by_client_chart(start_date=None, end_date=None, client_filter=None):
    """Produção por Cliente - Cruzamento Rel_Carga com clientes"""
    
    # Construir filtro de data
    date_filter = "WHERE rc.\"Time_Stamp\" >= CURRENT_DATE - INTERVAL '30 days'"
    if start_date and end_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" >= '{start_date}' AND rc.\"Time_Stamp\" <= '{end_date}'"
    elif start_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" <= '{end_date}'"
    
    # Adicionar filtro de cliente se especificado
    if client_filter:
        if 'WHERE' in date_filter:
            date_filter += f" AND rc.\"C1\" = '{client_filter}'"
        else:
            date_filter = f"WHERE rc.\"C1\" = '{client_filter}'"
    
    query = f"""
    SELECT 
        COALESCE(a.alias, CAST(rc."C1" AS TEXT)) as client_display,
        rc."C1" as client_id,
        COUNT(*) as total_loads,
        SUM(rc."C2") as total_weight_kg,
        AVG(rc."C2") as avg_weight_per_load
    FROM "Rel_Carga" rc
    LEFT JOIN app.client_alias a ON CAST(rc."C1" AS INTEGER) = a.client_id
    {date_filter}
    GROUP BY a.alias, rc."C1"
    ORDER BY total_weight_kg DESC
    LIMIT 15
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de produção por cliente", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=df['client_display'],
        y=df['total_weight_kg'],
        name='Peso Total (kg)',
        marker_color='#3498db',
        text=df['total_weight_kg'].round(0),
        textposition='auto',
        hovertemplate='<b>%{x}</b><br>Peso Total: %{y:.0f} kg<br>Cargas: %{customdata[0]}<br>Média/Carga: %{customdata[1]:.1f} kg<extra></extra>',
        customdata=list(zip(df['total_loads'], df['avg_weight_per_load']))
    ))
    
    fig.update_layout(
        title="Produção por Cliente (Últimos 30 dias)",
        xaxis_title="Cliente",
        yaxis_title="Peso Total (kg)",
        template='plotly_white',
        xaxis_tickangle=-45
    )
    
    return fig

def create_production_by_program_chart(start_date=None, end_date=None, client_filter=None):
    """Produção por Programa - Cruzamento Rel_Carga com programas"""
    
    # Construir filtro de data
    date_filter = "WHERE rc.\"Time_Stamp\" >= CURRENT_DATE - INTERVAL '30 days'"
    if start_date and end_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" >= '{start_date}' AND rc.\"Time_Stamp\" <= '{end_date}'"
    elif start_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE rc.\"Time_Stamp\" <= '{end_date}'"
    
    # Adicionar filtro de cliente se especificado
    if client_filter:
        if 'WHERE' in date_filter:
            date_filter += f" AND rc.\"C1\" = '{client_filter}'"
        else:
            date_filter = f"WHERE rc.\"C1\" = '{client_filter}'"
    
    query = f"""
    SELECT 
        p.program_name,
        rc."C0" as program_id,
        COUNT(*) as total_loads,
        SUM(rc."C2") as total_weight_kg,
        AVG(rc."C2") as avg_weight_per_load
    FROM "Rel_Carga" rc
    LEFT JOIN programas p ON rc."C0" = p.program_id
    {date_filter}
    GROUP BY p.program_name, rc."C0"
    ORDER BY total_weight_kg DESC
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de produção por programa", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    # Tratar programas sem nome
    df['program_display'] = df['program_name'].fillna("Programa " + df['program_id'].astype(str))
    
    colors = ['#e74c3c', '#f39c12', '#2ecc71', '#9b59b6', '#1abc9c']
    
    fig = go.Figure(data=[
        go.Pie(
            labels=df['program_display'],
            values=df['total_weight_kg'],
            marker_colors=colors[:len(df)],
            hole=0.4,
            textinfo='label+percent+value',
            hovertemplate='<b>%{label}</b><br>Peso: %{value:.0f} kg<br>Percentual: %{percent}<br>Cargas: %{customdata[0]}<br>Média/Carga: %{customdata[1]:.1f} kg<extra></extra>',
            customdata=list(zip(df['total_loads'], df['avg_weight_per_load']))
        )
    ])
    
    fig.update_layout(
        title="Distribuição da Produção por Programa (Últimos 30 dias)",
        template='plotly_white'
    )
    
    return fig

# ===== FUNÇÕES AUXILIARES =====

def format_number_abbreviated(value):
    """Formatar números com abreviações (k, M, B)"""
    if pd.isna(value) or value == 0:
        return "0"
    
    abs_value = abs(value)
    
    if abs_value >= 1_000_000_000:
        return f"{value/1_000_000_000:.1f}B"
    elif abs_value >= 1_000_000:
        return f"{value/1_000_000:.1f}M"
    elif abs_value >= 1_000:
        return f"{value/1_000:.1f}k"
    else:
        return f"{value:.0f}"

def get_kpi_tooltip(kpi_name, value, description):
    """Gerar tooltip informativo para KPIs"""
    tooltips = {
        'quilos_lavados_hoje': f"Produção total de hoje: {value} kg\nMeta diária: 2.000 kg",
        'litros_agua_hoje': f"Consumo de água hoje: {value} L\nMeta: 12-18 L/kg",
        'ml_quimicos_hoje': f"Consumo de químicos: {value} ml\nOtimização em andamento",
        'alarmes_ativos': f"Alarmes ativos: {value}\nMonitoramento 24/7",
        'eficiencia_media': f"Eficiência operacional: {value}%\nMeta: >85%"
    }
    return tooltips.get(kpi_name, description)

# ===== KPIs E TABELAS =====

def get_operational_kpis(start_date=None, end_date=None, client_filter=None):
    """Calcula KPIs operacionais principais com foco em produção e consumos
    
    Args:
        start_date: Data de início para filtro (opcional)
        end_date: Data de fim para filtro (opcional) 
        client_filter: Filtro de cliente (opcional)
        
    Returns:
        dict: KPIs com dados separados para 'hoje' (dia atual) e 'periodo' (intervalo selecionado)
    """
    
    from datetime import datetime, date
    
    # Dados de "hoje" vêm da tabela Rel_Carga (cargas do dia atual)
    # Dados históricos vêm da tabela Rel_Diario (registros consolidados)
    today = date.today()
    
    # Para a tabela Sts_Dados, vamos usar dois filtros de data diferentes:
    # 1. Para o Resumo Executivo: dados do dia atual (hoje)
    # 2. Para os KPIs principais: dados da data mais recente disponível
    
    # Consulta para obter a data mais recente disponível na tabela Sts_Dados
    sts_dados_hoje_query = """
    WITH latest_date AS (
        SELECT MAX("Time_Stamp"::date) as max_date FROM "Sts_Dados"
    )
    SELECT max_date FROM latest_date
    """
    
    # Consulta para verificar se existem dados para o dia atual
    sts_dados_hoje_check_query = f"""
    SELECT COUNT(*) as count FROM "Sts_Dados"
    WHERE "Time_Stamp"::date = '{today}'::date
    """
    
    try:
        # Verificar se existem dados para o dia atual
        today_data_check = execute_query(sts_dados_hoje_check_query)
        has_today_data = today_data_check.iloc[0]['count'] > 0 if not today_data_check.empty else False
        
        # Obter a data mais recente disponível na tabela Sts_Dados
        latest_date_df = execute_query(sts_dados_hoje_query)
        if not latest_date_df.empty and latest_date_df.iloc[0]['max_date'] is not None:
            latest_date = latest_date_df.iloc[0]['max_date']
            print(f"📊 Dados mais recentes disponíveis na tabela Sts_Dados: {latest_date}")
        else:
            latest_date = today
            print(f"⚠️ Não foi possível obter a data mais recente da tabela Sts_Dados. Usando data atual: {today}")
            
        # Definir a data a ser usada para o Resumo Executivo
        if has_today_data:
            print(f"📊 Usando dados do dia atual ({today}) para o Resumo Executivo")
            resumo_exec_date = today
        else:
            print(f"⚠️ Não há dados para hoje na tabela Sts_Dados. Usando data mais recente ({latest_date}) para o Resumo Executivo")
            resumo_exec_date = latest_date
    except Exception as e:
        latest_date = today
        resumo_exec_date = today
        print(f"❌ Erro ao verificar datas na tabela Sts_Dados: {e}. Usando data atual: {today}")
    
    # Filtro para dados de hoje nas tabelas tradicionais
    date_filter_hoje_carga = f"\"Time_Stamp\" >= '{today}'::date AND \"Time_Stamp\" < '{today}'::date + INTERVAL '1 day'"
    
    # Filtro para dados mais recentes na tabela Sts_Dados (para KPIs principais)
    date_filter_sts_hoje = f"\"Time_Stamp\"::date = '{latest_date}'::date"
    
    # Filtro para dados do dia atual ou mais recentes na tabela Sts_Dados (para Resumo Executivo)
    date_filter_resumo_exec = f"\"Time_Stamp\"::date = '{resumo_exec_date}'::date"
    
    print(f"📊 Buscando dados de HOJE ({today}) na tabela Rel_Carga (cargas do dia)")
    hoje_label = f"Hoje ({today})"
    
    # Filtros para o período selecionado ou padrão
    if start_date and end_date:
        # Período personalizado selecionado pelo usuário
        date_filter_periodo = f"\"Time_Stamp\" >= '{start_date}' AND \"Time_Stamp\" <= '{end_date}'"
        periodo_label = f"Período: {start_date} a {end_date}"
        print(f"Calculando KPIs - Hoje: {today} | Período: {start_date} a {end_date}")
    else:
        # Período padrão: últimos 7 dias
        date_filter_periodo = "\"Time_Stamp\" >= CURRENT_DATE - INTERVAL '7 days'"
        periodo_label = "Últimos 7 dias"
        print(f"Calculando KPIs - Hoje: {today} | Período: últimos 7 dias")
    
    # Filtro de cliente
    client_filter_sql = ""
    if client_filter and client_filter != 'all':
        client_filter_sql = f""" AND "C5" = {client_filter}"""
    
    # Dados da tabela Sts_Dados para HOJE (último registro - valores cumulativos)
    sts_hoje_query = f"""
    SELECT 
        COALESCE("D3", 0) as quilos_lavados_hoje,
        COALESCE("D2", 0) as batchs_hoje,
        COALESCE("D1", 0) * 1000 as litros_agua_hoje,
        CASE 
            WHEN "D2" > 0 THEN ROUND(CAST("D3" / "D2" AS NUMERIC), 2)
            ELSE 0 
        END as peso_medio_hoje,
        CASE 
            WHEN "D3" > 0 THEN ROUND(CAST(("D1" * 1000) / "D3" AS NUMERIC), 2)
            ELSE 0 
        END as litros_por_kg_hoje
    FROM "Sts_Dados"
    WHERE {date_filter_sts_hoje}
    ORDER BY "Time_Stamp" DESC
    LIMIT 1
    """
    
    # Usar ÚLTIMO registro de Sts_Dados (valor mais recente, não soma)
    sts_resumo_exec_query = f"""
    SELECT 
        COALESCE("D3", 0) as quilos_lavados_resumo,
        COALESCE("D2", 0) as batchs_resumo,
        COALESCE("D1", 0) * 1000 as litros_agua_resumo,
        CASE 
            WHEN "D2" > 0 THEN ROUND(CAST("D3" / "D2" AS NUMERIC), 2)
            ELSE 0 
        END as peso_medio_resumo,
        CASE 
            WHEN "D3" > 0 THEN ROUND(CAST(("D1" * 1000) / "D3" AS NUMERIC), 2)
            ELSE 0 
        END as litros_por_kg_resumo
    FROM "Sts_Dados"
    WHERE {date_filter_resumo_exec}
    ORDER BY "Time_Stamp" DESC
    LIMIT 1
    """
    
    # Dados do PERÍODO - usar Rel_Diario como no gráfico de água
    sts_periodo_query = f"""
    SELECT 
        COALESCE(SUM("C4"), 0) as quilos_lavados_periodo,
        COUNT(*) as batchs_periodo,
        COALESCE(SUM("C2") * 1000, 0) as litros_agua_periodo,
        CASE 
            WHEN COUNT(*) > 0 THEN ROUND(CAST(SUM("C4") / COUNT(*) AS NUMERIC), 2)
            ELSE 0 
        END as peso_medio_periodo,
        CASE 
            WHEN SUM("C4") > 0 THEN ROUND(CAST((SUM("C2") * 1000) / SUM("C4") AS NUMERIC), 2)
            ELSE 0 
        END as litros_por_kg_periodo
    FROM "Rel_Diario"
    WHERE {date_filter_periodo} AND "C4" > 0
    """
    
    # Produção HOJE (dia atual) - usar Rel_Carga (dados em tempo real)
    production_hoje_query = f"""
    SELECT 
        COALESCE(SUM("C2"), 0) as quilos_lavados_hoje,
        COUNT(*) as ciclos_hoje
    FROM "Rel_Carga"
    WHERE {date_filter_hoje_carga}
      AND "C2" > 0
    """
    
    # Produção PERÍODO (intervalo selecionado) - usar Rel_Diario
    production_periodo_query = f"""
    SELECT 
        COALESCE(SUM("C4"), 0) as quilos_lavados_periodo,
        COUNT(*) as ciclos_periodo
    FROM "Rel_Diario"
    WHERE {date_filter_periodo}
      AND "C4" > 0{client_filter_sql}
    """
    
    # Consumo de água HOJE (dia atual) - usar Rel_Carga
    water_hoje_query = f"""
    SELECT 
        COALESCE(SUM("C3"), 0) * 1000 as litros_agua_hoje,
        CASE 
            WHEN SUM("C2") > 0 THEN ROUND(CAST((SUM("C3") * 1000) / SUM("C2") AS NUMERIC), 2)
            ELSE 0 
        END as litros_por_kg_hoje
    FROM "Rel_Carga"
    WHERE {date_filter_hoje_carga}
      AND "C2" > 0 AND "C3" > 0
    """
    
    # Consumo de água PERÍODO (intervalo selecionado) - usar Rel_Diario
    water_periodo_query = f"""
    SELECT 
        COALESCE(SUM("C2"), 0) * 1000 as litros_agua_periodo,
        CASE 
            WHEN SUM("C4") > 0 THEN ROUND(CAST((SUM("C2") * 1000) / SUM("C4") AS NUMERIC), 2)
            ELSE 0 
        END as litros_por_kg_periodo
    FROM "Rel_Diario"
    WHERE {date_filter_periodo}
      AND "C4" > 0{client_filter_sql}
    """
    
    # Consumo de químicos HOJE (dia atual) - usar produção do Sts_Dados para o denominador (consistência do Resumo Executivo)
    chemical_hoje_query = f"""
    SELECT 
        COALESCE(SUM("Q1" + "Q2" + "Q3" + "Q4" + "Q5" + "Q6" + "Q7" + "Q8" + "Q9"), 0) as ml_quimicos_hoje,
        CASE 
            WHEN (SELECT "D3" FROM "Sts_Dados" WHERE {date_filter_resumo_exec} ORDER BY "Time_Stamp" DESC LIMIT 1) > 0 
            THEN ROUND(CAST(SUM("Q1" + "Q2" + "Q3" + "Q4" + "Q5" + "Q6" + "Q7" + "Q8" + "Q9") / 
                 (SELECT "D3" FROM "Sts_Dados" WHERE {date_filter_resumo_exec} ORDER BY "Time_Stamp" DESC LIMIT 1) AS NUMERIC), 3)
            ELSE 0 
        END as ml_quimicos_por_kg_hoje
    FROM "Rel_Quimico"
    WHERE "Time_Stamp"::date = '{resumo_exec_date}'::date
    """
    
    # Consumo de químicos PERÍODO (intervalo selecionado)
    chemical_periodo_query = f"""
    SELECT 
        COALESCE(SUM("Q1" + "Q2" + "Q3" + "Q4" + "Q5" + "Q6" + "Q7" + "Q8" + "Q9"), 0) as ml_quimicos_periodo,
        CASE 
            WHEN (SELECT SUM("C4") FROM "Rel_Diario" WHERE {date_filter_periodo} AND "C4" > 0) > 0 
            THEN ROUND(CAST(SUM("Q1" + "Q2" + "Q3" + "Q4" + "Q5" + "Q6" + "Q7" + "Q8" + "Q9") / 
                 (SELECT SUM("C4") FROM "Rel_Diario" WHERE {date_filter_periodo} AND "C4" > 0) AS NUMERIC), 3)
            ELSE 0 
        END as ml_quimicos_por_kg_periodo
    FROM "Rel_Quimico"
    WHERE {date_filter_periodo}
    """
    
    # Eficiência média - Fórmula correta: (tempo produção / (tempo produção + tempo parado)) * 100
    efficiency_query = f"""
    SELECT 
        CASE 
            WHEN SUM("C1" + "C0") > 0 THEN ROUND(CAST((SUM("C1") / SUM("C1" + "C0")) * 100 AS NUMERIC), 1)
            ELSE 0
        END as eficiencia_media
    FROM "Rel_Diario"
    WHERE {date_filter_periodo}
      AND "C1" > 0 AND "C0" >= 0{client_filter_sql}
    """
    
    # Alarmes ativos - otimizado: usar índice composto
    alarms_query = f"""
    SELECT COUNT(*) as alarmes_ativos
    FROM "ALARMHISTORY"
    WHERE "Al_Start_Time" >= '{today}'::date
      AND "Al_Start_Time" < '{today}'::date + INTERVAL '1 day'
      AND "Al_Norm_Time" IS NULL
    """
    
    try:
        # Executar todas as queries
        sts_hoje_df = execute_query(sts_hoje_query)
        sts_periodo_df = execute_query(sts_periodo_query)
        sts_resumo_exec_df = execute_query(sts_resumo_exec_query)  # Nova query para o Resumo Executivo
        production_hoje_df = execute_query(production_hoje_query)
        production_periodo_df = execute_query(production_periodo_query)
        water_hoje_df = execute_query(water_hoje_query)
        water_periodo_df = execute_query(water_periodo_query)
        chemical_hoje_df = execute_query(chemical_hoje_query)
        chemical_periodo_df = execute_query(chemical_periodo_query)
        efficiency_df = execute_query(efficiency_query)
        alarms_df = execute_query(alarms_query)
        
        # Extrair valores brutos - HOJE (dia atual) da tabela Sts_Dados
        quilos_hoje = float(sts_hoje_df.iloc[0]['quilos_lavados_hoje']) if not sts_hoje_df.empty and sts_hoje_df.iloc[0]['quilos_lavados_hoje'] is not None else 0
        litros_hoje = float(sts_hoje_df.iloc[0]['litros_agua_hoje']) if not sts_hoje_df.empty and sts_hoje_df.iloc[0]['litros_agua_hoje'] is not None else 0
        ml_quimicos_hoje = float(chemical_hoje_df.iloc[0]['ml_quimicos_hoje']) if not chemical_hoje_df.empty and chemical_hoje_df.iloc[0]['ml_quimicos_hoje'] is not None else 0
        peso_medio_hoje = float(sts_hoje_df.iloc[0]['peso_medio_hoje']) if not sts_hoje_df.empty and sts_hoje_df.iloc[0]['peso_medio_hoje'] is not None else 0
        batchs_hoje = int(sts_hoje_df.iloc[0]['batchs_hoje']) if not sts_hoje_df.empty and sts_hoje_df.iloc[0]['batchs_hoje'] is not None else 0
        litros_por_kg_hoje = float(sts_hoje_df.iloc[0]['litros_por_kg_hoje']) if not sts_hoje_df.empty and sts_hoje_df.iloc[0]['litros_por_kg_hoje'] is not None else 0
        
        # Extrair valores brutos para o Resumo Executivo (dia atual ou mais recente)
        quilos_resumo = float(sts_resumo_exec_df.iloc[0]['quilos_lavados_resumo']) if not sts_resumo_exec_df.empty and sts_resumo_exec_df.iloc[0]['quilos_lavados_resumo'] is not None else 0
        litros_resumo = float(sts_resumo_exec_df.iloc[0]['litros_agua_resumo']) if not sts_resumo_exec_df.empty and sts_resumo_exec_df.iloc[0]['litros_agua_resumo'] is not None else 0
        peso_medio_resumo = float(sts_resumo_exec_df.iloc[0]['peso_medio_resumo']) if not sts_resumo_exec_df.empty and sts_resumo_exec_df.iloc[0]['peso_medio_resumo'] is not None else 0
        batchs_resumo = int(sts_resumo_exec_df.iloc[0]['batchs_resumo']) if not sts_resumo_exec_df.empty and sts_resumo_exec_df.iloc[0]['batchs_resumo'] is not None else 0
        litros_por_kg_resumo = float(sts_resumo_exec_df.iloc[0]['litros_por_kg_resumo']) if not sts_resumo_exec_df.empty and sts_resumo_exec_df.iloc[0]['litros_por_kg_resumo'] is not None else 0
        
        # Extrair valores brutos - PERÍODO (intervalo selecionado) da tabela Sts_Dados
        quilos_periodo = float(sts_periodo_df.iloc[0]['quilos_lavados_periodo']) if not sts_periodo_df.empty and sts_periodo_df.iloc[0]['quilos_lavados_periodo'] is not None else 0
        litros_periodo = float(sts_periodo_df.iloc[0]['litros_agua_periodo']) if not sts_periodo_df.empty and sts_periodo_df.iloc[0]['litros_agua_periodo'] is not None else 0
        ml_quimicos_periodo = float(chemical_periodo_df.iloc[0]['ml_quimicos_periodo']) if not chemical_periodo_df.empty and chemical_periodo_df.iloc[0]['ml_quimicos_periodo'] is not None else 0
        peso_medio_periodo = float(sts_periodo_df.iloc[0]['peso_medio_periodo']) if not sts_periodo_df.empty and sts_periodo_df.iloc[0]['peso_medio_periodo'] is not None else 0
        batchs_periodo = int(sts_periodo_df.iloc[0]['batchs_periodo']) if not sts_periodo_df.empty and sts_periodo_df.iloc[0]['batchs_periodo'] is not None else 0
        litros_por_kg_periodo = float(sts_periodo_df.iloc[0]['litros_por_kg_periodo']) if not sts_periodo_df.empty and sts_periodo_df.iloc[0]['litros_por_kg_periodo'] is not None else 0
        
        # Montar KPIs com dados separados para HOJE e PERÍODO
        kpis = {
            # === DADOS DO DIA ATUAL (HOJE) ===
            'quilos_lavados_hoje': f"{round(quilos_hoje, 0):,.0f}".replace(',', '.'),
            'quilos_lavados_hoje_raw': round(quilos_hoje, 0),
            'ciclos_hoje': batchs_hoje,  # Usar dados da tabela Sts_Dados
            'litros_agua_hoje': f"{round(litros_hoje, 0):,.0f}" if litros_hoje < 1000000 else format_number_abbreviated(litros_hoje),
            'litros_agua_hoje_raw': round(litros_hoje, 0),
            'litros_por_kg_hoje': litros_por_kg_hoje,  # Usar valor já calculado
            'peso_medio_hoje': peso_medio_hoje,
            'ml_quimicos_hoje': round(ml_quimicos_hoje, 0),
            'ml_quimicos_por_kg_hoje': round(float(chemical_hoje_df.iloc[0]['ml_quimicos_por_kg_hoje']) if not chemical_hoje_df.empty and chemical_hoje_df.iloc[0]['ml_quimicos_por_kg_hoje'] is not None else 0, 3),
            
            # === DADOS PARA O RESUMO EXECUTIVO (dia atual ou mais recente) ===
            'quilos_lavados_resumo': f"{round(quilos_resumo, 0):,.0f}".replace(',', '.'),
            'quilos_lavados_resumo_raw': round(quilos_resumo, 0),
            'ciclos_resumo': batchs_resumo,
            'litros_agua_resumo': f"{round(litros_resumo, 0):,.0f}" if litros_resumo < 1000000 else format_number_abbreviated(litros_resumo),
            'litros_agua_resumo_raw': round(litros_resumo, 0),
            'litros_por_kg_resumo': litros_por_kg_resumo,
            'peso_medio_resumo': peso_medio_resumo,
            
            # === DADOS DO PERÍODO SELECIONADO ===
            'quilos_lavados_periodo': f"{round(quilos_periodo, 0):,.0f}".replace(',', '.'),
            'quilos_lavados_periodo_raw': round(quilos_periodo, 0),
            'ciclos_periodo': batchs_periodo,
            'litros_agua_periodo': f"{round(litros_periodo, 0):,.0f}" if litros_periodo < 1000000 else format_number_abbreviated(litros_periodo),
            'litros_agua_periodo_raw': round(litros_periodo, 0),
            'litros_por_kg_periodo': litros_por_kg_periodo,  # Usar valor já calculado
            'peso_medio_periodo': peso_medio_periodo,
            'ml_quimicos_periodo': round(ml_quimicos_periodo, 0),
            'ml_quimicos_por_kg_periodo': round(float(chemical_periodo_df.iloc[0]['ml_quimicos_por_kg_periodo']) if not chemical_periodo_df.empty and chemical_periodo_df.iloc[0]['ml_quimicos_por_kg_periodo'] is not None else 0, 3),
            
            # === OUTROS INDICADORES ===
            'eficiencia_media': round(float(efficiency_df.iloc[0]['eficiencia_media']) if not efficiency_df.empty and efficiency_df.iloc[0]['eficiencia_media'] is not None else 0, 1),
            'alarmes_ativos': int(alarms_df.iloc[0]['alarmes_ativos']) if not alarms_df.empty and alarms_df.iloc[0]['alarmes_ativos'] is not None else 0,
            
            # === METADADOS ===
            'periodo_label': periodo_label,
            'hoje_date': str(today),
            'hoje_label': hoje_label
        }
        
        print(f"KPIs calculados: {kpis}")
        return kpis
        
    except Exception as e:
        print(f"Erro ao calcular KPIs: {e}")
        # Retornar valores padrão em caso de erro
        return {
            # Dados do dia atual (hoje)
            'quilos_lavados_hoje': 0,
            'ciclos_hoje': 0,
            'litros_agua_hoje': 0,
            'litros_por_kg_hoje': 0,
            'ml_quimicos_hoje': 0,
            'ml_quimicos_por_kg_hoje': 0,
            
            # Dados do período selecionado
            'quilos_lavados_periodo': 0,
            'ciclos_periodo': 0,
            'litros_agua_periodo': 0,
            'litros_por_kg_periodo': 0,
            'ml_quimicos_periodo': 0,
            'ml_quimicos_por_kg_periodo': 0,
            
            # Outros
            'eficiencia_media': 0,
            'alarmes_ativos': 0,
            'periodo_label': 'Sem dados',
            'hoje_date': str(date.today())
        }

def create_active_alarms_table():
    """Tabela de alarmes ativos"""
    
    query = """
    SELECT 
        "Al_Tag" as tag,
        "Al_Message" as message,
        "Al_Selection" as area,
        "Al_Priority" as priority,
        "Al_Start_Time" as start_time,
        EXTRACT(EPOCH FROM (NOW() - "Al_Start_Time"))/60 as duration_minutes
    FROM "ALARMHISTORY"
    WHERE "Al_Norm_Time" IS NULL
      AND "Al_Start_Time" >= CURRENT_DATE - INTERVAL '7 days'
    ORDER BY "Al_Priority", "Al_Start_Time" DESC
    LIMIT 20
    """
    
    df = execute_query(query)
    
    if df.empty:
        return html.Div([
            html.H5("Alarmes Ativos", className="text-center mb-3"),
            html.P("Nenhum alarme ativo no momento", className="text-center text-muted")
        ])
    
    # Mapear prioridades
    priority_map = {1: 'Crítico', 2: 'Alto', 3: 'Médio', 4: 'Baixo', 5: 'Info'}
    df['priority_label'] = df['priority'].map(priority_map)
    
    # Formatar duração
    df['duration_formatted'] = df['duration_minutes'].apply(
        lambda x: f"{int(x//60)}h {int(x%60)}m" if x >= 60 else f"{int(x)}m"
    )
    
    # Truncar mensagens
    df['message_short'] = df['message'].str[:50] + '...'
    
    table_data = []
    for _, row in df.iterrows():
        table_data.append({
            'Tag': row['tag'],
            'Mensagem': row['message_short'],
            'Área': row['area'],
            'Prioridade': row['priority_label'],
            'Início': row['start_time'].strftime('%d/%m %H:%M'),
            'Duração': row['duration_formatted']
        })
    
    return html.Div([
        html.H5(f"Alarmes Ativos ({len(df)})", className="text-center mb-3"),
        dash_table.DataTable(
            data=table_data,
            columns=[
                {'name': 'Tag', 'id': 'Tag'},
                {'name': 'Mensagem', 'id': 'Mensagem'},
                {'name': 'Área', 'id': 'Área'},
                {'name': 'Prioridade', 'id': 'Prioridade'},
                {'name': 'Início', 'id': 'Início'},
                {'name': 'Duração', 'id': 'Duração'}
            ],
            style_cell={
                'textAlign': 'left',
                'fontSize': '12px',
                'fontFamily': 'Arial'
            },
            style_data_conditional=[
                {
                    'if': {'filter_query': '{Prioridade} = Crítico'},
                    'backgroundColor': '#ffebee',
                    'color': 'black',
                },
                {
                    'if': {'filter_query': '{Prioridade} = Alto'},
                    'backgroundColor': '#fff3e0',
                    'color': 'black',
                }
            ],
            style_header={
                'backgroundColor': '#f8f9fa',
                'fontWeight': 'bold'
            },
            page_size=10
        )
    ])

# ===== FUNÇÃO DE RESUMO FINAL =====

def get_dashboard_summary():
    """Resumo geral do dashboard com principais indicadores"""
    
    try:
        # Resumo de produção
        production_summary = """
        SELECT 
            COUNT(*) as total_cycles,
            SUM("C4") as total_production_kg,
            AVG("C4") as avg_production_per_cycle,
            AVG(("C1" / ("C1" + "C0")) * 100) as avg_efficiency
        FROM "Rel_Diario"
        WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '30 days'
        """
        
        # Resumo de alarmes
        alarms_summary = """
        SELECT 
            COUNT(*) as total_alarms,
            COUNT(CASE WHEN "Al_Priority" <= 2 THEN 1 END) as critical_high_alarms,
            AVG(EXTRACT(EPOCH FROM ("Al_Norm_Time" - "Al_Start_Time"))/60) as avg_resolution_time
        FROM "ALARMHISTORY"
        WHERE "Al_Start_Time" >= CURRENT_DATE - INTERVAL '30 days'
          AND "Al_Norm_Time" IS NOT NULL
        """
        
        # Resumo de consumos
        consumption_summary = """
        SELECT 
            AVG(("C2" * 1000) / "C4") as avg_water_per_kg,
            SUM("C2") as total_water_m3
        FROM "Rel_Diario"
        WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '30 days'
          AND "C4" > 0
        """
        
        prod_df = execute_query(production_summary)
        alarms_df = execute_query(alarms_summary)
        consumption_df = execute_query(consumption_summary)
        
        # Extrair valores brutos
        total_kg = prod_df.iloc[0]['total_production_kg'] if not prod_df.empty else 0
        total_alarms = alarms_df.iloc[0]['total_alarms'] if not alarms_df.empty else 0
        total_water = consumption_df.iloc[0]['total_water_m3'] if not consumption_df.empty else 0
        
        summary = {
            'production': {
                'total_cycles': int(prod_df.iloc[0]['total_cycles']) if not prod_df.empty else 0,
                'total_kg': format_number_abbreviated(total_kg),
                'total_kg_raw': round(total_kg, 0),
                'avg_per_cycle': round(prod_df.iloc[0]['avg_production_per_cycle'], 1) if not prod_df.empty else 0,
                'avg_efficiency': round(prod_df.iloc[0]['avg_efficiency'], 1) if not prod_df.empty else 0
            },
            'alarms': {
                'total': format_number_abbreviated(total_alarms),
                'total_raw': int(total_alarms),
                'critical_high': int(alarms_df.iloc[0]['critical_high_alarms']) if not alarms_df.empty else 0,
                'avg_resolution_min': round(alarms_df.iloc[0]['avg_resolution_time'], 1) if not alarms_df.empty else 0
            },
            'consumption': {
                'avg_water_per_kg': round(consumption_df.iloc[0]['avg_water_per_kg'], 1) if not consumption_df.empty else 0,
                'total_water_m3': format_number_abbreviated(total_water),
                'total_water_m3_raw': round(total_water, 1)
            }
        }
        
        return summary
        
    except Exception as e:
        print(f"Erro ao gerar resumo: {e}")
        return {
            'production': {'total_cycles': 0, 'total_kg': 0, 'avg_per_cycle': 0, 'avg_efficiency': 0},
            'alarms': {'total': 0, 'critical_high': 0, 'avg_resolution_min': 0},
            'consumption': {'avg_water_per_kg': 0, 'total_water_m3': 0}
        }

def generate_executive_report():
    """Gerar relatório executivo com dados formatados"""
    
    try:
        # Obter dados dos KPIs
        kpis = get_operational_kpis()
        summary = get_dashboard_summary()
        
        # Data atual
        current_date = datetime.now().strftime('%d/%m/%Y %H:%M')
        
        # Montar relatório
        report = {
            'timestamp': current_date,
            'production_summary': {
                'daily_production': kpis['quilos_lavados_resumo'],  # Usar dados do Resumo Executivo
                'daily_cycles': kpis['ciclos_resumo'],  # Usar dados do Resumo Executivo
                'weekly_production': kpis['quilos_lavados_semana'],
                'weekly_cycles': kpis['ciclos_semana'],
                'efficiency': f"{kpis['eficiencia_media']}%"
            },
            'consumption_summary': {
                'water_today': kpis['litros_agua_resumo'],  # Usar dados do Resumo Executivo
                'water_per_kg': f"{kpis['litros_por_kg_resumo']:.2f} L/kg",  # Usar dados do Resumo Executivo
                'chemicals_today': f"{kpis['ml_quimicos_hoje']:.0f} ml",
                'chemicals_per_kg': f"{kpis['ml_quimicos_por_kg_hoje']:.3f} ml/kg"
            },
            'alarms_summary': {
                'active_alarms': kpis['alarmes_ativos'],
                'total_month': summary['alarms']['total'],
                'critical_high': summary['alarms']['critical_high'],
                'avg_resolution': f"{summary['alarms']['avg_resolution_min']:.1f} min"
            },
            'recommendations': [
                "Manter consumo de água entre 12-18 L/kg para otimização",
                "Monitorar alarmes críticos para reduzir tempo de resolução",
                "Eficiência operacional acima de 85% indica boa performance",
                "Revisar consumo de químicos para possível otimização"
            ]
        }
        
        return report
        
    except Exception as e:
        print(f"Erro ao gerar relatório: {e}")
        return {
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M'),
            'error': 'Erro ao gerar relatório executivo'
        }

# ===== LISTA DE FUNÇÕES DISPONÍVEIS =====
"""
Funções principais do módulo dstech_charts.py:

1. create_efficiency_chart() - Eficiência operacional
2. create_water_consumption_chart() - Consumo de água por kg
3. create_chemical_consumption_chart() - Consumo de químicos por kg
4. create_top_alarms_chart() - Top 10 alarmes mais frequentes
5. create_alarm_analysis_chart() - Análise de alarmes por área
6. create_production_by_client_chart() - Produção por cliente
7. create_production_by_program_chart() - Produção por programa
8. get_operational_kpis() - KPIs operacionais principais
9. create_active_alarms_table() - Tabela de alarmes ativos
10. get_dashboard_summary() - Resumo geral do dashboard

Todas as funções utilizam dados reais do PostgreSQL com cálculos
baseados no README e arquivo de reunião.
"""

def create_temperature_trend_chart(start_date=None, end_date=None):
    """Gráfico de tendência de sensores e variáveis do processo"""
    
    # Construir filtro de data
    date_filter = "WHERE 1=1"
    if start_date and end_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}' AND \"Time_Stamp\" <= '{end_date}'"
    elif start_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE \"Time_Stamp\" <= '{end_date}'"
    
    # Se não há filtros específicos, pegar os dados mais recentes disponíveis
    if date_filter == "WHERE 1=1":
        query = f"""
        SELECT 
            "Time_Stamp" as timestamp,
            "Real_R_0" as sensor_principal,
            "Real_R_10" as sensor_secundario,
            "C8_Real_0" as variavel_processo_1,
            "C3_Real_0" as variavel_processo_2,
            "C4_Real_0" as variavel_processo_3
        FROM "TREND001"
        ORDER BY "Time_Stamp" DESC
        LIMIT 1000
        """
    else:
        query = f"""
        SELECT 
            "Time_Stamp" as timestamp,
            "Real_R_0" as sensor_principal,
            "Real_R_10" as sensor_secundario,
            "C8_Real_0" as variavel_processo_1,
            "C3_Real_0" as variavel_processo_2,
            "C4_Real_0" as variavel_processo_3
        FROM "TREND001"
        {date_filter}
        ORDER BY "Time_Stamp" ASC
        LIMIT 1000
        """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de tendência disponíveis", 
                                        xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    
    # Converter para numérico
    numeric_cols = ['sensor_principal', 'sensor_secundario', 'variavel_processo_1', 'variavel_processo_2', 'variavel_processo_3']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    fig = go.Figure()
    
    # Sensores e variáveis do processo
    variables = [
        ('sensor_principal', 'Sensor Principal', '#e74c3c'),
        ('sensor_secundario', 'Sensor Secundário', '#3498db'),
        ('variavel_processo_1', 'Variável C8', '#2ecc71'),
        ('variavel_processo_2', 'Variável C3', '#f39c12'),
        ('variavel_processo_3', 'Variável C4', '#9b59b6')
    ]
    
    for col, name, color in variables:
        if col in df.columns and not df[col].isna().all():
            # Filtrar valores válidos
            valid_data = df[df[col].notna()]
            if not valid_data.empty:
                fig.add_trace(go.Scatter(
                    x=valid_data['timestamp'],
                    y=valid_data[col],
                    mode='lines+markers',
                    name=name,
                    line=dict(color=color, width=2),
                    marker=dict(size=4),
                    hovertemplate=f'<b>{name}</b><br>%{{x}}<br>Valor: %{{y:.2f}}<extra></extra>'
                ))
    
    # Adicionar estatísticas se houver dados
    if not df.empty and len(fig.data) > 0:
        # Calcular médias para cada variável
        stats_text = "Médias: "
        for col, name, _ in variables:
            if col in df.columns and not df[col].isna().all():
                avg_val = df[col].mean()
                if not pd.isna(avg_val):
                    stats_text += f"{name}: {avg_val:.1f} | "
        
        fig.update_layout(
            title=f"Análise de Tendências do Processo<br><sub>{stats_text.rstrip(' | ')}</sub>",
            xaxis_title="Data/Hora",
            yaxis_title="Valores dos Sensores/Variáveis",
            hovermode='x unified',
            template='plotly_white',
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
    else:
        fig.update_layout(
            title="Análise de Tendências do Processo",
            xaxis_title="Data/Hora",
            yaxis_title="Valores dos Sensores/Variáveis",
            template='plotly_white'
        )
    
    return fig

def create_sensors_trend_chart(start_date=None, end_date=None):
    """Gráfico de análise completa de sensores usando dados reais da TREND001"""
    
    # Construir filtro de data
    date_filter = "WHERE 1=1"
    if start_date and end_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}' AND \"Time_Stamp\" <= '{end_date}'"
    elif start_date:
        date_filter = f"WHERE \"Time_Stamp\" >= '{start_date}'"
    elif end_date:
        date_filter = f"WHERE \"Time_Stamp\" <= '{end_date}'"
    
    query = f"""
    SELECT 
        "Time_Stamp" as timestamp,
        "Real_R_0" as sensor_principal,
        "Real_R_10" as sensor_secundario,
        "C8_Real_0" as variavel_c8,
        "C3_Real_0" as variavel_c3,
        "C4_Real_0" as variavel_c4 
    FROM "TREND001"
    {date_filter}
    ORDER BY "Time_Stamp" DESC
    LIMIT 1000
    """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(
            text="📊 Sem dados de sensores disponíveis<br>Verifique a conexão com o sistema de aquisição", 
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="#7f8c8d")
        )
    
    # Converter timestamp para datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')
    
    fig = go.Figure()
    
    # Adicionar cada sensor como uma linha
    sensors = [
        ('sensor_principal', 'Sensor Principal', '#3498db'),
        ('sensor_secundario', 'Sensor Secundário', '#e74c3c'),
        ('variavel_c8', 'Variável C8', '#2ecc71'),
        ('variavel_c3', 'Variável C3', '#f39c12'),
        ('variavel_c4', 'Variável C4', '#9b59b6')
    ]
    
    for col, name, color in sensors:
        if col in df.columns and not df[col].isna().all():
            fig.add_trace(go.Scatter(
                x=df['timestamp'],
                y=df[col],
                mode='lines',
                name=name,
                line=dict(color=color, width=2),
                hovertemplate=f'<b>{name}</b><br>Valor: %{{y:.2f}}<br>Tempo: %{{x}}<extra></extra>'
            ))
    
    # Calcular estatísticas dos sensores
    stats_text = []
    for col, name, _ in sensors:
        if col in df.columns and not df[col].isna().all():
            mean_val = df[col].mean()
            stats_text.append(f"{name}: {mean_val:.1f}")
    
    stats_subtitle = " | ".join(stats_text) if stats_text else "Sem dados válidos"
    
    fig.update_layout(
        title=f"📊 Análise Completa de Sensores<br><sub>Médias: {stats_subtitle}</sub>",
        xaxis_title="Tempo",
        yaxis_title="Valores dos Sensores",
        template='plotly_white',
        showlegend=True,
        legend=dict(x=0, y=1, bgcolor='rgba(255,255,255,0.8)'),
        hovermode='x unified'
    )
    
    return fig

def create_client_analysis_chart(client_filter=None):
    """Gráfico de análise por cliente baseado nos dados de produção"""
    
    # Se há filtro de cliente específico, usar dados reais da tabela Rel_Carga
    if client_filter:
        query = f"""
        SELECT 
            COALESCE(c.client_name, 'Cliente ' || CAST(rc."C1" AS TEXT)) as cliente,
            COUNT(*) as total_ciclos,
            SUM(rc."C2") as total_kg,
            AVG(rc."C2") as media_kg_ciclo,
            0 as total_agua_litros,
            0 as total_quimicos_kg
        FROM "Rel_Carga" rc
        LEFT JOIN clientes c ON CAST(rc."C1" AS INTEGER) = c.client_id
        WHERE rc."Time_Stamp" >= CURRENT_DATE - INTERVAL '30 days'
          AND rc."C1" = '{client_filter}'
          AND rc."C2" > 0
        GROUP BY c.client_name, rc."C1"
        ORDER BY total_kg DESC
        """
    else:
        query = """
        SELECT 
            CASE 
                WHEN "C4" BETWEEN 0 AND 50 THEN 'Cliente A (Pequeno)'
                WHEN "C4" BETWEEN 51 AND 150 THEN 'Cliente B (Médio)'
                WHEN "C4" BETWEEN 151 AND 300 THEN 'Cliente C (Grande)'
                ELSE 'Cliente D (Industrial)'
            END as cliente,
            COUNT(*) as total_ciclos,
            SUM("C4") as total_kg,
            AVG("C4") as media_kg_ciclo,
            SUM("C2" * 1000) as total_agua_litros,
            SUM("C3") as total_quimicos_kg
        FROM "Rel_Diario"
        WHERE "Time_Stamp" >= CURRENT_DATE - INTERVAL '30 days'
          AND "C4" > 0
        GROUP BY 
            CASE 
                WHEN "C4" BETWEEN 0 AND 50 THEN 'Cliente A (Pequeno)'
                WHEN "C4" BETWEEN 51 AND 150 THEN 'Cliente B (Médio)'
                WHEN "C4" BETWEEN 151 AND 300 THEN 'Cliente C (Grande)'
                ELSE 'Cliente D (Industrial)'
            END
        ORDER BY total_kg DESC
        """
    
    df = execute_query(query)
    
    if df.empty:
        return go.Figure().add_annotation(text="Sem dados de clientes disponíveis", 
                                        xref="paper", yref="paper",
                                        x=0.5, y=0.5, showarrow=False)
    
    # Criar subplots
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=('Produção por Cliente (kg)', 'Ciclos por Cliente', 
                       'Consumo de Água (L)', 'Consumo de Químicos (kg)'),
        specs=[[{"type": "bar"}, {"type": "pie"}],
               [{"type": "bar"}, {"type": "bar"}]]
    )
    
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12']
    
    # Gráfico 1: Produção por cliente
    fig.add_trace(
        go.Bar(x=df['cliente'], y=df['total_kg'], 
               marker_color=colors, name='Produção (kg)'),
        row=1, col=1
    )
    
    # Gráfico 2: Distribuição de ciclos (pizza)
    fig.add_trace(
        go.Pie(labels=df['cliente'], values=df['total_ciclos'],
               marker_colors=colors, name='Ciclos'),
        row=1, col=2
    )
    
    # Gráfico 3: Consumo de água
    fig.add_trace(
        go.Bar(x=df['cliente'], y=df['total_agua_litros'],
               marker_color='#17a2b8', name='Água (L)'),
        row=2, col=1
    )
    
    # Gráfico 4: Consumo de químicos
    fig.add_trace(
        go.Bar(x=df['cliente'], y=df['total_quimicos_kg'],
               marker_color='#6f42c1', name='Químicos (kg)'),
        row=2, col=2
    )
    
    fig.update_layout(
        title="Análise de Clientes - Últimos 30 Dias",
        height=600,
        showlegend=False,
        template='plotly_white'
    )
    
    return fig
