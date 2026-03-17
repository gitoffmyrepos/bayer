#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Nightwatch Deploy Script — Phase 1
# Deploys the full Nightwatch monitoring stack to Kubernetes
#
# Usage:
#   ./deploy.sh                  # Deploy everything
#   ./deploy.sh --dry-run        # Preview what would be deployed
#   ./deploy.sh --namespace-only # Only create namespace + RBAC
#   ./deploy.sh --uninstall      # Remove all Nightwatch resources
#
# Prerequisites:
#   - kubectl configured with access to the target cluster
#   - Secrets updated (see "Pre-flight" section below)
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

NIGHTWATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KUBECTL="kubectl"
DRY_RUN=false
NAMESPACE_ONLY=false
UNINSTALL=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

log_info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
log_step()    { echo -e "\n${BLUE}══════ $* ══════${NC}"; }

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --dry-run)        DRY_RUN=true ;;
        --namespace-only) NAMESPACE_ONLY=true ;;
        --uninstall)      UNINSTALL=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--namespace-only] [--uninstall]"
            exit 0
            ;;
        *)
            log_warn "Unknown argument: $arg"
            ;;
    esac
done

# Set kubectl flags
KUBECTL_FLAGS=""
if $DRY_RUN; then
    KUBECTL_FLAGS="--dry-run=client"
    log_warn "DRY RUN mode — no changes will be applied"
fi

apply() {
    local path="$1"
    local label="${2:-$path}"
    log_info "Applying: $label"
    if $DRY_RUN; then
        $KUBECTL apply -f "$path" --dry-run=client
    else
        $KUBECTL apply -f "$path"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# Uninstall
# ─────────────────────────────────────────────────────────────────────────────
if $UNINSTALL; then
    log_step "UNINSTALLING Nightwatch"
    log_warn "This will delete ALL Nightwatch resources including persistent data!"
    read -p "Are you sure? Type 'yes' to confirm: " confirm
    if [ "$confirm" != "yes" ]; then
        log_info "Aborted."
        exit 0
    fi
    $KUBECTL delete namespace nightwatch --ignore-not-found=true
    $KUBECTL delete clusterrole nightwatch-collector-role --ignore-not-found=true
    $KUBECTL delete clusterrolebinding nightwatch-collector-rolebinding --ignore-not-found=true
    log_success "Nightwatch uninstalled"
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────
log_step "Pre-flight Checks"

# Check kubectl access
if ! $KUBECTL cluster-info &>/dev/null; then
    log_error "Cannot connect to Kubernetes cluster. Is kubectl configured?"
    exit 1
fi
log_success "kubectl connected to cluster"

# Check that secrets have been updated
SECRETS_TO_CHECK=(
    "k8s/alerting/alertmanager.yaml:REPLACE_WITH_SLACK_WEBHOOK_URL"
    "k8s/alerting/alertmanager.yaml:REPLACE_WITH_ALERT_EMAIL"
    "k8s/collectors/aws-pipeline-collector.yaml:REPLACE_WITH_AWS_ACCESS_KEY_ID"
    "k8s/collectors/aws-pipeline-collector.yaml:BAYER_ACCOUNT_ID"
)

SECRETS_MISSING=false
for check in "${SECRETS_TO_CHECK[@]}"; do
    file="${NIGHTWATCH_DIR}/${check%%:*}"
    placeholder="${check##*:}"
    if grep -q "$placeholder" "$file" 2>/dev/null; then
        log_warn "Placeholder not replaced in: $file → $placeholder"
        SECRETS_MISSING=true
    fi
done

if $SECRETS_MISSING && ! $DRY_RUN; then
    log_error "Please replace all placeholder values before deploying."
    log_error "See README.md → Pre-deployment Configuration section."
    echo ""
    log_info "Required replacements:"
    echo "  1. k8s/alerting/alertmanager.yaml — SLACK_WEBHOOK_URL, ALERT_EMAIL, SMTP settings"
    echo "  2. k8s/collectors/aws-pipeline-collector.yaml — AWS credentials, account ID"
    echo "  3. k8s/dashboards/grafana.yaml — Admin password (optional)"
    echo ""
    read -p "Continue anyway? (for testing) [y/N]: " force
    [ "${force:-N}" = "y" ] || exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Deploy
# ─────────────────────────────────────────────────────────────────────────────
log_step "Step 1: Namespace + Resource Quotas"
apply "$NIGHTWATCH_DIR/k8s/namespace/"

log_step "Step 2: RBAC — ServiceAccount, Roles, Bindings"
apply "$NIGHTWATCH_DIR/k8s/rbac/"

if $NAMESPACE_ONLY; then
    log_success "Namespace + RBAC deployed. Exiting (--namespace-only mode)."
    exit 0
fi

log_step "Step 3: Storage — VictoriaMetrics + OpenSearch"
apply "$NIGHTWATCH_DIR/k8s/storage/"

log_info "Waiting for storage to be ready..."
if ! $DRY_RUN; then
    $KUBECTL wait --for=condition=available --timeout=300s deployment/victoriametrics -n nightwatch 2>/dev/null || \
        log_warn "VictoriaMetrics may still be starting (this is OK for first deploy)"
fi

log_step "Step 4: Collectors — OTel, Fluent Bit, Prometheus, AWS Pipeline Collector"
apply "$NIGHTWATCH_DIR/k8s/collectors/"

log_step "Step 5: Alerting — AlertManager"
apply "$NIGHTWATCH_DIR/k8s/alerting/"

log_step "Step 6: Dashboards — Grafana"
apply "$NIGHTWATCH_DIR/k8s/dashboards/"

# ─────────────────────────────────────────────────────────────────────────────
# Post-deploy status
# ─────────────────────────────────────────────────────────────────────────────
if ! $DRY_RUN; then
    log_step "Deployment Status"

    echo ""
    log_info "Waiting for pods to start (up to 5 minutes)..."
    $KUBECTL wait --for=condition=ready pod --selector="app.kubernetes.io/part-of=nightwatch-platform" \
        --timeout=300s -n nightwatch 2>/dev/null || true

    echo ""
    log_info "Pod status:"
    $KUBECTL get pods -n nightwatch -o wide

    echo ""
    log_info "PVC status:"
    $KUBECTL get pvc -n nightwatch

    echo ""
    log_info "Services:"
    $KUBECTL get svc -n nightwatch

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Nightwatch Phase 1 Deployed! ⚡${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "  Access Grafana:"
    echo -e "  ${CYAN}kubectl port-forward svc/grafana 3000:3000 -n nightwatch${NC}"
    echo "  Then open: http://localhost:3000 (admin / NightWatch2026!)"
    echo ""
    echo "  Access AlertManager:"
    echo -e "  ${CYAN}kubectl port-forward svc/alertmanager 9093:9093 -n nightwatch${NC}"
    echo ""
    echo "  Access VictoriaMetrics:"
    echo -e "  ${CYAN}kubectl port-forward svc/victoriametrics 8428:8428 -n nightwatch${NC}"
    echo ""
    echo "  Access OpenSearch Dashboards:"
    echo -e "  ${CYAN}kubectl port-forward svc/opensearch-dashboards 5601:5601 -n nightwatch${NC}"
    echo ""
    echo "  Check collector metrics:"
    echo -e "  ${CYAN}kubectl port-forward svc/aws-pipeline-collector 8080:8080 -n nightwatch${NC}"
    echo "  Then: curl http://localhost:8080/metrics"
    echo ""
fi
