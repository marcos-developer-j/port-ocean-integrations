# Integración Ocean: Argo CD

La integración oficial **Argo CD** de Port (`integration.type: argocd`, chart `port-ocean`) sincroniza el estado de tus despliegues GitOps hacia el catálogo de Port: qué aplicaciones existen, en qué clusters/namespaces viven, su salud y su historial de despliegues.

**Kinds soportados (según la documentación oficial):** `cluster`, `namespace`, `project`, `application`, `deployment-history`, `kubernetes-resource`, `managed-resource`.

**Blueprints default que crea** (con `initializePortResources: true`): `argocdCluster`, `argocdNamespace`, `argocdProject`, `argocdApplication`, `argocdDeploymentHistory`, con relaciones automáticas entre aplicaciones, proyectos, clusters y namespaces.

> Nota: aquí Argo CD juega dos papeles distintos. Es la herramienta que DESPLIEGA la integración (nuestro modelo GitOps con ApplicationSets) y a la vez el SISTEMA OBSERVADO del que Ocean extrae datos. No los confundas: la integración consume la API del `argocd-server`.

## Prerrequisitos

- Cluster Kubernetes registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- App-of-apps activa: `deployment/bootstrap/root.yaml` sincronizando `deployment/applicationsets/*.yaml` desde la rama `laboratory` de `https://github.com/marcos-developer-j/port-ocean-integrations`.
- Namespace `port-idp`.
- Credenciales de Port (región **US**): en [app.getport.io](https://app.getport.io) → botón `...` → **Credentials** → `Client ID` y `Client Secret`. Rol **Admin** en Port.
- Acceso de administrador al Argo CD que se quiere sincronizar (para editar `argocd-cm` y `argocd-rbac-cm`).
- URL del `argocd-server` alcanzable desde el pod de la integración. Si la integración corre en el MISMO cluster que Argo CD, sirve la URL interna: `https://argocd-server.argocd.svc.cluster.local`.

## Paso 1 — Obtener credenciales (token de cuenta local con apiKey)

La integración se autentica con un **token de API de Argo CD** (`integration.secrets.token`). La doc oficial recomienda una cuenta local dedicada de solo lectura con capability `apiKey`.

### 1.1 Crear la cuenta local `port-ocean-user`

Edita el ConfigMap `argocd-cm` (namespace `argocd`):

```bash
kubectl patch configmap argocd-cm -n argocd --type merge -p '
data:
  accounts.port-ocean-user: apiKey, login
  accounts.port-ocean-user.enabled: "true"
'
```

- `apiKey`: permite generar tokens de API para la cuenta (imprescindible).
- `login`: opcional, permite iniciar sesión en la UI con esa cuenta (útil para generar el token desde la UI).

### 1.2 Dar permisos RBAC de solo lectura

Edita `argocd-rbac-cm` y añade una policy de solo lectura (líneas exactas de la doc oficial):

```bash
kubectl patch configmap argocd-rbac-cm -n argocd --type merge -p '
data:
  policy.csv: |
    p, role:read-only-role, applications, get, */*, allow
    p, role:read-only-role, clusters, get, *, allow
    p, role:read-only-role, projects, get, *, allow
    p, role:read-only-role, repositories, get, *, allow
    g, port-ocean-user, role:read-only-role
'
```

> Si `policy.csv` ya tiene contenido, AÑADE estas líneas en lugar de sobreescribirlo (usa `kubectl edit configmap argocd-rbac-cm -n argocd`). Estos permisos `get` sobre applications/clusters/projects/repositories son el mínimo que necesita la integración.

Reinicia el server para aplicar (según versión puede no ser necesario):

```bash
kubectl rollout restart deployment argocd-server -n argocd
```

### 1.3 Establecer contraseña (solo si vas a usar la UI)

```bash
# requiere argocd CLI logueado como admin
argocd account update-password --account port-ocean-user --new-password '<PASSWORD>'
```

### 1.4 Generar el token

**Opción CLI** (recomendada):

```bash
argocd login <ARGOCD_HOST> --username admin --password '<ADMIN_PASSWORD>' --grpc-web
argocd account generate-token --account port-ocean-user
```

**Opción UI**: inicia sesión como `port-ocean-user` → **Settings** → **Accounts** → `port-ocean-user` → sección **Tokens** → **Generate New**. (Ruta directa: `<serverURL>/settings/accounts/port-ocean-user`.)

Copia el token JWT resultante (`eyJhbGciOi...`). No caduca salvo que definas `--expires-in`; guárdalo solo en el Secret del paso 2.

**Parámetros exactos de la integración** (claves oficiales del chart):

| Tipo | Clave | Descripción |
|---|---|---|
| `integration.config` | `serverUrl` | URL del servidor Argo CD (API) |
| `integration.secrets` | `token` | Token de API de la cuenta `port-ocean-user` |

## Paso 2 — Crear el Secret manual

El secret `token` se inyecta como `OCEAN__INTEGRATION__CONFIG__TOKEN` (patrón `OCEAN__INTEGRATION__CONFIG__<CLAVE_EN_SNAKE_UPPER>`).

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-argocd-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__TOKEN='<ARGOCD_API_TOKEN>'
```

Verifica:

```bash
kubectl get secret ocean-argocd-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo `deployment/install/ocean-argocd/values.yaml`:

```yaml
# Values de la integración Ocean Argo CD para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-argocd-credentials"
# creado a mano en el namespace port-idp.
port:
  baseUrl: https://api.us.getport.io

# Integración OFICIAL: NO se define imageRegistry/image/imagePullPolicy,
# el chart usa ghcr.io/port-labs por defecto.

# true = crea blueprints y mapping default automáticamente.
# Alternativa: false + gestionar blueprints con Terraform (provider port-labs).
initializePortResources: true
scheduledResyncInterval: 60   # minutos; el estado de despliegues cambia a menudo, 1 h es razonable

# No crear el Secret desde el chart: usar el Secret manual del namespace.
# Debe contener: OCEAN__PORT__CLIENT_ID, OCEAN__PORT__CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__TOKEN
secret:
  create: false
  name: ocean-argocd-credentials

resources:
  requests:
    memory: "128Mi"
    cpu: "50m"
  limits:
    memory: "512Mi"
    cpu: "500m"

integration:
  identifier: argocd
  type: argocd
  eventListener:
    type: POLLING
  config:
    # Argo CD en el mismo cluster: usar el Service interno.
    # Si es externo: https://argocd.miempresa.com
    serverUrl: "https://argocd-server.argocd.svc.cluster.local"
```

## Paso 4 — ApplicationSet

Archivo `deployment/applicationsets/21-ocean-argocd.yaml`:

```yaml
# Despliega la integración Ocean Argo CD en cada cluster del entorno laboratory.
# Multi-source: chart oficial port-ocean + values desde este repo ($values).
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-argocd
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
      name: 'port-ocean-argocd-{{.name}}'
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
            releaseName: argocd
            valueFiles:
              - $values/deployment/install/ocean-argocd/values.yaml
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

> Haz commit de `deployment/install/ocean-argocd/values.yaml` y `deployment/applicationsets/21-ocean-argocd.yaml` y push a la rama `laboratory`. La app-of-apps recoge el nuevo ApplicationSet y ArgoCD despliega la integración automáticamente.

```bash
git checkout laboratory
git add deployment/install/ocean-argocd/values.yaml deployment/applicationsets/21-ocean-argocd.yaml
git commit -m "feat: integración Ocean Argo CD en laboratory"
git push origin laboratory
```

## Paso 5 — Verificación

```bash
kubectl get applications -n argocd | grep port-ocean-argocd

kubectl get pods -n port-idp -l app.kubernetes.io/instance=argocd

kubectl logs -n port-idp deploy/argocd-port-ocean -f
```

Qué buscar en los logs:

- Conexión correcta a `serverUrl` (sin errores de TLS ni `connection refused`).
- Resync por kind: `application`, `project`, `cluster`, `deployment-history`... con entidades "upserted".
- Sin `401` (token inválido) ni `permission denied` (RBAC insuficiente).

Qué ver en Port:

- **Builder**: blueprints `argocdApplication`, `argocdProject`, `argocdCluster`, `argocdNamespace`, `argocdDeploymentHistory`.
- **Catalog**: tus Applications de Argo CD como entidades, con salud y sync status, relacionadas con proyecto/cluster/namespace.
- **Data sources**: integración `argocd` con último resync correcto.

## Instalación alternativa (helm install directo)

Comando oficial (patrón de la doc de Port/Ocean):

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install argocd port-labs/port-ocean \
  --create-namespace --namespace port-idp \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=true \
  --set scheduledResyncInterval=60 \
  --set integration.identifier="argocd" \
  --set integration.type="argocd" \
  --set integration.eventListener.type="POLLING" \
  --set integration.config.serverUrl="<ARGOCD_SERVER_URL>" \
  --set integration.secrets.token="<ARGOCD_API_TOKEN>"
```

## Configuración avanzada

- **Mapping (port-app-config)**: editable en Port (**Data sources → argocd → Mapping**). El mapping default enlaza los 6+ kinds con sus blueprints; puedes añadir kinds como `kubernetes-resource` o `managed-resource` o relacionar `argocdApplication` con tu blueprint `service` usando JQ sobre labels/annotations de la Application.
- **Eventos en tiempo real (webhooks)**: la API REST de Argo CD NO soporta crear webhooks programáticamente, así que la configuración es manual mediante **Argo CD Notifications**: se añade la configuración de notificación al ConfigMap `argocd-notifications-cm` con triggers como `on-sync-operation-change`, `on-deployed` y `on-health-degraded` apuntando a la URL del endpoint de la integración (requiere exponerla vía `liveEvents.baseUrl` o un Service alcanzable desde el controller de notifications). Los pasos exactos y el manifiesto están en la doc oficial de la integración.
- **Entornos grandes (streaming)**: la API de Argo CD no pagina, lo que puede disparar la memoria del pod. Activa streaming con `--set streamingEnabled=true` (o `streamingEnabled: true` en values); afinable con las variables `OCEAN__STREAMING__CHUNK_SIZE` y `OCEAN__STREAMING__MAX_BUFFER_SIZE_MB`.
- **Blueprints con Terraform**: alternativa a `initializePortResources: true` → `false` y definir blueprints/mapping con el provider Terraform `port-labs`.

## Troubleshooting

| Síntoma | Causa | Fix |
|---|---|---|
| Pod en `CreateContainerConfigError` | Secret `ocean-argocd-credentials` inexistente o con claves mal escritas | Recrear el Secret con `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__TOKEN` |
| `401 Unauthorized` contra Argo CD | Token inválido, cuenta deshabilitada o sin capability `apiKey` | Verificar `accounts.port-ocean-user: apiKey, login` en `argocd-cm` y regenerar token |
| `account ... does not have apiKey capability` al generar token | Falta `apiKey` en la definición de la cuenta | Añadirlo en `argocd-cm` y reintentar |
| `permission denied` / listas vacías | RBAC sin los `get` necesarios | Revisar las líneas `p, role:read-only-role, ...` y el binding `g, port-ocean-user, role:read-only-role` en `argocd-rbac-cm` |
| Error TLS `certificate verify failed` hacia `serverUrl` | Certificado autofirmado del argocd-server | Usar la URL correcta del Service interno, o añadir la CA a la configuración de la integración (ver README del chart sobre CAs autofirmadas) |
| `connection refused` / timeout | `serverUrl` incorrecta o NetworkPolicy bloqueando `port-idp` → `argocd` | Probar `kubectl exec` con `wget`/`curl` desde el pod hacia la URL; ajustar URL o políticas de red |
| Pod OOMKilled en instancias grandes | API sin paginación, respuesta gigante en memoria | `streamingEnabled: true` y/o subir `resources.limits.memory` |
| `401` hacia `api.us.getport.io` | Credenciales de Port erróneas o región equivocada | Revisar Client ID/Secret y `port.baseUrl` |
| No llegan eventos en tiempo real | Webhooks no configurados (no hay API programática) | Configurar Argo CD Notifications manualmente o quedarse con POLLING |

## Referencias

- Argo CD — página principal de la integración: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/argocd/ (redirige a https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/argocd/)
- Argo CD — ejemplos de mapping: https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/argocd/example/
- Guía: visualizar runtime Kubernetes con Argo CD: https://docs.port.io/guides/all/visualize-service-argocd-runtime/
- Ocean — despliegue con Helm: https://ocean.port.io/deployment/helm/
- Ocean — despliegue con ArgoCD (patrón multi-source): https://ocean.port.io/deployment/argocd/
- Chart port-ocean (README): https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md
