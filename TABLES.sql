-- Estrutura das Tabelas - DSTech Dashboard
-- PostgreSQL Database Schema

-- Tabela principal de dados diários consolidados
CREATE TABLE IF NOT EXISTS "Rel_Diario" (
    "Time_Stamp" TIMESTAMP NOT NULL,
    "C0" NUMERIC DEFAULT 0,  -- Tempo parado (minutos)
    "C1" NUMERIC DEFAULT 0,  -- Tempo de produção (minutos)
    "C2" NUMERIC DEFAULT 0,  -- Consumo de água (m³)
    "C3" NUMERIC DEFAULT 0,  -- Campo reservado
    "C4" NUMERIC DEFAULT 0,  -- Produção total (kg)
    "C5" INTEGER DEFAULT 0,  -- Cliente ID
    PRIMARY KEY ("Time_Stamp")
);

-- Tabela de cargas individuais
CREATE TABLE IF NOT EXISTS "Rel_Carga" (
    "Time_Stamp" TIMESTAMP NOT NULL,
    "C0" INTEGER DEFAULT 0,  -- Programa ID
    "C1" INTEGER DEFAULT 0,  -- Cliente ID
    "C2" NUMERIC DEFAULT 0,  -- Peso da carga (kg)
    "C3" NUMERIC DEFAULT 0,  -- Campo adicional
    PRIMARY KEY ("Time_Stamp")
);

-- Tabela de consumo de químicos
CREATE TABLE IF NOT EXISTS "Rel_Quimico" (
    "Time_Stamp" TIMESTAMP NOT NULL,
    "Q1" NUMERIC DEFAULT 0,  -- Químico 1 (ml)
    "Q2" NUMERIC DEFAULT 0,  -- Químico 2 (ml)
    "Q3" NUMERIC DEFAULT 0,  -- Químico 3 (ml)
    "Q4" NUMERIC DEFAULT 0,  -- Químico 4 (ml)
    "Q5" NUMERIC DEFAULT 0,  -- Químico 5 (ml)
    "Q6" NUMERIC DEFAULT 0,  -- Químico 6 (ml)
    "Q7" NUMERIC DEFAULT 0,  -- Químico 7 (ml)
    "Q8" NUMERIC DEFAULT 0,  -- Químico 8 (ml)
    "Q9" NUMERIC DEFAULT 0,  -- Químico 9 (ml)
    PRIMARY KEY ("Time_Stamp")
);

-- Tabela de status e dados operacionais
CREATE TABLE IF NOT EXISTS "Sts_Dados" (
    "Time_Stamp" TIMESTAMP NOT NULL,
    "D1" NUMERIC DEFAULT 0,  -- Consumo de água acumulado (m³)
    "D2" NUMERIC DEFAULT 0,  -- Número de batches/ciclos
    "D3" NUMERIC DEFAULT 0,  -- Produção acumulada (kg)
    "D4" NUMERIC DEFAULT 0,  -- Campo reservado
    "D5" INTEGER DEFAULT 0,  -- Cliente atual
    PRIMARY KEY ("Time_Stamp")
);

-- Tabela de histórico de alarmes
CREATE TABLE IF NOT EXISTS "ALARMHISTORY" (
    "Al_ID" SERIAL PRIMARY KEY,
    "Al_Tag" VARCHAR(100) NOT NULL,
    "Al_Message" TEXT,
    "Al_Start_Time" TIMESTAMP,
    "Al_Norm_Time" TIMESTAMP,
    "Al_Priority" INTEGER DEFAULT 5,  -- 1=Crítico, 2=Alto, 3=Médio, 4=Baixo, 5=Info
    "Al_Selection" VARCHAR(50),       -- Área/Seção do alarme
    "Al_Value" NUMERIC,
    "Al_Limit" NUMERIC
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_alarmhistory_start_time ON "ALARMHISTORY" ("Al_Start_Time");
CREATE INDEX IF NOT EXISTS idx_alarmhistory_norm_time ON "ALARMHISTORY" ("Al_Norm_Time");
CREATE INDEX IF NOT EXISTS idx_alarmhistory_tag ON "ALARMHISTORY" ("Al_Tag");
CREATE INDEX IF NOT EXISTS idx_alarmhistory_priority ON "ALARMHISTORY" ("Al_Priority");

CREATE INDEX IF NOT EXISTS idx_rel_diario_timestamp ON "Rel_Diario" ("Time_Stamp");
CREATE INDEX IF NOT EXISTS idx_rel_carga_timestamp ON "Rel_Carga" ("Time_Stamp");
CREATE INDEX IF NOT EXISTS idx_rel_carga_client ON "Rel_Carga" ("C1");
CREATE INDEX IF NOT EXISTS idx_sts_dados_timestamp ON "Sts_Dados" ("Time_Stamp");

-- Schema para tabelas auxiliares
CREATE SCHEMA IF NOT EXISTS app;

-- Tabela de aliases para clientes
CREATE TABLE IF NOT EXISTS app.client_alias (
    client_id INTEGER PRIMARY KEY,
    alias VARCHAR(100) NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de programas de produção
CREATE TABLE IF NOT EXISTS programas (
    program_id INTEGER PRIMARY KEY,
    program_name VARCHAR(100) NOT NULL,
    description TEXT,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Inserir dados de exemplo para aliases de clientes
INSERT INTO app.client_alias (client_id, alias, description) VALUES
(1, 'Cliente Alpha', 'Cliente principal - Setor automotivo'),
(2, 'Cliente Beta', 'Cliente secundário - Setor alimentício'),
(3, 'Cliente Gamma', 'Cliente terciário - Setor farmacêutico'),
(4, 'Cliente Delta', 'Cliente quaternário - Setor químico'),
(5, 'Cliente Epsilon', 'Cliente quinário - Setor têxtil')
ON CONFLICT (client_id) DO NOTHING;

-- Inserir dados de exemplo para programas
INSERT INTO programas (program_id, program_name, description) VALUES
(1, 'Programa Padrão', 'Programa de lavagem padrão'),
(2, 'Programa Intensivo', 'Programa de lavagem intensiva'),
(3, 'Programa Eco', 'Programa econômico de lavagem'),
(4, 'Programa Delicado', 'Programa para materiais delicados'),
(5, 'Programa Express', 'Programa rápido de lavagem')
ON CONFLICT (program_id) DO NOTHING;

-- Views úteis para relatórios
CREATE OR REPLACE VIEW vw_production_summary AS
SELECT 
    DATE("Time_Stamp") as production_date,
    SUM("C4") as total_production_kg,
    SUM("C1") as total_production_time_min,
    SUM("C0") as total_downtime_min,
    SUM("C2") * 1000 as total_water_consumption_l,
    COUNT(*) as records_count,
    CASE 
        WHEN SUM("C1" + "C0") > 0 THEN 
            ROUND((SUM("C1") / SUM("C1" + "C0")) * 100, 2)
        ELSE 0 
    END as efficiency_percent
FROM "Rel_Diario"
WHERE "C4" > 0
GROUP BY DATE("Time_Stamp")
ORDER BY production_date DESC;

CREATE OR REPLACE VIEW vw_alarm_summary AS
SELECT 
    DATE("Al_Start_Time") as alarm_date,
    "Al_Priority",
    COUNT(*) as alarm_count,
    COUNT(DISTINCT "Al_Tag") as unique_alarms,
    AVG(EXTRACT(EPOCH FROM ("Al_Norm_Time" - "Al_Start_Time"))/60) as avg_duration_minutes
FROM "ALARMHISTORY"
WHERE "Al_Start_Time" IS NOT NULL 
  AND "Al_Norm_Time" IS NOT NULL
  AND "Al_Norm_Time" > "Al_Start_Time"
GROUP BY DATE("Al_Start_Time"), "Al_Priority"
ORDER BY alarm_date DESC, "Al_Priority";

-- Comentários sobre as tabelas
COMMENT ON TABLE "Rel_Diario" IS 'Dados consolidados diários de produção e consumo';
COMMENT ON TABLE "Rel_Carga" IS 'Registros individuais de cargas processadas';
COMMENT ON TABLE "Rel_Quimico" IS 'Consumo detalhado de químicos por período';
COMMENT ON TABLE "Sts_Dados" IS 'Status operacional e dados acumulados em tempo real';
COMMENT ON TABLE "ALARMHISTORY" IS 'Histórico completo de alarmes do sistema';

COMMENT ON COLUMN "Rel_Diario"."C0" IS 'Tempo de parada em minutos';
COMMENT ON COLUMN "Rel_Diario"."C1" IS 'Tempo de produção em minutos';
COMMENT ON COLUMN "Rel_Diario"."C2" IS 'Consumo de água em metros cúbicos';
COMMENT ON COLUMN "Rel_Diario"."C4" IS 'Produção total em quilogramas';

COMMENT ON COLUMN "ALARMHISTORY"."Al_Priority" IS '1=Crítico, 2=Alto, 3=Médio, 4=Baixo, 5=Info';
COMMENT ON COLUMN "ALARMHISTORY"."Al_Start_Time" IS 'Timestamp de início do alarme';
COMMENT ON COLUMN "ALARMHISTORY"."Al_Norm_Time" IS 'Timestamp de reconhecimento/normalização do alarme';
