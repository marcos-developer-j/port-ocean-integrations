#!/usr/bin/env bash
# Construye las imágenes Docker de las 4 integraciones y las carga en el cluster kind.
# Uso: ./build-and-load.sh [nombre-cluster] [integracion...]
#   ./build-and-load.sh                        # todas, cluster "port-ocean"
#   ./build-and-load.sh port-ocean jfrog orca  # solo jfrog y orca
set -euo pipefail

CLUSTER="${1:-port-ocean}"
shift || true
INTEGRATIONS=("$@")
if [ ${#INTEGRATIONS[@]} -eq 0 ]; then
  INTEGRATIONS=(jfrog orca veracode github-projects)
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

for integ in "${INTEGRATIONS[@]}"; do
  echo "==> Building port-ocean-${integ}:local"
  docker build -t "port-ocean-${integ}:local" "${ROOT}/${integ}"
  echo "==> Loading into kind cluster '${CLUSTER}'"
  kind load docker-image "port-ocean-${integ}:local" --name "${CLUSTER}"
done

echo "Done. Images available in the cluster:"
printf '  port-ocean-%s:local\n' "${INTEGRATIONS[@]}"
