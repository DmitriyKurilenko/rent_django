#!/bin/bash

# SSL Certificate Setup Script using Certbot
# This script automates Let's Encrypt SSL certificate installation for dockerized nginx

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

COMPOSE_FILE="docker-compose.prod.yml"

is_port_80_busy() {
    ss -ltn '( sport = :80 )' | grep -q ':80'
}

show_port_80_owners() {
    print_info "Port 80 listeners:"
    ss -ltnp '( sport = :80 )' || true
}

free_port_80() {
    print_info "Ensuring TCP port 80 is free for Let's Encrypt challenge..."

    if compose_cmd ps 2>/dev/null | grep -q "nginx"; then
        print_info "Stopping docker nginx temporarily..."
        compose_cmd stop nginx || true
    fi

    for svc in nginx apache2 httpd caddy; do
        if systemctl list-unit-files | grep -q "^${svc}\.service"; then
            if systemctl is-active --quiet "$svc"; then
                print_info "Stopping system service: $svc"
                systemctl stop "$svc" || true
            fi
        fi
    done

    if is_port_80_busy; then
        show_port_80_owners
        print_error "Port 80 is still busy. Stop the process above and re-run setup-ssl.sh"
        exit 1
    fi

    print_success "Port 80 is free"
}

compose_cmd() {
    if docker compose version &> /dev/null; then
        docker compose -f "${COMPOSE_FILE}" "$@"
    else
        docker-compose -f "${COMPOSE_FILE}" "$@"
    fi
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "Please run as root (use sudo)"
    exit 1
fi

# Get domain from user
read -p "Enter your domain name (e.g., example.com): " DOMAIN

if [ -z "$DOMAIN" ]; then
    print_error "Domain name cannot be empty"
    exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
    print_error "${COMPOSE_FILE} not found in current directory"
    exit 1
fi

print_info "Setting up SSL for domain: $DOMAIN"

# Install certbot if not installed
if ! command -v certbot &> /dev/null; then
    print_info "Installing certbot..."
    
    if [ -f /etc/debian_version ]; then
        # Debian/Ubuntu
        apt update
        apt install -y certbot python3-certbot-nginx
    elif [ -f /etc/redhat-release ]; then
        # CentOS/RHEL
        yum install -y certbot python3-certbot-nginx
    else
        print_error "Unsupported OS. Please install certbot manually."
        exit 1
    fi
    
    print_success "Certbot installed"
else
    print_success "Certbot already installed"
fi

# Create directories
SSL_DIR="./nginx/ssl"
mkdir -p "$SSL_DIR"

print_info "Obtaining SSL certificate..."

read -p "Enter your email for renewal notifications: " EMAIL

if [ -z "$EMAIL" ]; then
    print_error "Email cannot be empty"
    exit 1
fi

free_port_80

# Get certificate (try domain + www, fallback to domain-only)
CERT_DOMAINS=("-d" "$DOMAIN" "-d" "www.$DOMAIN")
if ! certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    "${CERT_DOMAINS[@]}"; then
    print_info "Failed for www.${DOMAIN}, retrying with ${DOMAIN} only..."
    certbot certonly \
        --standalone \
        --non-interactive \
        --agree-tos \
        --email "$EMAIL" \
        -d "$DOMAIN"
fi

if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    print_success "SSL certificate obtained successfully"
    
    # Copy certificates to project directory
    install -m 644 "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$SSL_DIR/fullchain.pem"
    install -m 600 "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$SSL_DIR/privkey.pem"
    install -m 644 "/etc/letsencrypt/live/$DOMAIN/chain.pem" "$SSL_DIR/chain.pem"
    
    print_success "Certificates copied to $SSL_DIR"
    
    # Update .env with nginx ssl template vars
    print_info "Updating .env with SSL/Nginx variables..."
    touch .env
    sed -i.bak '/^NGINX_SERVER_NAME=/d;/^NGINX_SSL_CERT_PATH=/d;/^NGINX_SSL_KEY_PATH=/d;/^NGINX_SSL_CHAIN_PATH=/d' .env
    {
        echo "NGINX_SERVER_NAME=$DOMAIN www.$DOMAIN"
        echo "NGINX_SSL_CERT_PATH=/etc/nginx/ssl/fullchain.pem"
        echo "NGINX_SSL_KEY_PATH=/etc/nginx/ssl/privkey.pem"
        echo "NGINX_SSL_CHAIN_PATH=/etc/nginx/ssl/chain.pem"
    } >> .env
    print_success ".env updated with Nginx SSL variables"
    
    # Set up auto-renewal
    print_info "Setting up automatic certificate renewal..."
    
    # Create renewal hook
        cat > /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh <<EOF
#!/bin/bash
set -e
install -m 644 /etc/letsencrypt/live/$DOMAIN/fullchain.pem $SSL_DIR/fullchain.pem
install -m 600 /etc/letsencrypt/live/$DOMAIN/privkey.pem $SSL_DIR/privkey.pem
install -m 644 /etc/letsencrypt/live/$DOMAIN/chain.pem $SSL_DIR/chain.pem
cd $(pwd)
if docker compose version >/dev/null 2>&1; then
    docker compose -f ${COMPOSE_FILE} restart nginx
else
    docker-compose -f ${COMPOSE_FILE} restart nginx
fi
EOF
    
    chmod +x /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
    
    # Add cron job for renewal (if not exists)
    if ! crontab -l | grep -q "certbot renew"; then
        (crontab -l 2>/dev/null; echo "0 0 * * * certbot renew --quiet") | crontab -
        print_success "Auto-renewal cron job added"
    fi
    
    print_info "Starting nginx container..."
    compose_cmd up -d nginx
    print_success "SSL setup completed!"
    echo ""
    echo "=========================================="
    echo "   SSL Configuration Complete"
    echo "=========================================="
    echo ""
    echo "Domain: $DOMAIN"
    echo "Certificate location: /etc/letsencrypt/live/$DOMAIN/"
    echo "Project SSL location: $SSL_DIR/"
    echo ""
    print_info "Next steps:"
    echo "  1. Verify: curl -I http://127.0.0.1 && curl -k -I https://127.0.0.1"
    echo "  2. Restart full stack if needed: ./deploy.sh"
    echo "  3. Test SSL: https://www.ssllabs.com/ssltest/analyze.html?d=$DOMAIN"
    echo "  4. Certificates will auto-renew every 60 days"
    echo ""
else
    print_error "Failed to obtain SSL certificate"
    print_info "Common issues:"
    echo "  - Port 80 is blocked by firewall"
    echo "  - Domain DNS not pointing to this server"
    echo "  - Another process using port 80"
    exit 1
fi
