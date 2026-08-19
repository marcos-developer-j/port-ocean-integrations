# Integración Ocean: Azure (multi-suscripción con Service Principal)

> Integración **OFICIAL** del framework Ocean de Port. Verificada en el repositorio oficial
> [port-labs/ocean/integrations/azure](https://github.com/port-labs/ocean/tree/main/integrations/azure)
> (`.port/spec.yaml`) y en la documentación oficial de Port
> ([Azure](https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/azure/)).

La integración de Azure (`integration.type: azure`) exporta recursos de Azure Resource Manager al catálogo de Port. Port ofrece dos "sabores" documentados:

- **Azure REST Exporter** (esta integración `azure`): usa la API REST de ARM; con despliegue Terraform añade eventos en tiempo real vía Event Grid.
- **Azure Resource Graph / Incremental Sync** (integración más reciente, en beta): usa **Azure Resource Graph** para sincronizar a gran escala (hasta miles de suscripciones con un único despliegue), sin Event Grid. La integración clásica `azure` NO usa Resource Graph; si tu escala lo requiere, evalúa la variante Resource Graph en la doc oficial.

Este documento cubre la integración estándar `azure` vía chart `port-ocean` (Helm + ArgoCD).

## Qué sincroniza (kinds y blueprints por defecto)

Kinds por defecto según el `spec.yaml` oficial:

| Kind | Blueprint en Port | Contenido |
|---|---|---|
| `subscription` | `azureSubscription` | Suscripciones visibles para el Service Principal |
| `resourceGroup` (`Microsoft.Resources/resourceGroups`) | `azureResourceGroup` | Resource Groups |
| `containerApp` (`Microsoft.App/containerApps`) | `azureCloudResource` | Container Apps |
| `aks` (`Microsoft.ContainerService/managedClusters`) | `azureCloudResource` | Clusters AKS |
| `storageAccount` (`Microsoft.Storage/storageAccounts`) | `azureCloudResource` | Storage Accounts |
| `storageContainer` | `azureCloudResource` | Contenedores blob |
| `virtualMachine` (`Microsoft.Compute/virtualMachines`) | `azureCloudResource` | Máquinas virtuales |

Con `initializePortResources: true` los blueprints y el mapping por defecto se crean automáticamente. Puedes añadir al mapping cualquier tipo de recurso Azure con API `List` a nivel de suscripción.

## Qué necesitas

- Cluster Kubernetes con ArgoCD y el app-of-apps de este repo ya sincronizando (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- Namespace destino `port-idp` (lo crea el ApplicationSet con `CreateNamespace=true`).
- Credenciales de Port (Client ID / Client Secret). Región US: `https://api.us.getport.io`.
- Tenant de Microsoft Entra ID (Azure AD) con permisos para:
  - Crear un App Registration / Service Principal (`Application Administrator` o similar).
  - Asignar roles RBAC (`Owner` o `User Access Administrator`) en las suscripciones o en el Management Group.
- Azure CLI (`az`) autenticada: `az login` y `az account show` funcionando.
- `kubectl` apuntando al cluster de laboratorio.

## Arquitectura multi-suscripción

Mecanismo: un único **Service Principal** (App Registration) con el rol **Reader** asignado en CADA suscripción a sincronizar. La integración enumera todas las suscripciones visibles para el SP y exporta los recursos de cada una. La forma más escalable de dar visibilidad es asignar Reader **una sola vez a nivel de Management Group**: la asignación se hereda a todas las suscripciones actuales y futuras bajo ese grupo.

```
                 Microsoft Entra ID (tenant)
                 ┌─────────────────────────────┐
                 │ App Registration            │
                 │ "port-ocean-azure"          │
                 │ clientId/clientSecret/      │
                 │ tenantId                    │
                 └──────────────┬──────────────┘
                                │ RBAC: Reader (heredado)
                     ┌──────────▼──────────┐
                     │ Management Group    │
                     │ (p.ej. root "mg")   │
                     └──┬────────┬───────┬─┘
                        │        │       │
        ┌───────────────▼─┐ ┌────▼────┐ ┌▼──────────────┐
        │ Suscripción A   │ │ Susc. B │ │ Suscripción C │
        │ (Reader hered.) │ │         │ │               │
        └─────────────────┘ └─────────┘ └───────────────┘
                 ▲
                 │ ARM REST API (List por suscripción)
        ┌────────┴────────┐
        │ K8s (port-idp)  │
        │ pod ocean-azure │
        └─────────────────┘
```

Credenciales que consume la integración (las TRES marcadas `sensitive: true` en el spec oficial):

- `azureClientId` — Application (client) ID del App Registration.
- `azureClientSecret` — Client secret del App Registration.
- `azureTenantId` — Directory (tenant) ID.

## Paso 1 — Preparar credenciales en Azure

### 1.1 Crear el App Registration / Service Principal

Opción rápida (crea SP + asignación de rol en un paso, a nivel de Management Group):

```bash
TENANT_ID=$(az account show --query tenantId -o tsv)
MG_ID=<ID_DEL_MANAGEMENT_GROUP>   # p.ej. el root MG: az account management-group list

az ad sp create-for-rbac \
  --name port-ocean-azure \
  --role Reader \
  --scopes /providers/Microsoft.Management/managementGroups/${MG_ID}
```

Salida (guárdala; el secret solo se muestra una vez):

```json
{
  "appId":    "<AZURE_CLIENT_ID>",
  "password": "<AZURE_CLIENT_SECRET>",
  "tenant":   "<AZURE_TENANT_ID>"
}
```

Opción manual (App Registration separado del role assignment):

```bash
# 1) App registration
APP_ID=$(az ad app create --display-name port-ocean-azure --query appId -o tsv)

# 2) Service principal asociado
az ad sp create --id ${APP_ID}

# 3) Secret (2 años; ajusta la rotación a tu política)
az ad app credential reset --id ${APP_ID} --years 2 --query password -o tsv
```

## Paso 2 — Configurar multi-suscripción (asignaciones RBAC)

### Opción A (recomendada) — Reader a nivel de Management Group

Una única asignación cubre todas las suscripciones del grupo (y las que se añadan después):

```bash
az role assignment create \
  --assignee ${APP_ID} \
  --role "Reader" \
  --scope /providers/Microsoft.Management/managementGroups/${MG_ID}
```

> Para el Management Group raíz del tenant el ID suele coincidir con el Tenant ID. Necesitas permisos elevados sobre el MG (`Owner`/`User Access Administrator` en ese scope).

### Opción B — Reader suscripción por suscripción

Si no puedes tocar Management Groups, repite por cada suscripción:

```bash
for SUB in <SUB_ID_1> <SUB_ID_2> <SUB_ID_3>; do
  az role assignment create \
    --assignee ${APP_ID} \
    --role "Reader" \
    --scope /subscriptions/${SUB}
done
```

Verifica qué ve el SP:

```bash
az role assignment list --assignee ${APP_ID} --all -o table
```

> Mínimo privilegio: `Reader` es lo recomendado por la doc oficial para consultar todo. Si quieres restringir, la doc de Port lista como permisos de acción: `Microsoft.Resources/subscriptions/read`, `Microsoft.Resources/subscriptions/resourceGroups/read`, `Microsoft.Resources/subscriptions/resources/read` y `*/read` (rol custom).

## Paso 3 — Crear el Secret en Kubernetes

Mapeo config sensible → variable de entorno (`OCEAN__INTEGRATION__CONFIG__<SNAKE_UPPER>`):

| Clave del spec (camelCase) | Variable de entorno |
|---|---|
| `azureClientId` | `OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_ID` |
| `azureClientSecret` | `OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_SECRET` |
| `azureTenantId` | `OCEAN__INTEGRATION__CONFIG__AZURE_TENANT_ID` |

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-azure-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_ID='<AZURE_CLIENT_ID>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_SECRET='<AZURE_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__AZURE_TENANT_ID='<AZURE_TENANT_ID>'
```

Verifica:

```bash
kubectl get secret ocean-azure-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 4 — Values del chart

Archivo: `deployment/install/ocean-azure/values.yaml` (rama `laboratory`).

```yaml
# Values de la integración Ocean Azure (oficial) para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-azure-credentials"
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
# OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_ID,
# OCEAN__INTEGRATION__CONFIG__AZURE_CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__AZURE_TENANT_ID
secret:
  create: false
  name: ocean-azure-credentials

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "500m"

integration:
  identifier: azure
  type: azure
  eventListener:
    type: POLLING
  # Las tres claves del spec oficial (azureClientId, azureClientSecret,
  # azureTenantId) son sensitive: van TODAS en el Secret manual.
  # No hay claves de config no sensibles obligatorias.
```

## Paso 5 — ApplicationSet

Archivo: `deployment/applicationsets/31-ocean-azure.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-azure
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
      name: 'port-ocean-azure-{{.name}}'
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
            releaseName: azure
            valueFiles:
              - $values/deployment/install/ocean-azure/values.yaml
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
kubectl get pods -n port-idp -l app.kubernetes.io/instance=azure
kubectl logs -n port-idp -l app.kubernetes.io/instance=azure -f --tail=200
```

Qué buscar en los logs:

- Autenticación OK contra Entra ID (sin `ClientAuthenticationError` / `invalid_client`).
- Enumeración de suscripciones: deben aparecer TODAS las suscripciones esperadas (prueba real del multi-subscription; si solo ves una, revisa RBAC).
- Resync por kind (`subscription`, `resourceGroup`, `aks`, `storageAccount`, `virtualMachine`, `containerApp`, `storageContainer`) con contadores de upserts.
- `Resync finished successfully`.

En Port:

1. **Builder** → blueprints `azureSubscription`, `azureResourceGroup`, `azureCloudResource` creados.
2. **Catalog** → entidades de varias suscripciones (comprueba la propiedad subscription en recursos de distintas suscripciones).
3. **Data sources** → integración `azure` en verde con timestamp de último resync.

## Instalación alternativa

### Terraform con Event Grid (tiempo real) — Azure Container App

Según el spec oficial: módulo `port-labs/integration-factory/ocean`, ejemplo `azure_container_app_azure_integration`, versión `>= 0.0.25`. Despliega la integración como Azure Container App y crea la suscripción de Event Grid (topic de sistema `Microsoft.Resources.Subscriptions`) para eventos en tiempo real:

```hcl
module "ocean_azure" {
  source  = "port-labs/integration-factory/ocean//examples/azure_container_app_azure_integration"
  version = ">=0.0.25"

  port = {
    client_id     = var.port_client_id
    client_secret = var.port_client_secret
    base_url      = "https://api.us.getport.io"
  }

  integration = {
    type       = "azure"
    identifier = "azure"
  }

  # Variables extra del ejemplo (según spec oficial):
  # Nota: Azure solo permite UN topic Microsoft.Resources.Subscriptions por cuenta.
  event_grid_system_topic_name = ""   # vacío = crear uno nuevo

  included_event_types = [
    "Microsoft.Resources/subscriptions/resourceGroups",
    "Microsoft.App/containerApp",
    "Microsoft.Storage/storageAccounts",
    "Microsoft.Compute/virtualMachines",
    "Microsoft.ContainerService/managedClusters",
    "Microsoft.Network/loadBalancers",
    "Microsoft.Network/virtualNetworks",
  ]

  action_permissions_list = [
    "Microsoft.Resources/subscriptions/read",
    "Microsoft.Resources/subscriptions/resourceGroups/read",
    "Microsoft.Resources/subscriptions/resources/read",
    "*/read",
  ]
}
```

### Azure Resource Graph / Incremental Sync (gran escala)

Para tenants con muchas suscripciones (hasta ~5000 por consulta), Port ofrece la integración basada en **Azure Resource Graph** (beta), que sincroniza de forma centralizada con un solo despliegue y encaja de forma natural con el Reader a nivel de Management Group. Ver la doc oficial (`.../cloud-providers/azure/azure-resource-graph/` en la sección Context Lake / native integrations) antes de adoptarla; sus parámetros de config difieren de los de esta integración (verificar en la doc oficial).

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `AADSTS7000215: Invalid client secret` | Secret caducado o mal copiado (ojo: copiar el *Value*, no el *Secret ID*) | `az ad app credential reset --id $APP_ID` y recrear el Secret de K8s |
| `AADSTS700016: Application ... not found` | `azureClientId` incorrecto o SP no creado en el tenant indicado | Verifica `az ad sp show --id $APP_ID` y que `azureTenantId` sea el tenant correcto |
| Solo aparece una suscripción | Falta el role assignment Reader en las demás (o el MG no contiene esas suscripciones) | `az role assignment list --assignee $APP_ID --all -o table`; asigna a nivel MG (Paso 2A) |
| `AuthorizationFailed ... does not have authorization to perform action 'Microsoft.Resources/subscriptions/read'` | Rol insuficiente o scope equivocado | Asigna `Reader` en el scope correcto; espera unos minutos a la propagación RBAC |
| 429 `TooManyRequests` de ARM | Throttling de ARM con muchos recursos/suscripciones | Sube `scheduledResyncInterval`, reduce kinds del mapping, o migra a la variante Resource Graph |
| Kinds custom no devuelven nada | El tipo no tiene API `List` a nivel de suscripción o el apiVersion del mapping es inválido | Revisa el mapping en Port (Data sources → azure → Mapping) y el apiVersion soportado del recurso |
| Pod CrashLoopBackOff al arrancar | Faltan claves `OCEAN__*` en el Secret o `secret.name` no coincide | `kubectl describe pod -n port-idp ...`; el Secret debe llamarse `ocean-azure-credentials` |
| 401/403 contra api.us.getport.io | Credenciales Port de otra región/organización | Confirma `port.baseUrl: https://api.us.getport.io` |

## Referencias

- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/azure/ (overview de la integración Azure)
- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/azure/installation/ (instalación; incluye sección *Multiple subscriptions setup*)
- https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/cloud-providers/azure/azure-resource-graph/ (variante Resource Graph, beta)
- https://github.com/port-labs/ocean/tree/main/integrations/azure (código + `.port/spec.yaml` con las claves exactas)
- https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md (convención `OCEAN__*` del chart)
- https://github.com/port-labs/terraform-ocean-integration-factory (módulo Terraform oficial)
- https://learn.microsoft.com/en-us/cli/azure/azure-cli-sp-tutorial-1 (creación de Service Principals con az CLI)
