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

pin_runtime_env_from_file() {
    # Docker Compose interpolation prefers shell env over --env-file.
    # Pin critical keys from .env to avoid accidental overrides from CI/shell.
    print_info "Pinning runtime env from ${ENV_FILE}..."

    export DEBUG="$(get_env_value "DEBUG" "False")"
    export SECURE_SSL_REDIRECT="$(get_env_value "SECURE_SSL_REDIRECT" "True")"
    export SESSION_COOKIE_SECURE="$(get_env_value "SESSION_COOKIE_SECURE" "True")"
    export CSRF_COOKIE_SECURE="$(get_env_value "CSRF_COOKIE_SECURE" "True")"
    export USE_X_FORWARDED_HOST="$(get_env_value "USE_X_FORWARDED_HOST" "True")"
    export SECURE_CONTENT_TYPE_NOSNIFF="$(get_env_value "SECURE_CONTENT_TYPE_NOSNIFF" "True")"
    export SECURE_HSTS_INCLUDE_SUBDOMAINS="$(get_env_value "SECURE_HSTS_INCLUDE_SUBDOMAINS" "True")"
    export SECURE_HSTS_PRELOAD="$(get_env_value "SECURE_HSTS_PRELOAD" "True")"

    print_success "Pinned runtime env values from ${ENV_FILE}"
}

is_valid_bool() {
    local value_lower
    value_lower=$(echo "$1" | tr '[:upper:]' '[:lower:]')

    case "$value_lower" in
        true|false|1|0|yes|no|on|off|'')
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

validate_bool_env() {
    local key="$1"
    local default_value="$2"
    local value
    value=$(get_env_value "$key" "$default_value")

    if ! is_valid_bool "$value"; then
        print_error "Invalid boolean value for ${key}: '${value}'"
        print_info "Allowed values: true/false, 1/0, yes/no, on/off"
        exit 1
    fi
}

validate_env_values() {
    print_info "Validating .env values format..."
    validate_bool_env "DEBUG" "False"
    validate_bool_env "SECURE_SSL_REDIRECT" "True"
    validate_bool_env "SESSION_COOKIE_SECURE" "True"
    validate_bool_env "CSRF_COOKIE_SECURE" "True"
    validate_bool_env "USE_X_FORWARDED_HOST" "True"
    validate_bool_env "SECURE_CONTENT_TYPE_NOSNIFF" "True"
    validate_bool_env "SECURE_HSTS_INCLUDE_SUBDOMAINS" "True"
    validate_bool_env "SECURE_HSTS_PRELOAD" "True"
    print_success ".env values format is valid"
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
    print_info "Building Docker images (including Tailwind+DaisyUI CSS)..."
    compose_cmd build
    print_success "Images built successfully"
}

prepare_app() {
    print_info "Running migrations, collecting static, deploy check..."
    compose_cmd run --rm web sh -c "\
        python manage.py migrate --noinput && \
        python manage.py collectstatic --noinput && \
        python manage.py check --deploy"
    print_success "App preparation completed"
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
    pin_runtime_env_from_file

    # Step 2: Validate compose config
    validate_compose

    # Step 2.3: Validate required environment values
    check_required_env
    validate_env_values

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
    
    # Step 5: Migrate + collectstatic + check (one container)
    prepare_app
    
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
