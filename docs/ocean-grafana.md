# Integración Ocean: Grafana

## Estado actual (verificado)

**NO existe una integración Ocean oficial de Grafana.** Verificado el 2026-08-19 contra el listado
de integraciones del repositorio oficial
[github.com/port-labs/ocean/tree/main/integrations](https://github.com/port-labs/ocean/tree/main/integrations):
no hay carpeta `grafana` (sí existen `datadog`, `newrelic`, `dynatrace`, etc.) ni integración
comunitaria de Grafana publicada en ese repo. Tampoco aparece en el índice de integraciones nativas
de docs.port.io.

Las alternativas REALES y documentadas por Port son:

| Alternativa | Qué aporta | Esfuerzo |
|---|---|---|
| (a) Webhook genérico de Port | Ingesta de **alertas** de Grafana en tiempo real (ejemplo oficial en la doc de Port, blueprint `grafanaAlert`) | Bajo |
| (b) Ocean **custom** (`integration.type: custom`) | Sincronización periódica de **dashboards, folders, alert rules** vía la HTTP API de Grafana, sin escribir código | Medio |
| (c) Integración Ocean custom desarrollada (scaffold propio) | Control total (lógica Python propia), mismo patrón que las 4 custom de este repo: `jfrog`, `orca`, `veracode`, `github-projects` | Alto |

Este tutorial implementa la **(b)** con el patrón GitOps del repo, y documenta la (a) como
complemento para alertas en tiempo real.

## Qué sincroniza (blueprints propuestos — NO hay defaults oficiales)

La integración `custom` NO trae blueprints por defecto (su kind es dinámico: cada kind es una ruta
de endpoint). Debes crear los blueprints manualmente (UI, API o Terraform). Propuesta:

| Kind (endpoint Grafana) | Blueprint propuesto | Contenido |
|---|---|---|
| `/api/search` (con `type: dash-db`) | `grafanaDashboard` | Dashboards (uid, título, URL, carpeta, tags) |
| `/api/folders` | `grafanaFolder` | Carpetas de organización |
| Webhook (alternativa a) | `grafanaAlert` | Alertas firing/resolved (blueprint del ejemplo oficial de Port) |

## Prerrequisitos

- Cluster Kubernetes con ArgoCD y el app-of-apps del repo sincronizando
  (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- Namespace destino `port-idp`.
- Credenciales de Port (Client ID / Client Secret). Región US: `https://api.us.getport.io`.
- Instancia Grafana (OSS, Enterprise o Cloud) accesible desde el cluster, versión con
  service accounts (9.1+).
- `kubectl` apuntando al cluster de laboratorio.

## Paso 1 — Obtener credenciales (service account token, permisos mínimos)

1. En Grafana: **Administration → Users and access → Service accounts**.
2. **Add service account**. Nombre: `port-ocean`. Rol: **Viewer** (mínimo suficiente para
   `/api/search` y `/api/folders`; no uses Editor/Admin).
3. Entra en el service account → **Add service account token** → nombre `port-ocean-token` →
   define expiración según tu política → **Generate token**.
4. Copia el token (formato `glsa_XXXXXXXX...`). Solo se muestra una vez.
5. En Grafana Cloud el flujo es el mismo desde el stack de Grafana (no el portal de Cloud).

El token se usa como Bearer token: `Authorization: Bearer glsa_...`.

Nota de permisos: endpoints como `/api/datasources` requieren rol Admin; no los incluyas en el
mapping salvo que aceptes elevar el rol del service account.

## Paso 2 — Crear el Secret manual

La integración `custom` declara el secreto `apiToken` (spec oficial) cuando `authType` es
`bearer_token`. Convención de env var: `apiToken` → `OCEAN__INTEGRATION__CONFIG__API_TOKEN`.

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-grafana-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__API_TOKEN='glsa_XXXXXXXX'
```

Verifica:

```bash
kubectl get secret ocean-grafana-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo: `deployment/install/ocean-grafana/values.yaml` (rama `laboratory`).

```yaml
port:
  baseUrl: https://api.us.getport.io

# La integracion custom NO trae blueprints por defecto: se crean manualmente (ver Paso 5),
# por eso aqui se deja en false.
initializePortResources: false

# Resync programado (minutos)
scheduledResyncInterval: 120

# Credenciales fuera de git: Secret manual creado en el Paso 2
secret:
  create: false
  name: ocean-grafana-credentials

resources:
  requests: {memory: "128Mi", cpu: "50m"}
  limits: {memory: "512Mi", cpu: "500m"}

integration:
  identifier: grafana
  # Tipo oficial "custom" (Ocean custom integration, en el repo oficial port-labs/ocean)
  type: custom
  eventListener:
    type: POLLING
  config:
    # Claves de config NO sensibles segun spec oficial de la integracion custom
    baseUrl: https://<tu-grafana>.example.com
    authType: bearer_token
    # /api/search de Grafana pagina con ?page=N&limit=M
    paginationType: page
    paginationParam: page
    sizeParam: limit
    pageSize: "100"
    startPage: "1"
    timeout: "30"
    verifySsl: true
```

Notas:
- `integration.type: custom` es una integración publicada en el repo oficial de Ocean, así que NO
  se define `imageRegistry`/`image`/`imagePullPolicy` (imagen por defecto de `ghcr.io/port-labs`).
- El token (`apiToken`) NO va en values: viaja en el Secret del Paso 2.
- Claves de config disponibles en la spec oficial de `custom` (por si las necesitas):
  `baseUrl`, `authType` (`none|bearer_token|basic|api_key|custom`), `apiKeyHeader`,
  `paginationType` (`none|offset|page|cursor|next_link|header_link`), `pageSize`,
  `paginationParam`, `sizeParam`, `startPage`, `cursorPath`, `hasMorePath`, `lastPagePath`,
  `nextLinkPath`, `headerLinkRel`, `timeout`, `verifySsl`, `maxConcurrentRequests`,
  `customAuthRequest`, `customAuthRequestTemplate`. Secretos: `apiToken`, `username`, `password`,
  `apiKey`.

## Paso 4 — ApplicationSet

Archivo: `deployment/applicationsets/25-ocean-grafana.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-grafana
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
      name: 'port-ocean-grafana-{{.name}}'
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
            releaseName: grafana
            valueFiles:
              - $values/deployment/install/ocean-grafana/values.yaml
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

Commit y push:

```bash
git checkout laboratory
git add deployment/applicationsets/25-ocean-grafana.yaml deployment/install/ocean-grafana/values.yaml
git commit -m "feat(ocean): add grafana via ocean custom integration"
git push origin laboratory
```

## Paso 5 — Verificación (y creación de blueprints + mapping)

### 5.1 Crear blueprints (manual, la custom no trae defaults)

En Port UI (*Builder* → *New blueprint* → *Edit JSON*), crea por ejemplo:

```json
{
  "identifier": "grafanaDashboard",
  "title": "Grafana Dashboard",
  "icon": "Grafana",
  "schema": {
    "properties": {
      "url": {"type": "string", "format": "url", "title": "URL"},
      "folder": {"type": "string", "title": "Folder"},
      "tags": {"type": "array", "title": "Tags"}
    }
  },
  "relations": {}
}
```

y `grafanaFolder` con `title` y `url`.

### 5.2 Configurar el mapping

*Data sources* → integración `grafana` → *Mapping* (formato oficial de la integración custom:
el `kind` es la ruta del endpoint y `data_path` apunta al array de items):

```yaml
resources:
  - kind: /api/search
    selector:
      query: 'true'
      # /api/search devuelve un array JSON en la raiz
      data_path: '.'
      query_params:
        type: dash-db
    port:
      entity:
        mappings:
          identifier: .uid
          title: .title
          blueprint: '"grafanaDashboard"'
          properties:
            url: .url
            folder: .folderTitle
            tags: .tags

  - kind: /api/folders
    selector:
      query: 'true'
      data_path: '.'
    port:
      entity:
        mappings:
          identifier: .uid
          title: .title
          blueprint: '"grafanaFolder"'
```

### 5.3 Verificar despliegue

```bash
kubectl get applications -n argocd | grep grafana
kubectl get pods -n port-idp -l app.kubernetes.io/instance=grafana
kubectl logs -n port-idp deployment/grafana-port-ocean -f
```

Smoke test del token:

```bash
curl -s -H "Authorization: Bearer glsa_XXXXXXXX" \
  "https://<tu-grafana>.example.com/api/search?type=dash-db&limit=1"
```

En Port: *Data sources* → `grafana` en `Active` y entities `grafanaDashboard` en el catálogo.

## Instalación alternativa (helm install directo)

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install grafana port-labs/port-ocean \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=false \
  --set scheduledResyncInterval=120 \
  --set integration.identifier="grafana" \
  --set integration.type="custom" \
  --set integration.eventListener.type="POLLING" \
  --set integration.config.baseUrl="https://<tu-grafana>.example.com" \
  --set integration.config.authType="bearer_token" \
  --set integration.secrets.apiToken="glsa_XXXXXXXX"
```

## Configuración avanzada

### Alternativa (a): alertas en tiempo real con el Webhook genérico de Port (ejemplo oficial)

Port documenta un ejemplo oficial "Ingest Grafana alerts" con:
- Blueprint `grafanaAlert` (propiedades: `status` enum firing/resolved, `labels`, `description`,
  `summary`, `createdAt`, `resolvedAt`, `values`, `generatorURL`, `fingerprint`, `silenceURL`,
  `runbookURL`).
- Webhook mapper `grafana_alert_mapper` (identifier de entity:
  `.item.labels.alertname + "-" + .item.fingerprint`, saneado con `gsub`).

Pasos en Grafana: **Alerting → Contact points → Add contact point** → tipo **Webhook** → URL del
webhook generada por Port → guardar y añadir el contact point a la **Notification policy**.
Es complementario a la integración custom: la custom inventaría dashboards/folders por polling y
el webhook ingiere alertas al momento.

### Alternativa (c): integración Ocean custom desarrollada

Si necesitas lógica que la integración `custom` no cubre (joins entre endpoints, enriquecimiento,
APIs no paginables de forma estándar), haz scaffold de una integración propia con el CLI de Ocean
(`ocean new`), igual que las 4 custom de este repo (`integrations/jfrog`, `integrations/orca`,
`integrations/veracode`, `integrations/github-projects`): handlers `@ocean.on_resync("kind")` en
Python, spec.yaml propio, imagen propia (aquí SÍ tendrías que publicar imagen y setear
`imageRegistry`/`image` en values, como hacen esas 4).

### Otros ajustes

- **Alert rules provisionadas**: puedes añadir el kind `/api/v1/provisioning/alert-rules`
  (requiere permisos de alerting en el service account) con `data_path: '.'`.
- **Multi-org Grafana**: usa un values + ApplicationSet por organización, con
  `integration.identifier` distinto (ej. `grafana-org2`).
- **Rate limiting**: `integration.config.maxConcurrentRequests` (default "10").

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `401 Unauthorized` contra Grafana | Token expirado/revocado o mal copiado | Regenera el service account token y actualiza el Secret |
| `403 Forbidden` en un endpoint | Rol Viewer insuficiente (ej. `/api/datasources`) | Quita ese kind del mapping o eleva el rol conscientemente |
| Resync sin entities y sin errores | `data_path` incorrecto | `/api/search` y `/api/folders` devuelven array raíz: usa `data_path: '.'` |
| Solo llegan 100 dashboards | Paginación no configurada | Revisa `paginationType: page`, `paginationParam: page`, `sizeParam: limit` en values |
| Pod `CreateContainerConfigError` | Secret ausente o clave mal nombrada | Claves exactas: `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__API_TOKEN` |
| Error de certificado TLS | Grafana con cert interno | `verifySsl: false` solo en laboratorio; en producción añade la CA al trust |
| Entities sin blueprint (`blueprint not found`) | Blueprints no creados (custom no trae defaults) | Crea `grafanaDashboard`/`grafanaFolder` antes del primer resync (Paso 5.1) |
| Alertas del webhook no llegan | Contact point mal configurado o policy sin el contact point | Revisa Contact points y Notification policies en Grafana; prueba con *Test* |

## Referencias

- Listado oficial de integraciones Ocean (verificación de inexistencia): https://github.com/port-labs/ocean/tree/main/integrations
- Ocean custom integration (overview): https://docs.port.io/build-your-software-catalog/custom-integration/ocean-custom-integration/overview/
- Spec oficial de la integración custom (claves exactas): https://github.com/port-labs/ocean/blob/main/integrations/custom/.port/spec.yaml
- Ejemplos de webhook de Port (incluye "Ingest Grafana alerts"): https://docs.port.io/build-your-software-catalog/custom-integration/webhook/examples/
- Ejemplo oficial webhook Grafana (blueprint `grafanaAlert`): https://docs.port.io/build-your-software-catalog/custom-integration/webhook/examples/grafana
- Grafana service accounts: https://grafana.com/docs/grafana/latest/administration/service-accounts/
- Grafana HTTP API (search/folders): https://grafana.com/docs/grafana/latest/developers/http_api/
- Helm charts de Port: https://port-labs.github.io/helm-charts
