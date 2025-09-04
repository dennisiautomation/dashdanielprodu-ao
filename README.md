# DSTech Dashboard - Sistema de Monitoramento Industrial

## 📋 Visão Geral

O DSTech Dashboard é um sistema completo de monitoramento industrial desenvolvido em Python com Dash/Plotly, projetado para análise em tempo real de dados de produção, alarmes, consumo de recursos e KPIs operacionais.

## 🏗️ Arquitetura do Sistema

### Arquivos Principais

- **`dstech_app.py`** - Aplicação principal com interface web, callbacks e lógica de negócio
- **`dstech_charts.py`** - Módulo de gráficos e visualizações com Plotly
- **`.env_dstech`** - Configurações de ambiente e conexão com PostgreSQL

### Estrutura de Dados

O sistema conecta-se a um banco PostgreSQL com as seguintes tabelas principais:

#### Tabelas de Produção
- **`Rel_Diario`** - Dados consolidados diários de produção
- **`Rel_Carga`** - Registros de cargas individuais
- **`Rel_Quimico`** - Consumo de químicos por período
- **`Sts_Dados`** - Status e dados operacionais em tempo real

#### Tabelas de Alarmes
- **`ALARMHISTORY`** - Histórico completo de alarmes do sistema

#### Tabelas Auxiliares
- **`app.client_alias`** - Aliases para clientes
- **`programas`** - Programas de produção

## 🧮 Cálculos e KPIs

### Eficiência Operacional
```python
eficiencia = (tempo_producao / (tempo_producao + tempo_parado)) * 100
```

### Consumo de Água por Kg
```python
agua_por_kg = (consumo_agua_m3 * 1000) / peso_producao_kg
```

### Consumo de Químicos por Kg
```python
quimico_por_kg = consumo_quimico_ml / peso_producao_kg
```

### Contagem de Alarmes
O sistema utiliza lógica específica para evitar duplicação:
- **Alarmes do Dia**: `COUNT(*)` com `Al_Start_Time > CURRENT_DATE` e `Al_Norm_Time > CURRENT_DATE`
- **Alarmes do Período**: `COUNT(*)` com bounds inferiores em ambos os campos
- **Top 10 Alarmes**: Mesma lógica com agrupamento por tag e mensagem

## 📊 Funcionalidades

### Dashboard Principal
- **KPIs em Tempo Real**: Produção, consumo de água, químicos, alarmes ativos
- **Top 5 Alarmes**: Do dia atual e do período selecionado
- **Seletor de Período**: Interface responsiva para análise temporal

### Aba de Gráficos
- **Eficiência Operacional**: Timeline com meta de 85%
- **Consumo Hídrico**: Barras com zonas de alerta (12-18 L/kg ideal)
- **Consumo de Químicos**: 9 químicos diferentes por kg produzido
- **Top 10 Alarmes**: Ranking de frequência por período
- **Análise por Severidade**: Distribuição de alarmes por prioridade
- **Timeline de Alarmes**: Comparação período atual vs anterior

### Relatórios
- **Export Excel**: Múltiplas abas com dados detalhados
- **Export PDF**: Relatório executivo formatado
- **Nomenclatura**: Arquivos com data no formato `relatorio_dstech_YYYYMMDD_YYYYMMDD`

## 🔧 Configuração

### Variáveis de Ambiente (.env_dstech)
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres123
POSTGRES_DB=dstech_dashboard
DASH_PORT=8051
```

### Dependências Python
```
dash
dash-bootstrap-components
plotly
pandas
psycopg2-binary
sqlalchemy
python-dotenv
reportlab
xlsxwriter
```

## 🚀 Execução

```bash
python dstech_app.py
```

Acesso: http://localhost:8051
Login: admin / admin123

## 📱 Responsividade

O sistema foi otimizado para diferentes dispositivos:

### Breakpoints Bootstrap
- **xs (< 576px)**: Mobile - Cards em coluna única
- **sm (≥ 576px)**: Mobile grande - Layout adaptado
- **md (≥ 768px)**: Tablet - Cards em 2 colunas
- **lg (≥ 992px)**: Desktop - Layout completo
- **xl (≥ 1200px)**: Desktop grande - Máximo aproveitamento

### Ajustes Específicos
- Logo centralizado em mobile
- Date pickers com z-index adequado
- Cards com altura uniforme (`h-100`)
- Texto responsivo com `clamp()`

## 🔍 Lógica de Alarmes

### Problema Original
Contagem duplicada devido a registros de "start" e "acknowledgment" separados.

### Solução Implementada
1. **Filtros Temporais**: Usar ambos `Al_Start_Time` e `Al_Norm_Time`
2. **Contagem**: `COUNT(*)` em vez de `COUNT(DISTINCT Al_ID)`
3. **Bounds**: Apenas limite inferior para consistência com origem

### Queries Principais

#### Top 5 Alarmes do Dia
```sql
SELECT Al_Tag, Al_Message, COUNT(*), MAX(Al_Start_Time)
FROM ALARMHISTORY 
WHERE Al_Start_Time > CURRENT_DATE AND Al_Norm_Time > CURRENT_DATE
GROUP BY Al_Tag, Al_Message
ORDER BY COUNT(*) DESC LIMIT 5
```

#### Top 5 Alarmes do Período
```sql
SELECT Al_Tag, Al_Message, COUNT(*), MAX(Al_Start_Time)
FROM ALARMHISTORY 
WHERE Al_Start_Time >= %s AND Al_Norm_Time >= %s
GROUP BY Al_Tag, Al_Message
ORDER BY COUNT(*) DESC LIMIT 5
```

## 🎨 Interface

### Tema e Cores
- **Bootstrap Theme**: Tema padrão com customizações
- **Gradientes**: Cards com gradientes modernos
- **Ícones**: Font Awesome e emojis para melhor UX
- **Sombras**: Box-shadow para profundidade

### Componentes Principais
- **Cards KPI**: Métricas com ícones e cores temáticas
- **Date Pickers**: Seletores de período responsivos
- **Gráficos Plotly**: Interativos com hover personalizado
- **Tabelas**: Formatação Bootstrap com dados paginados

## 🔄 Atualizações Recentes

### Correções de Alarmes
- Alinhamento com SQL de origem
- Remoção de números de frequência da interface
- Bounds inferiores para consistência

### Melhorias de Layout
- Centralização do logo em mobile
- Altura uniforme dos cards
- Otimização de breakpoints

### Performance
- Queries otimizadas
- Caching de dados
- Redução de duplicações

## 📈 Métricas de Negócio

### Metas Operacionais
- **Eficiência**: > 85%
- **Consumo Hídrico**: 12-18 L/kg (ideal)
- **Alarmes Críticos**: Minimizar ocorrências
- **Produção Diária**: 2.000 kg (meta)

### Indicadores Chave
- Peso médio por ciclo
- Litros de água por kg produzido
- Consumo de químicos por kg
- Tempo médio de resolução de alarmes

## 🛠️ Manutenção

### Logs
Sistema registra atividades em console com timestamps e códigos de status.

### Backup
Estrutura preparada para backup automático de dados e configurações.

### Monitoramento
Interface mostra status do sistema e última atualização em tempo real.

---

**Desenvolvido para monitoramento industrial avançado com foco em eficiência operacional e análise de dados em tempo real.**
