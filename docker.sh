#!/bin/bash

# Script Manager Docker Helper
# Provides easy commands for Docker Compose operations

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored messages
print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Show usage
show_help() {
    cat << EOF
${BLUE}Script Manager Docker Helper${NC}

${YELLOW}Usage:${NC}
  ./docker.sh <command> [options]

${YELLOW}Commands:${NC}
  up              Start the application (development)
  down            Stop the application
  restart         Restart the application
  build           Build Docker images
  logs            View application logs
  logs-backend    View backend logs only
  logs-frontend   View frontend logs only
  shell-backend   Access backend shell
  shell-frontend  Access frontend shell
  clean           Remove containers and volumes
  status          Show container status
  health          Check application health
  prod            Start with production config (includes Nginx)
  prod-down       Stop production environment

${YELLOW}Examples:${NC}
  ./docker.sh up
  ./docker.sh logs -f
  ./docker.sh shell-backend
  ./docker.sh prod
  ./docker.sh down

${YELLOW}Docker Compose Commands:${NC}
  Pass through to docker-compose:
  ./docker.sh --compose <docker-compose commands>

EOF
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    print_success "Docker and Docker Compose are installed"
}

# Build images
build_images() {
    print_info "Building Docker images..."
    docker-compose build
    print_success "Images built successfully"
}

# Start application (development)
start_dev() {
    print_info "Starting Script Manager (development)..."
    docker-compose up -d
    
    print_success "Application started"
    print_info "Frontend: http://localhost:3000"
    print_info "Backend API: http://localhost:8000"
    print_info "API Docs: http://localhost:8000/docs"
    
    # Wait a moment and show health status
    sleep 2
    show_health
}

# Start application (production)
start_prod() {
    print_info "Starting Script Manager (production with Nginx)..."
    docker-compose -f docker-compose.prod.yml up -d
    
    print_success "Application started"
    print_info "Frontend: http://localhost"
    print_info "API: http://localhost/api"
    
    # Wait a moment and show health status
    sleep 2
    show_health
}

# Stop application
stop_app() {
    print_info "Stopping Script Manager..."
    docker-compose down
    print_success "Application stopped"
}

# Stop production application
stop_prod() {
    print_info "Stopping Script Manager (production)..."
    docker-compose -f docker-compose.prod.yml down
    print_success "Application stopped"
}

# Restart application
restart_app() {
    stop_app
    start_dev
}

# View logs
view_logs() {
    if [ "$1" = "backend" ]; then
        docker-compose logs "${@:2}" backend
    elif [ "$1" = "frontend" ]; then
        docker-compose logs "${@:2}" frontend
    else
        docker-compose logs "$@"
    fi
}

# Access shell
shell_backend() {
    print_info "Accessing backend shell..."
    docker-compose exec backend bash
}

shell_frontend() {
    print_info "Accessing frontend shell..."
    docker-compose exec frontend sh
}

# Show container status
show_status() {
    print_info "Container status:"
    docker-compose ps
}

# Show application health
show_health() {
    print_info "Checking application health..."
    
    # Check backend
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        print_success "Backend is healthy (http://localhost:8000)"
    else
        print_warning "Backend is starting... (check logs with './docker.sh logs-backend')"
    fi
    
    # Check frontend
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        print_success "Frontend is healthy (http://localhost:3000)"
    else
        print_warning "Frontend is starting... (check logs with './docker.sh logs-frontend')"
    fi
}

# Clean up (remove containers and volumes)
clean() {
    print_warning "This will remove containers and data volumes"
    read -p "Are you sure? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Cleaning up Docker resources..."
        docker-compose down -v
        print_success "Cleanup complete"
    else
        print_info "Cleanup cancelled"
    fi
}

# Main command handling
main() {
    if [ $# -eq 0 ]; then
        show_help
        exit 0
    fi
    
    case "$1" in
        help|-h|--help)
            show_help
            ;;
        up)
            check_docker
            start_dev
            ;;
        down)
            stop_app
            ;;
        restart)
            restart_app
            ;;
        build)
            check_docker
            build_images
            ;;
        logs)
            view_logs "${@:2}"
            ;;
        logs-backend)
            view_logs backend "${@:2}"
            ;;
        logs-frontend)
            view_logs frontend "${@:2}"
            ;;
        shell-backend)
            shell_backend
            ;;
        shell-frontend)
            shell_frontend
            ;;
        status)
            show_status
            ;;
        health)
            show_health
            ;;
        clean)
            clean
            ;;
        prod)
            check_docker
            start_prod
            ;;
        prod-down)
            stop_prod
            ;;
        --compose)
            docker-compose "${@:2}"
            ;;
        *)
            print_error "Unknown command: $1"
            echo
            show_help
            exit 1
            ;;
    esac
}

main "$@"
