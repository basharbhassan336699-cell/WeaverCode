#!/usr/bin/env bash
# weaver-gateway.sh — نشر WeaverCode Gateway على GCP
# الاستخدام: ./scripts/weaver-gateway.sh [setup|deploy|destroy]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATEWAY_DIR="$SCRIPT_DIR/gateway"
ACTION="${1:-help}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

info()  { echo -e "${GREEN}[WeaverGateway]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WeaverGateway]${NC} $*"; }
error() { echo -e "${RED}[WeaverGateway]${NC} $*" >&2; }

case "$ACTION" in
  setup)
    info "إعداد WeaverCode GCP Gateway..."
    if [ ! -f "$GATEWAY_DIR/gateway.yaml" ]; then
      cp "$GATEWAY_DIR/gateway.yaml.example" "$GATEWAY_DIR/gateway.yaml"
      warn "أنشأت gateway.yaml — عدّل القيم قبل النشر"
    fi
    cd "$GATEWAY_DIR" && bash setup.sh
    ;;
  deploy)
    info "نشر WeaverCode Gateway عبر Terraform..."
    cd "$GATEWAY_DIR/terraform"
    if [ ! -f "terraform.tfvars" ]; then
      cp terraform.tfvars.example terraform.tfvars
      error "عدّل terraform.tfvars أولاً ثم أعد التشغيل"
      exit 1
    fi
    terraform init && terraform plan && terraform apply
    ;;
  destroy)
    warn "حذف WeaverCode Gateway من GCP..."
    cd "$GATEWAY_DIR/terraform"
    terraform destroy
    ;;
  *)
    echo "الاستخدام: $0 [setup|deploy|destroy]"
    echo "  setup   — إعداد الملفات وتثبيت المتطلبات"
    echo "  deploy  — نشر على GCP عبر Terraform"
    echo "  destroy — حذف الموارد من GCP"
    ;;
esac
