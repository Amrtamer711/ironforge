# Deployment Guide

Options for deploying the CRM platform to production.

## Deployment Options

| Option | Use Case | Complexity |
|--------|----------|------------|
| Docker Compose | Single server, small team | Low |
| Render.com | Managed hosting, auto-scaling | Low |
| Manual Uvicorn | Custom infrastructure | Medium |

---

## Option 1: Docker Compose (Single Server)

Best for: Single server deployments, self-hosted environments.

### Production Deployment

```bash
# Build and start
docker-compose up -d --build

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Environment Configuration

Create `.env` files for each service:
- `sales-module/.env`
- `unified-ui/.env`

Or use root-level configuration with docker-compose.

### Production docker-compose.yml

The production compose file:
- Uses per-service `.env` files
- Sets ENVIRONMENT=production
- Configures health checks
- Uses named volumes for persistence

### Health Checks

Both services expose `/health` endpoints:
```bash
curl https://your-domain.com:8000/health
curl https://your-domain.com:3005/health
```

---

## Option 2: Render.com (Managed Hosting)

Best for: Auto-scaling, zero-ops deployment, CI/CD integration.

Each service has its own `render.yaml` for independent deployment.

### Deploy Sales Module

```bash
cd sales-module
render blueprint apply
```

### Deploy Unified UI

```bash
cd unified-ui
render blueprint apply
```

### Environment Variables on Render

Set via Render dashboard or `render.yaml`:

**Sales Module:**
| Variable | Value |
|----------|-------|
| ENVIRONMENT | production |
| DB_BACKEND | supabase |
| AUTH_PROVIDER | supabase |
| SALESBOT_PROD_SUPABASE_URL | (your URL) |
| SALESBOT_PROD_SUPABASE_SERVICE_ROLE_KEY | (your key) |
| PROXY_SECRET | (shared secret) |
| OPENAI_API_KEY | (your key) |
| GOOGLE_API_KEY | (your key) |

**Unified UI:**
| Variable | Value |
|----------|-------|
| ENVIRONMENT | production |
| SALES_BOT_URL | https://proposal-bot.onrender.com |
| UI_PROD_SUPABASE_URL | (your URL) |
| UI_PROD_SUPABASE_ANON_KEY | (your key) |
| UI_PROD_SUPABASE_SERVICE_ROLE_KEY | (your key) |
| PROXY_SECRET | (shared secret - must match) |

### Service URLs After Deploy

| Service | URL |
|---------|-----|
| proposal-bot | https://proposal-bot.onrender.com |
| unified-ui | https://unified-ui.onrender.com |

---

## Option 3: Manual Uvicorn

Best for: Custom infrastructure (AWS, GCP, Azure, bare metal).

### Sales Module

```bash
cd sales-module
pip install -r requirements.txt
uvicorn api.server:app --host 0.0.0.0 --port 8000
```

### Unified UI

```bash
cd unified-ui
pip install -r requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 3005
```

### Process Management with systemd

```ini
# /etc/systemd/system/proposal-bot.service
[Unit]
Description=Proposal Bot
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/CRM/sales-module
Environment="ENVIRONMENT=production"
Environment="PORT=8000"
ExecStart=/opt/CRM/sales-module/venv/bin/uvicorn api.server:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/unified-ui.service
[Unit]
Description=Unified UI
After=network.target proposal-bot.service

[Service]
User=www-data
WorkingDirectory=/opt/CRM/unified-ui
Environment="ENVIRONMENT=production"
Environment="PORT=3005"
Environment="SALES_BOT_URL=http://localhost:8000"
ExecStart=/opt/CRM/unified-ui/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 3005
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable proposal-bot unified-ui
sudo systemctl start proposal-bot unified-ui
```

---

## SSL/TLS Configuration

### With Render.com

- Automatic SSL provided
- Custom domains supported via Render dashboard

### With Docker Compose / Manual

Use nginx reverse proxy with Let's Encrypt:

```nginx
# /etc/nginx/sites-available/crm
server {
    listen 80;
    server_name crm.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name crm.example.com;

    ssl_certificate /etc/letsencrypt/live/crm.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/crm.example.com/privkey.pem;

    # Unified UI (frontend)
    location / {
        proxy_pass http://localhost:3005;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Direct API access (optional)
    location /api/direct/ {
        proxy_pass http://localhost:8000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Scaling Considerations

### Horizontal Scaling

Both services are stateless and can scale horizontally:
- Use load balancer in front of multiple instances
- Session state stored in Supabase
- File storage in Supabase Storage

### Database

- Supabase handles PostgreSQL scaling
- Connection pooling enabled by default
- Consider read replicas for heavy read loads

### File Storage

- Production uses Supabase Storage
- Large files (mockups, proposals) stored remotely
- Consider CDN for static assets

---

## Monitoring

### Health Endpoints

```bash
# Sales module
curl https://your-domain.com/api/direct/health

# Unified UI
curl https://your-domain.com/health
```

### Logging

- Structured JSON logging in production
- Log aggregation via Render, CloudWatch, etc.
- Key metrics to monitor:
  - Request latency
  - Error rates (4xx, 5xx)
  - LLM token usage

### Render.com Monitoring

- Built-in metrics dashboard
- Alert configuration
- Log streaming

---

## Backup & Recovery

### Database

- Supabase provides automatic daily backups
- Point-in-time recovery available on Pro plan
- Manual backup: Supabase dashboard -> Database -> Backups

### File Storage

- Supabase Storage with redundancy
- Consider additional backup for critical files
- Export strategy for large file sets

---

## Environment Matrix

| Variable | Development | Production |
|----------|-------------|------------|
| ENVIRONMENT | development | production |
| DB_BACKEND | supabase | supabase |
| SUPABASE_* | *_DEV_* vars | *_PROD_* vars |
| DEV_AUTH_ENABLED | true (optional) | false |
| LOG_LEVEL | DEBUG | INFO |

---

## Checklist

### Pre-Deployment

- [ ] All environment variables set
- [ ] PROXY_SECRET matches between services
- [ ] Supabase production project configured
- [ ] RLS policies verified
- [ ] API keys rotated from development

### Post-Deployment

- [ ] Health checks passing
- [ ] SSL certificate valid
- [ ] Authentication flow working
- [ ] Proxy to sales-module working
- [ ] File uploads working
- [ ] LLM integration working

---

## Related Documentation

| Document | Description |
|----------|-------------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Full system architecture |
| [DEVELOPMENT.md](./DEVELOPMENT.md) | Development setup guide |
| [sales-module/README.md](./sales-module/README.md) | Sales module docs |
| [unified-ui/README.md](./unified-ui/README.md) | Unified UI docs |
