#!/usr/bin/env bash
###############################################################################
# Lenskart Retail Intelligence — Server Deployment Script
#
# Usage:
#   ./scripts/deploy.sh setup       # First-time server setup
#   ./scripts/deploy.sh start       # Start all services
#   ./scripts/deploy.sh stop        # Stop all services
#   ./scripts/deploy.sh restart     # Restart API + Dagster (no infra restart)
#   ./scripts/deploy.sh ssl DOMAIN  # Set up SSL with Let's Encrypt
#   ./scripts/deploy.sh status      # Show service status
#   ./scripts/deploy.sh logs [svc]  # Tail logs (default: api)
#   ./scripts/deploy.sh update      # Pull latest code and redeploy
#   ./scripts/deploy.sh bootstrap   # Re-run data pipeline only
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"
ENV_FILE="$PROJECT_DIR/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${GREEN}[DEPLOY]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Check prerequisites ─────────────────────────────────────────────────────

check_prereqs() {
    local missing=0
    for cmd in docker git curl; do
        if ! command -v "$cmd" &>/dev/null; then
            err "$cmd is not installed"
            missing=1
        fi
    done

    if ! docker compose version &>/dev/null; then
        err "docker compose (v2) is required"
        missing=1
    fi

    if [ $missing -eq 1 ]; then
        exit 1
    fi
}

# ── First-time server setup ─────────────────────────────────────────────────

cmd_setup() {
    log "Setting up Lenskart Retail Intelligence Platform..."
    check_prereqs

    # Create .env from template if not exists
    if [ ! -f "$ENV_FILE" ]; then
        if [ -f "$PROJECT_DIR/.env.example" ]; then
            cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
            log "Created .env from template — EDIT IT before starting!"
            warn "Run: nano $ENV_FILE"
            warn "Then run: ./scripts/deploy.sh start"
            return
        else
            err ".env.example not found"
            exit 1
        fi
    fi

    # Ensure data directories exist
    mkdir -p "$PROJECT_DIR/data"

    # Pull/build images
    log "Building Docker images (this takes 5-10 minutes on first run)..."
    docker compose -f "$COMPOSE_FILE" build

    log "Setup complete."
    log "Next: ./scripts/deploy.sh start"
}

# ── Start services ───────────────────────────────────────────────────────────

cmd_start() {
    check_prereqs

    if [ ! -f "$ENV_FILE" ]; then
        err ".env file not found. Run: ./scripts/deploy.sh setup"
        exit 1
    fi

    log "Starting all services..."
    docker compose -f "$COMPOSE_FILE" up -d

    log "Waiting for API to be healthy..."
    local retries=0
    local max_retries=60
    while [ $retries -lt $max_retries ]; do
        if curl -sf http://localhost/health >/dev/null 2>&1; then
            break
        fi
        retries=$((retries + 1))
        sleep 5
    done

    if [ $retries -ge $max_retries ]; then
        warn "API did not become healthy in time. Check logs:"
        warn "  docker compose -f $COMPOSE_FILE logs api"
    else
        log ""
        log "╔═══════════════════════════════════════════════════════════╗"
        log "║   Lenskart Retail Intelligence Platform is RUNNING       ║"
        log "╠═══════════════════════════════════════════════════════════╣"
        log "║                                                         ║"
        log "║   API + Swagger:  http://YOUR_SERVER/docs               ║"
        log "║   API Endpoints:  http://YOUR_SERVER/api/v1/            ║"
        log "║   Health Check:   http://YOUR_SERVER/health             ║"
        log "║   Dagster UI:     http://YOUR_SERVER:3000               ║"
        log "║   MLflow UI:      http://YOUR_SERVER:5001               ║"
        log "║   MinIO Console:  http://YOUR_SERVER:9001               ║"
        log "║                                                         ║"
        log "╚═══════════════════════════════════════════════════════════╝"
        log ""
        log "Run: ./scripts/deploy.sh ssl YOUR_DOMAIN  to enable HTTPS"
    fi
}

# ── Stop services ────────────────────────────────────────────────────────────

cmd_stop() {
    log "Stopping all services..."
    docker compose -f "$COMPOSE_FILE" down
    log "All services stopped."
}

# ── Restart app services (not infra) ─────────────────────────────────────────

cmd_restart() {
    log "Restarting API and Dagster..."
    docker compose -f "$COMPOSE_FILE" restart api dagster-webserver dagster-daemon
    log "Restarted."
}

# ── SSL setup with Let's Encrypt ─────────────────────────────────────────────

cmd_ssl() {
    local domain="${1:-}"
    if [ -z "$domain" ]; then
        err "Usage: ./scripts/deploy.sh ssl YOUR_DOMAIN"
        exit 1
    fi

    log "Setting up SSL for $domain..."

    # Make sure nginx is running for ACME challenge
    docker compose -f "$COMPOSE_FILE" up -d nginx

    # Request certificate
    log "Requesting certificate from Let's Encrypt..."
    docker compose -f "$COMPOSE_FILE" run --rm certbot \
        certonly --webroot \
        -w /var/www/certbot \
        -d "$domain" \
        --email "admin@${domain}" \
        --agree-tos \
        --non-interactive

    if [ $? -eq 0 ]; then
        log "SSL certificate obtained!"
        log ""
        log "Now enable HTTPS in the nginx config:"
        log "  1. Edit infra/nginx/conf.d/default.conf"
        log "  2. Uncomment the HTTPS server block at the bottom"
        log "  3. Replace YOUR_DOMAIN with: $domain"
        log "  4. Uncomment the HTTP→HTTPS redirect"
        log "  5. Run: ./scripts/deploy.sh restart-nginx"
        log ""
        log "Auto-renewal: add to crontab:"
        log '  0 3 * * * cd '"$PROJECT_DIR"' && docker compose -f docker-compose.prod.yml run --rm certbot renew && docker compose -f docker-compose.prod.yml restart nginx'
    else
        err "SSL setup failed. Check the domain's DNS points to this server."
    fi
}

# ── Status ───────────────────────────────────────────────────────────────────

cmd_status() {
    docker compose -f "$COMPOSE_FILE" ps

    echo ""
    log "Service health:"

    # API
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo -e "  API:     ${GREEN}HEALTHY${NC}"
    else
        echo -e "  API:     ${RED}DOWN${NC}"
    fi

    # Dagster
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        echo -e "  Dagster: ${GREEN}HEALTHY${NC}"
    else
        echo -e "  Dagster: ${RED}DOWN${NC}"
    fi

    # MLflow
    if curl -sf http://localhost:5001 >/dev/null 2>&1; then
        echo -e "  MLflow:  ${GREEN}HEALTHY${NC}"
    else
        echo -e "  MLflow:  ${RED}DOWN${NC}"
    fi

    # Postgres
    if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U lenskart >/dev/null 2>&1; then
        echo -e "  Postgres:${GREEN} HEALTHY${NC}"
    else
        echo -e "  Postgres:${RED} DOWN${NC}"
    fi
}

# ── Logs ─────────────────────────────────────────────────────────────────────

cmd_logs() {
    local service="${1:-api}"
    docker compose -f "$COMPOSE_FILE" logs -f --tail=100 "$service"
}

# ── Update (git pull + redeploy) ─────────────────────────────────────────────

cmd_update() {
    log "Pulling latest code..."
    cd "$PROJECT_DIR"
    git pull

    log "Rebuilding images..."
    docker compose -f "$COMPOSE_FILE" build api dagster-webserver dagster-daemon

    log "Restarting services..."
    docker compose -f "$COMPOSE_FILE" up -d api dagster-webserver dagster-daemon

    log "Update complete."
    cmd_status
}

# ── Re-run bootstrap (data pipeline) ─────────────────────────────────────────

cmd_bootstrap() {
    log "Re-running data bootstrap..."
    docker compose -f "$COMPOSE_FILE" run --rm bootstrap
    log "Bootstrap complete."
}

# ── Restart nginx ─────────────────────────────────────────────────────────────

cmd_restart_nginx() {
    docker compose -f "$COMPOSE_FILE" restart nginx
    log "Nginx restarted."
}

# ── Main ─────────────────────────────────────────────────────────────────────

case "${1:-help}" in
    setup)          cmd_setup ;;
    start)          cmd_start ;;
    stop)           cmd_stop ;;
    restart)        cmd_restart ;;
    restart-nginx)  cmd_restart_nginx ;;
    ssl)            cmd_ssl "${2:-}" ;;
    status)         cmd_status ;;
    logs)           cmd_logs "${2:-}" ;;
    update)         cmd_update ;;
    bootstrap)      cmd_bootstrap ;;
    *)
        echo "Lenskart Retail Intelligence — Deployment"
        echo ""
        echo "Usage: $0 <command> [args]"
        echo ""
        echo "Commands:"
        echo "  setup              First-time server setup"
        echo "  start              Start all services"
        echo "  stop               Stop all services"
        echo "  restart            Restart API + Dagster"
        echo "  restart-nginx      Restart nginx only"
        echo "  ssl DOMAIN         Set up Let's Encrypt SSL"
        echo "  status             Show service status"
        echo "  logs [service]     Tail logs (default: api)"
        echo "  update             Git pull + rebuild + restart"
        echo "  bootstrap          Re-run data pipeline"
        ;;
esac
