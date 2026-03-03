# SceneDream Deployment

This document describes deploying SceneDream with Docker Compose. It assumes a reverse proxy (for example Traefik) is already set up for TLS and routing.

## Prerequisites

- A Linux host with Docker Engine and Docker Compose
- DNS records pointing your domain/subdomains to the host
- A deployment user with access to Docker

## Required Environment Variables

Set these in your deployment environment or GitHub Actions secrets:

- `ENVIRONMENT` (`staging` or `production`)
- `DOMAIN`
- `STACK_NAME`
- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `SMTP_HOST` (optional)
- `SMTP_USER` (optional)
- `SMTP_PASSWORD` (optional)
- `EMAILS_FROM_EMAIL` (optional)
- `SENTRY_DSN` (optional)

SceneDream does not require `FIRST_SUPERUSER` or `FIRST_SUPERUSER_PASSWORD`.

## Deploy with Docker Compose

```bash
docker compose -f docker-compose.yml --project-name "$STACK_NAME" build
docker compose -f docker-compose.yml --project-name "$STACK_NAME" up -d
```

## GitHub Actions Workflows

Repository workflows in `.github/workflows/` include:

- `deploy-staging.yml`
- `deploy-production.yml`
- `generate-client.yml`

Configure environment-specific secrets for staging/production domains and stack names.

## Post-Deploy Checks

- API docs endpoint responds: `https://api.<domain>/docs`
- Frontend responds: `https://dashboard.<domain>` (or your configured frontend host)
- Pipeline routes return expected data
- Background generation jobs can write outputs under `img/generated/`

## Data Safety

- Do not run destructive DB commands in deployment scripts.
- Preserve SceneDream domain tables and records (scene extractions/rankings/prompts/images/documents/pipeline runs/generated assets/social posting).
