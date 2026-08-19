# Integración Ocean: GCP (multi-proyecto con Service Account a nivel de organización)

> Integración **OFICIAL** del framework Ocean de Port. Verificada en el repositorio oficial
> [port-labs/ocean/integrations/gcp](https://github.com/port-labs/ocean/tree/main/integrations/gcp)
> (`.port/spec.yaml`) y en la documentación oficial de Port
> ([GCP](https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/gcp/)).

La integración de GCP (`integration.type: gcp`) exporta recursos de Google Cloud al catálogo de Port usando la **Cloud Asset Inventory API** (`cloudasset.googleapis.com`), lo que le permite descubrir recursos de TODOS los proyectos visibles para la Service Account con una sola instalación. La autenticación usa **Application Default Credentials (ADC)**: una key JSON de Service Account codificada en base64 (`encodedADCConfiguration`) o Workload Identity en GKE.

## Qué sincroniza (kinds y blueprints por defecto)

Kinds por defecto según la doc oficial (el spec no fija resources; el mapping default de la doc incluye):

| Kind (asset type de Cloud Asset Inventory) | Blueprint en Port | Contenido |
|---|---|---|
| `cloudresourcemanager.googleapis.com/Project` | `gcpProject` | Proyectos descubiertos |
| `container.googleapis.com/Cluster` | `gcpCloudResource` | Clusters GKE |
| `cloudfunctions.googleapis.com/CloudFunction` | `gcpCloudResource` | Cloud Functions |
| `pubsub.googleapis.com/Topic` | `gcpCloudResource` | Topics Pub/Sub |
| `pubsub.googleapis.com/Subscription` | `gcpCloudResource` | Suscripciones Pub/Sub |
| `compute.googleapis.com/Disk` | `gcpCloudResource` | Discos de Compute Engine |
| `iam.googleapis.com/ServiceAccount` | `gcpCloudResource` | Service Accounts |

Con `initializePortResources: true` los blueprints (`gcpProject`, `gcpCloudResource`) y el mapping por defecto se crean automáticamente. Puedes añadir al mapping cualquier [asset type soportado por Cloud Asset Inventory](https://cloud.google.com/asset-inventory/docs/supported-asset-types).

## Qué necesitas

- Cluster Kubernetes con ArgoCD y el app-of-apps de este repo ya sincronizando (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- Namespace destino `port-idp` (lo crea el ApplicationSet con `CreateNamespace=true`).
- Credenciales de Port (Client ID / Client Secret). Región US: `https://api.us.getport.io`.
- Organización o folder de GCP y permisos para:
  - Crear una Service Account en un proyecto "host" (`roles/iam.serviceAccountAdmin` en ese proyecto).
  - Conceder IAM bindings a nivel de organización/folder (`roles/resourcemanager.organizationAdmin` o equivalente).
- APIs habilitadas en el proyecto host (donde "vive" la SA y contra el que se facturan las cuotas):
  - `cloudasset.googleapis.com` (Cloud Asset API) — **obligatoria**.
  - `cloudresourcemanager.googleapis.com` (Cloud Resource Manager API) — **obligatoria** (proyectos/folders/org).
  - `pubsub.googleapis.com` — solo si sincronizas topics/subscriptions.
  - `cloudquotas.googleapis.com` (Cloud Quotas API) — opcional; permite rate limiting dinámico (si no, cuota fija 400/min).
- `gcloud` CLI autenticada (`gcloud auth login`) y `kubectl` apuntando al cluster de laboratorio.

## Arquitectura multi-proyecto

Mecanismo: una única **Service Account** con roles de solo lectura concedidos a nivel de **organización** (o folder). La integración usa Cloud Asset Inventory (`searchAllResources`) y Resource Manager para enumerar proyectos y recursos de TODO el scope donde la SA tiene permisos: no hay que instalar nada por proyecto ni enumerarlos manualmente; los proyectos nuevos bajo la organización/folder se descubren solos.

```
                    GCP Organization (org-id: 123456789)
                    ┌───────────────────────────────────┐
   IAM bindings ───▶│ roles/cloudasset.viewer           │
   (a nivel org)    │ roles/browser                     │
                    │ member: port-ocean-gcp@host-      │
                    │         project.iam.gserviceaccount.com
                    └───────┬─────────────┬─────────────┘
                            │  herencia   │
              ┌─────────────▼──┐   ┌──────▼─────────┐
              │ Folder "prod"  │   │ Folder "dev"   │
              └───┬────────┬───┘   └──────┬─────────┘
                  │        │              │
            ┌─────▼──┐ ┌───▼────┐   ┌─────▼──┐
            │ proj-a │ │ proj-b │   │ proj-c │   ... (y futuros)
            └────────┘ └────────┘   └────────┘
                  ▲
                  │ Cloud Asset Inventory API (searchAllResources)
         ┌────────┴─────────┐
         │ K8s (port-idp)   │
         │ pod ocean-gcp    │
         │ ADC = key JSON   │
         │ base64           │
         └──────────────────┘
```

Roles necesarios (doc oficial):

- `roles/cloudasset.viewer` (**Cloud Asset Viewer**) — lectura de metadatos de assets (permisos `cloudasset.*`).
- `roles/browser` (**Browser**) — lectura de la jerarquía proyectos/folders/org (permisos `resourcemanager.*`).

Se pueden conceder a nivel de proyecto, folder u organización: la integración ingiere todos los recursos de todos los proyectos alcanzables con esos permisos.

## Paso 1 — Preparar credenciales en GCP

### 1.1 Habilitar APIs en el proyecto host

```bash
HOST_PROJECT=port-integrations-host   # proyecto donde vive la SA
ORG_ID=123456789                      # gcloud organizations list
SA_NAME=port-ocean-gcp
SA_EMAIL=${SA_NAME}@${HOST_PROJECT}.iam.gserviceaccount.com

gcloud services enable \
  cloudasset.googleapis.com \
  cloudresourcemanager.googleapis.com \
  pubsub.googleapis.com \
  cloudquotas.googleapis.com \
  --project ${HOST_PROJECT}
```

### 1.2 Crear la Service Account

```bash
gcloud iam service-accounts create ${SA_NAME} \
  --project ${HOST_PROJECT} \
  --display-name "Port Ocean GCP integration (read-only)"
```

### 1.3 Crear la key JSON y codificarla en base64 (`encodedADCConfiguration`)

```bash
gcloud iam service-accounts keys create port-ocean-gcp-key.json \
  --iam-account ${SA_EMAIL}

# Linux/macOS (sin saltos de línea):
base64 -w 0 port-ocean-gcp-key.json > port-ocean-gcp-key.b64   # macOS: base64 -i ... | tr -d '\n'

# Windows PowerShell:
# [Convert]::ToBase64String([System.IO.File]::ReadAllBytes("port-ocean-gcp-key.json")) | Out-File -NoNewline port-ocean-gcp-key.b64
```

> Seguridad: la doc oficial indica que el fichero codificado NO se envía a Port en ningún momento; solo lo consume el pod localmente. Aun así, trata la key como un secreto: no la subas a git y bórrala del disco tras crear el Secret.

> Alternativa sin key: en GKE puedes usar **Workload Identity** (ServiceAccount de K8s anotado con `iam.gke.io/gcp-service-account` + `podServiceAccount.name` en el chart y volúmenes proyectados según la doc oficial), omitiendo `encodedADCConfiguration`.

## Paso 2 — Configurar multi-proyecto (bindings a nivel de organización)

### Opción A (recomendada) — Toda la organización

```bash
gcloud organizations add-iam-policy-binding ${ORG_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudasset.viewer"

gcloud organizations add-iam-policy-binding ${ORG_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/browser"
```

### Opción B — Solo un folder (subárbol de proyectos)

```bash
FOLDER_ID=456789123   # gcloud resource-manager folders list --organization $ORG_ID

gcloud resource-manager folders add-iam-policy-binding ${FOLDER_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudasset.viewer"

gcloud resource-manager folders add-iam-policy-binding ${FOLDER_ID} \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/browser"
```

### Opción C — Proyectos sueltos

```bash
for PROJ in proj-a proj-b proj-c; do
  gcloud projects add-iam-policy-binding ${PROJ} \
    --member="serviceAccount:${SA_EMAIL}" --role="roles/cloudasset.viewer"
  gcloud projects add-iam-policy-binding ${PROJ} \
    --member="serviceAccount:${SA_EMAIL}" --role="roles/browser"
done
```

Verifica los bindings a nivel org:

```bash
gcloud organizations get-iam-policy ${ORG_ID} \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:${SA_EMAIL}" \
  --format="table(bindings.role)"
```

## Paso 3 — Crear el Secret en Kubernetes

Mapeo config → variable de entorno (`OCEAN__INTEGRATION__CONFIG__<SNAKE_UPPER>`):

| Clave del spec (camelCase) | Variable de entorno | Sensible |
|---|---|---|
| `encodedADCConfiguration` | `OCEAN__INTEGRATION__CONFIG__ENCODED_ADC_CONFIGURATION` | Sí en la práctica (es la credencial); al Secret |
| `searchAllResourcesPerMinuteQuota` | `OCEAN__INTEGRATION__CONFIG__SEARCH_ALL_RESOURCES_PER_MINUTE_QUOTA` | No (va en values) |
| `cloudFunctionSecret` (opcional, objeto) | `OCEAN__INTEGRATION__CONFIG__CLOUD_FUNCTION_SECRET` | Sí (spec: sensitive) |

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-gcp-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__ENCODED_ADC_CONFIGURATION="$(cat port-ocean-gcp-key.b64)"
```

Verifica y limpia:

```bash
kubectl get secret ocean-gcp-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
rm -f port-ocean-gcp-key.json port-ocean-gcp-key.b64
```

## Paso 4 — Values del chart

Archivo: `deployment/install/ocean-gcp/values.yaml` (rama `laboratory`).

```yaml
# Values de la integración Ocean GCP (oficial) para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-gcp-credentials"
# creado a mano en el namespace port-idp.
port:
  baseUrl: https://api.us.getport.io

# Integración OFICIAL: crea blueprints y mapping por defecto en el primer arranque
initializePortResources: true

# Resync programado (minutos)
scheduledResyncInterval: 1440

# Imagen oficial de ghcr.io/port-labs (default del chart): NO definir
# imageRegistry custom ni imagePullPolicy Never.

# No crear el Secret desde el chart: usar el Secret manual del namespace.
# Debe contener: OCEAN__PORT__CLIENT_ID, OCEAN__PORT__CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__ENCODED_ADC_CONFIGURATION
secret:
  create: false
  name: ocean-gcp-credentials

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "500m"

integration:
  identifier: gcp
  type: gcp
  eventListener:
    type: POLLING
  config:
    # Cuota de peticiones/min a Cloud Asset Inventory (default oficial: 400).
    # Ajusta si tu proyecto host tiene otra cuota de searchAllResources.
    searchAllResourcesPerMinuteQuota: 400
```

## Paso 5 — ApplicationSet

Archivo: `deployment/applicationsets/32-ocean-gcp.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-gcp
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - clusters:
        selector:
          matchLabels:
            project: port
            environment: laboratory
          matchExpressions:
            - key: cloud
              operator: Exists
  template:
    metadata:
      name: 'port-ocean-gcp-{{.name}}'
      annotations:
        argocd.argoproj.io/sync-wave: "0"
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      sources:
        - repoURL: https://port-labs.github.io/helm-charts
          chart: port-ocean
          targetRevision: 0.23.4
          helm:
            releaseName: gcp
            valueFiles:
              - $values/deployment/install/ocean-gcp/values.yaml
        - repoURL: https://github.com/marcos-developer-j/port-ocean-integrations.git
          targetRevision: laboratory
          ref: values
      destination:
        server: '{{.server}}'
        namespace: port-idp
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ApplyOutOfSyncOnly=true
```

## Paso 6 — Verificación

```bash
kubectl get pods -n port-idp -l app.kubernetes.io/instance=gcp
kubectl logs -n port-idp -l app.kubernetes.io/instance=gcp -f --tail=200
```

Qué buscar en los logs:

- ADC cargadas correctamente (sin `DefaultCredentialsError` ni `invalid_grant`).
- Descubrimiento de proyectos: deben listarse TODOS los proyectos del scope (prueba real del multi-proyecto).
- Llamadas a `searchAllResources` por asset type con contadores de entidades.
- Mensajes de rate limiting dinámico si `cloudquotas` está habilitada (informativos, no errores).
- `Resync finished successfully`.

En Port:

1. **Builder** → blueprints `gcpProject` y `gcpCloudResource` creados.
2. **Catalog** → entidades de recursos pertenecientes a MÁS de un proyecto (verifica la propiedad project).
3. **Data sources** → integración `gcp` en verde con timestamp de último resync.

## Instalación alternativa

### Terraform (tiempo real vía Asset Feeds + Pub/Sub) — Cloud Run

Según el spec oficial: módulo `port-labs/integration-factory/ocean`, ejemplo `gcp_cloud_run`, versión `>= 0.0.31`. Despliega la integración en Cloud Run y configura eventos en tiempo real con Cloud Asset Feeds → Pub/Sub → endpoint `/integration/events`:

```hcl
module "ocean_gcp" {
  source  = "port-labs/integration-factory/ocean//examples/gcp_cloud_run"
  version = ">=0.0.31"

  port = {
    client_id     = var.port_client_id
    client_secret = var.port_client_secret
    base_url      = "https://api.us.getport.io"
  }

  integration = {
    type       = "gcp"
    identifier = "gcp"
  }
  # Resto de variables (proyecto, región, asset types del feed):
  # verificar en el README del ejemplo gcp_cloud_run del módulo oficial.
}
```

Creación manual del feed (si prefieres montar el tiempo real a mano sobre el despliegue Helm expuesto públicamente):

```bash
gcloud pubsub topics create port-ocean-gcp-events --project ${HOST_PROJECT}

gcloud pubsub subscriptions create port-ocean-gcp-events-push \
  --topic port-ocean-gcp-events \
  --push-endpoint "https://<URL_PUBLICA_DE_LA_INTEGRACION>/integration/events" \
  --project ${HOST_PROJECT}

gcloud asset feeds create port-ocean-feed \
  --organization ${ORG_ID} \
  --pubsub-topic "projects/${HOST_PROJECT}/topics/port-ocean-gcp-events" \
  --asset-types "container.googleapis.com/Cluster,pubsub.googleapis.com/Topic" \
  --content-type resource
```

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `PERMISSION_DENIED: Cloud Asset API has not been used in project ...` | `cloudasset.googleapis.com` no habilitada en el proyecto host | `gcloud services enable cloudasset.googleapis.com --project $HOST_PROJECT` y espera unos minutos |
| `PERMISSION_DENIED` en `searchAllResources` sobre la org | Falta `roles/cloudasset.viewer` en el scope (org/folder) | Repite el binding del Paso 2 y verifica con `get-iam-policy` |
| Se descubren recursos pero faltan proyectos | Falta `roles/browser` (jerarquía) o el folder correcto | Añade `roles/browser` en el mismo scope que `cloudasset.viewer` |
| `DefaultCredentialsError` / `Could not automatically determine credentials` | `ENCODED_ADC_CONFIGURATION` ausente, mal codificada (saltos de línea) o JSON corrupto | Regenera el base64 SIN saltos (`base64 -w 0`) y recrea el Secret; reinicia el pod |
| `invalid_grant: Invalid JWT` | Key de SA revocada/caducada o reloj del nodo desfasado | Crea una key nueva (`gcloud iam service-accounts keys create`) y actualiza el Secret |
| 429 / `Quota exceeded for quota metric 'Search All Resources requests'` | Superada la cuota de Cloud Asset (default 400/min) | Baja `searchAllResourcesPerMinuteQuota` en values, habilita `cloudquotas.googleapis.com` para rate limiting dinámico, o pide aumento de cuota |
| Pub/Sub kinds vacíos | `pubsub.googleapis.com` no habilitada en el proyecto host | Habilita la API o elimina esos kinds del mapping |
| La key no puede crearse: `Key creation is not allowed on this service account` | Org policy `iam.disableServiceAccountKeyCreation` activa | Usa Workload Identity (GKE) o pide excepción a la org policy |
| Pod CrashLoopBackOff al arrancar | Faltan claves `OCEAN__*` o `secret.name` no coincide | El Secret debe llamarse exactamente `ocean-gcp-credentials` en `port-idp` |
| 401/403 contra api.us.getport.io | Credenciales Port de otra región/organización | Confirma `port.baseUrl: https://api.us.getport.io` |

## Referencias

- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/gcp/ (overview de la integración GCP)
- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/gcp/installation/ (instalación: SA, roles, encodedADCConfiguration, Helm)
- https://github.com/port-labs/ocean/tree/main/integrations/gcp (código + `.port/spec.yaml` con las claves exactas)
- https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md (convención `OCEAN__*` del chart)
- https://github.com/port-labs/terraform-ocean-integration-factory (módulo Terraform oficial, ejemplo `gcp_cloud_run`)
- https://cloud.google.com/asset-inventory/docs/supported-asset-types (asset types soportados)
- https://cloud.google.com/asset-inventory/docs/quota (cuotas de Cloud Asset Inventory)
