#!/bin/bash

# Production deployment script for BoatRental
# Usage:
#   ./deploy.sh
#   ./deploy.sh --dry-run

set -euo pipefail  # Exit on error, undefined variable, and pipeline failures

ENV_FILE=".env"
DRY_RUN=false
COMPOSE_BIN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

detect_compose() {
    if docker compose version &> /dev/null; then
        COMPOSE_BIN="docker compose"
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_BIN="docker-compose"
    else
        print_error "Docker Compose is not installed"
        exit 1
    fi
}

compose_cmd() {
    ${COMPOSE_BIN} -f docker-compose.prod.yml --env-file "${ENV_FILE}" "$@"
}

get_env_value() {
    local key="$1"
    local default_value="$2"
    local value
    value=$(grep -E "^${key}=" "${ENV_FILE}" | tail -n 1 | cut -d '=' -f2-)

    if [ -z "${value}" ]; then
        echo "${default_value}"
    else
        echo "${value}"
    fi
}

check_required_env() {
    local missing=()
    local required_keys=(
        "SECRET_KEY"
        "ALLOWED_HOSTS"
        "DB_NAME"
        "DB_USER"
        "DB_PASSWORD"
        "REDIS_PASSWORD"
    )
    local key
    local value

    print_info "Checking required .env variables..."

    for key in "${required_keys[@]}"; do
        value=$(get_env_value "$key" "")
        if [ -z "$value" ]; then
            missing+=("$key")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        print_error "Missing required .env variables: ${missing[*]}"
        exit 1
    fi

    print_success "Required .env variables are present"
}

service_is_up() {
    local service_name="$1"

    if compose_cmd ps --services --status running 2>/dev/null | grep -qx "$service_name"; then
        return 0
    fi

    compose_cmd ps "$service_name" | tail -n +2 | grep -q "Up"
}

check_requirements() {
    print_info "Checking requirements..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    detect_compose

    if [ ! -f "${ENV_FILE}" ]; then
        print_error "${ENV_FILE} file not found"
        print_info "Copy .env.example to ${ENV_FILE} and configure it"
        exit 1
    fi

    print_success "All requirements met"
}

backup_database() {
    print_info "Creating database backup..."
    
    BACKUP_DIR="./backups"
    mkdir -p "$BACKUP_DIR"
    
    BACKUP_FILE="$BACKUP_DIR/db_backup_$(date +%Y%m%d_%H%M%S).sql"
    local db_user
    local db_name
    db_user=$(get_env_value "DB_USER" "boat_user")
    db_name=$(get_env_value "DB_NAME" "boat_rental")
    
    if compose_cmd ps | grep -q "db"; then
        compose_cmd exec -T db pg_dump -U "$db_user" "$db_name" > "$BACKUP_FILE"
        print_success "Database backup created: $BACKUP_FILE"
    else
        print_info "Database container not running, skipping backup"
    fi
}

build_images() {
    print_info "Building Docker images..."
    compose_cmd build --no-cache
    print_success "Images built successfully"
}

migrate_database() {
    print_info "Running database migrations..."
    compose_cmd run --rm web python manage.py migrate --noinput
    print_success "Migrations completed"
}

collect_static() {
    print_info "Collecting static files..."
    compose_cmd run --rm web python manage.py collectstatic --noinput
    print_success "Static files collected"
}

check_deploy() {
    print_info "Running deployment checks..."
    compose_cmd run --rm web python manage.py check --deploy
    print_success "Deployment checks passed"
}

validate_compose() {
    print_info "Validating docker-compose.prod.yml and env interpolation..."
    compose_cmd config > /dev/null
    print_success "Compose configuration is valid"
}

check_ssl_files() {
    local cert_path
    local key_path
    local chain_path
    local cert_host_path
    local key_host_path
    local chain_host_path

    cert_path=$(get_env_value "NGINX_SSL_CERT_PATH" "/etc/nginx/ssl/fullchain.pem")
    key_path=$(get_env_value "NGINX_SSL_KEY_PATH" "/etc/nginx/ssl/privkey.pem")
    chain_path=$(get_env_value "NGINX_SSL_CHAIN_PATH" "/etc/nginx/ssl/chain.pem")

    cert_host_path="${cert_path/\/etc\/nginx\/ssl/.\/nginx\/ssl}"
    key_host_path="${key_path/\/etc\/nginx\/ssl/.\/nginx\/ssl}"
    chain_host_path="${chain_path/\/etc\/nginx\/ssl/.\/nginx\/ssl}"

    print_info "Checking SSL certificate files for nginx..."

    if [ ! -f "$cert_host_path" ] || [ ! -f "$key_host_path" ] || [ ! -f "$chain_host_path" ]; then
        print_error "SSL certificate files not found. Expected:"
        echo "  - $cert_host_path"
        echo "  - $key_host_path"
        echo "  - $chain_host_path"
        print_info "Run: sudo ./setup-ssl.sh"
        exit 1
    fi

    print_success "SSL certificate files found"
}

restart_services() {
    print_info "Restarting services..."
    compose_cmd down
    compose_cmd up -d
    print_success "Services restarted"
}

wait_for_services() {
    print_info "Waiting for services to be healthy..."
    
    max_attempts=30
    attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if service_is_up "web" && service_is_up "nginx"; then
            print_success "Critical services (web, nginx) are up"
            return 0
        fi
        
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    print_error "Services failed to start (web/nginx not up)"
    compose_cmd ps
    show_failure_diagnostics
    return 1
}

show_status() {
    print_info "Service status:"
    compose_cmd ps
}

show_failure_diagnostics() {
    print_info "Startup diagnostics (service states):"
    compose_cmd ps || true
    compose_cmd ps -a || true
    print_info "Startup diagnostics (web/nginx/db logs):"
    compose_cmd logs --tail=160 web nginx db || true
}

# Main deployment flow
main() {
    echo "=========================================="
    echo "   BoatRental Production Deployment"
    echo "=========================================="
    echo ""
    
    # Step 1: Check requirements
    check_requirements

    # Step 2: Validate compose config
    validate_compose

    # Step 2.3: Validate required environment values
    check_required_env

    if [ "$DRY_RUN" = true ]; then
        print_success "Dry run passed. No deployment actions executed."
        return 0
    fi

    # Step 2.5: Ensure SSL files exist for nginx
    check_ssl_files
    
    # Step 3: Backup database (if exists)
    if [ "${SKIP_BACKUP:-false}" != "true" ]; then
        backup_database
    fi
    
    # Step 4: Build images
    build_images
    
    # Step 5: Run migrations
    migrate_database
    
    # Step 6: Collect static files
    collect_static
    
    # Step 7: Run deployment checks
    check_deploy
    
    # Step 8: Restart services
    restart_services
    
    # Step 9: Wait for services
    wait_for_services
    
    # Step 10: Show status
    show_status
    
    echo ""
    echo "=========================================="
    print_success "Deployment completed successfully!"
    echo "=========================================="
    echo ""
    print_info "Next steps:"
    echo "  1. Check logs: docker-compose -f docker-compose.prod.yml logs -f"
    echo "  2. Test the application: https://yourdomain.com"
    echo "  3. Monitor Celery: docker-compose -f docker-compose.prod.yml logs -f celery_worker"
    echo "  4. If nginx fails, verify SSL files exist under ./nginx/ssl and paths in .env"
    echo ""
}

# Run main function
main "$@"
