# Guia de Instalação - DSTech Dashboard

## 📋 Pré-requisitos

### Sistema Operacional
- Linux (Ubuntu 18.04+, CentOS 7+, Debian 9+)
- Windows 10+ com WSL2
- macOS 10.14+

### Software Necessário
- Python 3.8+
- PostgreSQL 12+
- Git

## 🔧 Instalação Passo a Passo

### 1. Clonar o Repositório
```bash
git clone https://github.com/dennisiautomation/dashdanielprodu-ao.git
cd dashdanielprodu-ao
```

### 2. Criar Ambiente Virtual
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate     # Windows
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar Banco de Dados PostgreSQL

#### Instalar PostgreSQL
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# CentOS/RHEL
sudo yum install postgresql-server postgresql-contrib
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

#### Criar Banco e Usuário
```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE dstech_dashboard;
CREATE USER dstech_user WITH PASSWORD 'sua_senha_segura';
GRANT ALL PRIVILEGES ON DATABASE dstech_dashboard TO dstech_user;
\q
```

### 5. Configurar Variáveis de Ambiente

Copie o arquivo `.env_dstech` e ajuste as configurações:

```bash
cp .env_dstech.example .env_dstech
nano .env_dstech
```

Conteúdo do `.env_dstech`:
```
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=dstech_user
POSTGRES_PASSWORD=sua_senha_segura
POSTGRES_DB=dstech_dashboard
DASH_PORT=8051
```

### 6. Importar Estrutura do Banco

```bash
# Se você tem um dump SQL
psql -h localhost -U dstech_user -d dstech_dashboard -f database_structure.sql

# Ou criar as tabelas manualmente (veja TABLES.sql)
```

### 7. Executar a Aplicação

```bash
python dstech_app.py
```

Acesse: http://localhost:8051

**Login padrão:**
- Usuário: `admin`
- Senha: `admin123`

## 🐳 Instalação com Docker

### 1. Criar docker-compose.yml
```yaml
version: '3.8'
services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_DB: dstech_dashboard
      POSTGRES_USER: dstech_user
      POSTGRES_PASSWORD: sua_senha_segura
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  dstech_app:
    build: .
    ports:
      - "8051:8051"
    depends_on:
      - postgres
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: dstech_user
      POSTGRES_PASSWORD: sua_senha_segura
      POSTGRES_DB: dstech_dashboard
    volumes:
      - ./logs:/app/logs

volumes:
  postgres_data:
```

### 2. Criar Dockerfile
```dockerfile
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8051

CMD ["python", "dstech_app.py"]
```

### 3. Executar
```bash
docker-compose up -d
```

## 🔧 Configuração Avançada

### Nginx Reverse Proxy
```nginx
server {
    listen 80;
    server_name seu-dominio.com;

    location / {
        proxy_pass http://127.0.0.1:8051;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Systemd Service
```ini
[Unit]
Description=DSTech Dashboard
After=network.target postgresql.service

[Service]
Type=simple
User=dstech
WorkingDirectory=/opt/dstech
Environment=PATH=/opt/dstech/venv/bin
ExecStart=/opt/dstech/venv/bin/python dstech_app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## 📊 Estrutura de Dados

### Tabelas Principais

#### Rel_Diario
```sql
CREATE TABLE "Rel_Diario" (
    "Time_Stamp" TIMESTAMP,
    "C0" NUMERIC,  -- Tempo parado (min)
    "C1" NUMERIC,  -- Tempo produção (min)
    "C2" NUMERIC,  -- Consumo água (m³)
    "C4" NUMERIC   -- Produção (kg)
);
```

#### ALARMHISTORY
```sql
CREATE TABLE "ALARMHISTORY" (
    "Al_ID" INTEGER,
    "Al_Tag" VARCHAR(100),
    "Al_Message" TEXT,
    "Al_Start_Time" TIMESTAMP,
    "Al_Norm_Time" TIMESTAMP,
    "Al_Priority" INTEGER,
    "Al_Selection" VARCHAR(50)
);
```

#### Sts_Dados
```sql
CREATE TABLE "Sts_Dados" (
    "Time_Stamp" TIMESTAMP,
    "D1" NUMERIC,  -- Água (m³)
    "D2" NUMERIC,  -- Batches
    "D3" NUMERIC   -- Produção (kg)
);
```

## 🔍 Troubleshooting

### Problemas Comuns

#### Erro de Conexão PostgreSQL
```bash
# Verificar se PostgreSQL está rodando
sudo systemctl status postgresql

# Verificar logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

#### Porta 8051 em Uso
```bash
# Encontrar processo usando a porta
sudo lsof -i :8051

# Matar processo
sudo kill -9 PID
```

#### Problemas de Permissão
```bash
# Ajustar permissões do diretório
sudo chown -R $USER:$USER /opt/dstech
chmod +x dstech_app.py
```

### Logs da Aplicação
```bash
# Executar com logs detalhados
python dstech_app.py --debug

# Verificar logs do sistema
journalctl -u dstech-dashboard -f
```

## 🔒 Segurança

### Configurações Recomendadas

1. **Alterar senha padrão**
2. **Usar HTTPS em produção**
3. **Configurar firewall**
4. **Backup regular do banco**
5. **Monitoramento de logs**

### Backup Automático
```bash
#!/bin/bash
# backup_dstech.sh
DATE=$(date +%Y%m%d_%H%M%S)
pg_dump -h localhost -U dstech_user dstech_dashboard > backup_$DATE.sql
tar -czf dstech_backup_$DATE.tar.gz *.py *.md .env_dstech backup_$DATE.sql
```

## 📞 Suporte

Para problemas técnicos:
1. Verificar logs da aplicação
2. Consultar documentação
3. Abrir issue no GitHub
4. Contatar suporte técnico

---

**Sistema testado em Ubuntu 20.04 LTS com PostgreSQL 13 e Python 3.9**
