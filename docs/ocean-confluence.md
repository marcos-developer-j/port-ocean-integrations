# Integración Ocean: Confluence

## Estado actual (verificado)

**NO existe una integración Ocean oficial de Confluence.** Verificado el 2026-08-19 contra el
listado de integraciones del repositorio oficial
[github.com/port-labs/ocean/tree/main/integrations](https://github.com/port-labs/ocean/tree/main/integrations):
existen integraciones de Atlassian para `jira` y `jira-server`, pero NO hay carpeta `confluence` ni
integración comunitaria de Confluence en ese repo. Tampoco figura en el índice de integraciones
nativas de docs.port.io (Port sí documenta conectar Confluence como **MCP connector** para consultas
de IA, pero eso no ingesta datos al catálogo).

Alternativas REALES:

| Alternativa | Qué aporta | Esfuerzo |
|---|---|---|
| (a) Webhook genérico de Port | Ingesta de eventos puntuales (creación/edición de páginas) si expones un intermediario que reciba webhooks de Confluence y los reenvíe al webhook de Port | Bajo-Medio |
| (b) Ocean **custom** (`integration.type: custom`) | Sincronización periódica de **spaces y pages** vía la REST API v2 de Confluence Cloud, sin escribir código | Medio |
| (c) Integración Ocean custom desarrollada (scaffold propio) | Control total: jerarquía space → folder → page y conversión de contenido a markdown (ver sección "Visión") — mismo patrón que las 4 custom del repo (`jfrog`, `orca`, `veracode`, `github-projects`) | Alto |
| (d) MCP connector de Port | Consultas bajo demanda desde Port AI, sin persistir datos en el catálogo | Bajo |

Este tutorial implementa la **(b)** con el patrón GitOps del repo y desarrolla la **(c)** como
arquitectura propuesta en la sección de Visión.

## Qué sincroniza (blueprints propuestos — NO hay defaults oficiales)

La integración `custom` no trae blueprints por defecto (kinds dinámicos = rutas de endpoint).
Propuesta mínima:

| Kind (endpoint Confluence Cloud v2) | Blueprint propuesto | Contenido |
|---|---|---|
| `/wiki/api/v2/spaces` | `confluenceSpace` | Espacios (key, tipo, estado, homepage) |
| `/wiki/api/v2/pages` | `confluencePage` | Páginas (título, estado, autor, fechas, relación a space) |

## Prerrequisitos

- Cluster Kubernetes con ArgoCD y el app-of-apps del repo sincronizando
  (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- Namespace destino `port-idp`.
- Credenciales de Port (Client ID / Client Secret). Región US: `https://api.us.getport.io`.
- Sitio Confluence **Cloud** (`https://<tu-sitio>.atlassian.net`) y una cuenta con acceso de
  lectura a los espacios a sincronizar. (Para Confluence Data Center/Server cambia la base de la
  API a `/rest/api` y la autenticación a PAT; este tutorial cubre Cloud.)
- `kubectl` apuntando al cluster de laboratorio.

## Paso 1 — Obtener credenciales (permisos mínimos)

Confluence Cloud usa **Basic Auth con email + API token** para la REST API:

1. Con la cuenta de servicio (recomendado: una cuenta dedicada, no personal), entra en
   https://id.atlassian.com/manage-profile/security/api-tokens
2. **Create API token** (si tu organización lo permite, usa *API token with scopes* y concede solo
   scopes de lectura de Confluence, p. ej. lectura de contenido/espacios).
3. Nombre: `port-ocean`. Copia el token: solo se muestra una vez.
4. Permisos mínimos en Confluence: la cuenta solo necesita **permiso de visualización (view)** en
   los espacios a sincronizar. No concedas permisos de edición ni de administración de espacio.
   La API devuelve únicamente lo que la cuenta puede ver, así que el acceso de la cuenta define el
   alcance de la sincronización.

Credenciales resultantes: `username = email de la cuenta`, `password = API token`.

## Paso 2 — Crear el Secret manual

La spec oficial de la integración `custom` declara `username` y `password` para `authType: basic`
(`password` es sensible; guardamos ambos en el Secret para no dejar el email en git).
Convención: `username` → `OCEAN__INTEGRATION__CONFIG__USERNAME`,
`password` → `OCEAN__INTEGRATION__CONFIG__PASSWORD`.

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-confluence-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__USERNAME='svc-port@tuempresa.com' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__PASSWORD='<ATLASSIAN_API_TOKEN>'
```

Verifica:

```bash
kubectl get secret ocean-confluence-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo: `deployment/install/ocean-confluence/values.yaml` (rama `laboratory`).

```yaml
port:
  baseUrl: https://api.us.getport.io

# La integracion custom NO trae blueprints por defecto: se crean manualmente (ver Paso 5)
initializePortResources: false

# Resync programado (minutos)
scheduledResyncInterval: 120

# Credenciales fuera de git: Secret manual creado en el Paso 2
secret:
  create: false
  name: ocean-confluence-credentials

resources:
  requests: {memory: "128Mi", cpu: "50m"}
  limits: {memory: "512Mi", cpu: "500m"}

integration:
  identifier: confluence
  # Tipo oficial "custom" (Ocean custom integration, repo oficial port-labs/ocean)
  type: custom
  eventListener:
    type: POLLING
  config:
    # Claves de config NO sensibles segun spec oficial de la integracion custom
    baseUrl: https://<tu-sitio>.atlassian.net
    authType: basic
    # La API v2 de Confluence Cloud pagina por cursor y expone la siguiente pagina
    # en la cabecera HTTP "Link" con rel="next"
    paginationType: header_link
    headerLinkRel: next
    pageSize: "100"
    sizeParam: limit
    timeout: "30"
    verifySsl: true
```

Notas:
- `integration.type: custom` está en el repo oficial de Ocean: NO se define
  `imageRegistry`/`image`/`imagePullPolicy` (imagen por defecto de `ghcr.io/port-labs`).
- `username`/`password` NO van en values: viajan en el Secret del Paso 2.
- Si tu tenant devuelve la siguiente página solo en el cuerpo (`_links.next`), usa en su lugar
  `paginationType: next_link` + `nextLinkPath: _links.next`.

## Paso 4 — ApplicationSet

Archivo: `deployment/applicationsets/26-ocean-confluence.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-confluence
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
      name: 'port-ocean-confluence-{{.name}}'
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
            releaseName: confluence
            valueFiles:
              - $values/deployment/install/ocean-confluence/values.yaml
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
git add deployment/applicationsets/26-ocean-confluence.yaml deployment/install/ocean-confluence/values.yaml
git commit -m "feat(ocean): add confluence via ocean custom integration"
git push origin laboratory
```

## Paso 5 — Verificación (y creación de blueprints + mapping)

### 5.1 Crear blueprints (manual)

`confluenceSpace`:

```json
{
  "identifier": "confluenceSpace",
  "title": "Confluence Space",
  "icon": "Confluence",
  "schema": {
    "properties": {
      "key": {"type": "string", "title": "Key"},
      "type": {"type": "string", "title": "Type"},
      "status": {"type": "string", "title": "Status"},
      "url": {"type": "string", "format": "url", "title": "URL"}
    }
  },
  "relations": {}
}
```

`confluencePage` (con relación al space y property markdown para la Visión):

```json
{
  "identifier": "confluencePage",
  "title": "Confluence Page",
  "icon": "Confluence",
  "schema": {
    "properties": {
      "status": {"type": "string", "title": "Status"},
      "createdAt": {"type": "string", "format": "date-time", "title": "Created At"},
      "url": {"type": "string", "format": "url", "title": "URL"},
      "content": {"type": "string", "format": "markdown", "title": "Content"}
    }
  },
  "relations": {
    "space": {"target": "confluenceSpace", "many": false, "required": false, "title": "Space"}
  }
}
```

### 5.2 Configurar el mapping

*Data sources* → integración `confluence` → *Mapping* (formato oficial de la custom: `kind` =
ruta de endpoint, `data_path` = JQ hacia el array; Confluence v2 devuelve `{"results": [...]}`):

```yaml
resources:
  - kind: /wiki/api/v2/spaces
    selector:
      query: 'true'
      data_path: '.results'
    port:
      entity:
        mappings:
          identifier: .id | tostring
          title: .name
          blueprint: '"confluenceSpace"'
          properties:
            key: .key
            type: .type
            status: .status

  - kind: /wiki/api/v2/pages
    selector:
      query: 'true'
      data_path: '.results'
      query_params:
        status: current
    port:
      entity:
        mappings:
          identifier: .id | tostring
          title: .title
          blueprint: '"confluencePage"'
          properties:
            status: .status
            createdAt: .createdAt
          relations:
            space: .spaceId | tostring
```

### 5.3 Verificar despliegue

```bash
kubectl get applications -n argocd | grep confluence
kubectl get pods -n port-idp -l app.kubernetes.io/instance=confluence
kubectl logs -n port-idp deployment/confluence-port-ocean -f
```

Smoke test de credenciales:

```bash
curl -s -u 'svc-port@tuempresa.com:<ATLASSIAN_API_TOKEN>' \
  "https://<tu-sitio>.atlassian.net/wiki/api/v2/spaces?limit=1"
```

En Port: *Data sources* → `confluence` en `Active`; entities `confluenceSpace` y `confluencePage`
en el catálogo.

## Instalación alternativa (helm install directo)

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install confluence port-labs/port-ocean \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=false \
  --set scheduledResyncInterval=120 \
  --set integration.identifier="confluence" \
  --set integration.type="custom" \
  --set integration.eventListener.type="POLLING" \
  --set integration.config.baseUrl="https://<tu-sitio>.atlassian.net" \
  --set integration.config.authType="basic" \
  --set integration.secrets.username="svc-port@tuempresa.com" \
  --set integration.secrets.password="<ATLASSIAN_API_TOKEN>"
```

## Visión: Confluence como fuente de documentación del catálogo

Objetivo: que la documentación viva de Confluence se refleje en Port, de forma que cada entity del
catálogo tenga su documentación navegable (property `markdown`) sin salir del portal. Esto es un
**desarrollo custom** (alternativa c): ni la integración oficial existe ni la integración `custom`
genérica convierte contenido; hay que escribir una integración Ocean propia, igual que se hizo en
este repo con `jfrog`, `orca`, `veracode` y `github-projects`.

### Jerarquía a sincronizar: space → folder → page

La REST API v2 de Confluence Cloud modela la jerarquía completa:

- Spaces: `GET /wiki/api/v2/spaces`
- Folders (contenedores de organización dentro de un space): `GET /wiki/api/v2/folders/{id}` y
  navegación de hijos directos con `GET /wiki/api/v2/folders/{id}/direct-children`
- Pages: `GET /wiki/api/v2/pages`, con `parentId`/`spaceId` para reconstruir el árbol y
  `GET /wiki/api/v2/pages/{id}?body-format=storage` para el contenido

### Conversión de páginas a markdown (READMEs de entities)

Pipeline propuesto dentro del handler de resync del kind `page`:

1. Pedir la página con `body-format=storage` (XHTML del *storage format* de Confluence) o
   `body-format=export_view` (HTML renderizado). El *storage format* es más estable para conversión.
2. Convertir HTML/XHTML → markdown en la propia integración (librerías Python:
   `markdownify` o `html2text`; para macros complejas, limpiar antes con `BeautifulSoup`).
3. Volcar el resultado en una property de tipo `string` con `format: markdown` del blueprint
   (`content` en el ejemplo del Paso 5.1). Port renderiza esa property como pestaña de
   documentación en la página de la entity.
4. Opcional: mapear una página "README" de Confluence a la property markdown de OTRA entity ya
   existente (ej. un `service`), buscando por convención (label de Confluence `port-service:<id>`
   o título normalizado) y emitiendo la entity destino desde el handler.

### Arquitectura de la integración custom

- **Scaffold**: `ocean new confluence` (CLI del framework Ocean). Estructura resultante igual a la
  de `integrations/jfrog` de este repo: `main.py`, `client.py`, `.port/spec.yaml`,
  `.port/resources/blueprints.json` y `port-app-config.yaml`, `Dockerfile`.
- **Kinds** en `spec.yaml`: `space`, `folder`, `page`.
- **Configuración** (`spec.yaml`): `confluenceHostUrl` (url, required), `spaceKeys` (array,
  opcional, para limitar espacios), `convertContentToMarkdown` (boolean, default true);
  secretos: `confluenceUserEmail`, `confluenceApiToken` (sensitive).
- **Client** (`client.py`): httpx async contra `/wiki/api/v2`, Basic Auth, paginación por cursor
  (seguir `Link: rel="next"`), rate limiting (respetar 429 + `Retry-After`).
- **Handlers** (`main.py`):
  - `@ocean.on_resync("space")` → lista spaces.
  - `@ocean.on_resync("folder")` → recorre hijos de cada space filtrando type `folder`.
  - `@ocean.on_resync("page")` → lista pages con body storage; convierte a markdown; emite raw
    results con el campo extra `__markdown` para el mapping.
- **Blueprints sugeridos** (`blueprints.json`): `confluenceSpace`, `confluenceFolder`
  (relación `space`), `confluencePage` (relaciones `space` y `parentFolder`; properties `url`,
  `status`, `labels`, y `content` con `"format": "markdown"`).
- **Mapping por defecto** (`port-app-config.yaml`), extracto del kind `page`:

  ```yaml
  - kind: page
    selector:
      query: 'true'
    port:
      entity:
        mappings:
          identifier: .id | tostring
          title: .title
          blueprint: '"confluencePage"'
          properties:
            url: ._links.webui
            status: .status
            content: .__markdown
          relations:
            space: .spaceId | tostring
            parentFolder: .parentId | tostring
  ```

- **Despliegue en este repo**: al ser imagen propia (no publicada por Port), en values SÍ se
  definiría `imageRegistry`/`image` apuntando a tu registry, exactamente como hacen las 4
  integraciones custom existentes; el resto del patrón (Secret manual, ApplicationSet, POLLING)
  es idéntico.

Limitaciones a tener en cuenta: macros de Confluence (diagramas, includes) no tienen equivalente
markdown y deben degradarse a enlaces o eliminarse; adjuntos e imágenes requieren URLs absolutas
autenticadas (o re-subida a otro almacenamiento); páginas muy grandes pueden superar límites de
tamaño de property, conviene truncar con enlace "ver en Confluence".

## Configuración avanzada

- **Filtrar por espacio**: en el kind `/wiki/api/v2/pages` añade
  `query_params: {space-id: "<id>"}` o filtra con JQ en `query`
  (ej. `query: '.spaceId == "123456"'`).
- **Solo páginas actuales**: `query_params: {status: current}` (ya incluido en el ejemplo).
- **Webhook (alternativa a)**: Confluence Cloud no envía webhooks arbitrarios a URLs externas sin
  una app (Connect/Forge). El patrón real es una app Forge o un middleware (p. ej. Lambda) suscrito
  a eventos `page_created`/`page_updated` que reenvíe el payload al webhook genérico de Port con un
  mapping JQ. Útil para frescura, complementa al POLLING.
- **MCP connector (alternativa d)**: si solo necesitas que Port AI consulte Confluence bajo
  demanda (sin catálogo), configura Confluence como MCP connector remoto en Port
  (*AI registry → MCP connectors*), con OAuth. No sustituye a la ingesta.
- **Data Center/Server**: cambia endpoints a `/rest/api/space`, `/rest/api/content` y usa PAT
  (`authType: bearer_token` + `apiToken`).

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `401 Unauthorized` | Email o API token incorrectos, o token revocado | Regenera el token en id.atlassian.com y actualiza el Secret |
| `403 Forbidden` en un space | La cuenta de servicio no tiene permiso de view en ese space | Concede acceso de lectura al space o exclúyelo del alcance |
| Resultados vacíos con 200 | La API solo devuelve lo visible para la cuenta | Revisa permisos de espacio; valida con el smoke test del Paso 5.3 |
| Solo llega la primera página de resultados | Paginación mal configurada | `paginationType: header_link` + `headerLinkRel: next`; alternativa `next_link` + `nextLinkPath: _links.next` |
| `data_path` sin matches | Ruta JQ incorrecta | Confluence v2 envuelve en `results`: usa `data_path: '.results'` |
| Pod `CreateContainerConfigError` | Secret ausente o claves mal nombradas | Claves exactas: `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__USERNAME`, `OCEAN__INTEGRATION__CONFIG__PASSWORD` |
| `429 Too Many Requests` | Rate limiting de Atlassian Cloud | Baja `maxConcurrentRequests`, sube `scheduledResyncInterval` |
| Entities sin blueprint | Blueprints no creados (custom sin defaults) | Crea `confluenceSpace`/`confluencePage` antes del primer resync |
| Property markdown vacía | La integración `custom` genérica no convierte contenido | La conversión HTML→markdown requiere la integración desarrollada (sección Visión) |

## Referencias

- Listado oficial de integraciones Ocean (verificación de inexistencia): https://github.com/port-labs/ocean/tree/main/integrations
- Ocean custom integration (overview): https://docs.port.io/build-your-software-catalog/custom-integration/ocean-custom-integration/overview/
- Spec oficial de la integración custom (claves exactas): https://github.com/port-labs/ocean/blob/main/integrations/custom/.port/spec.yaml
- Custom integrations en Port (webhook/API): https://docs.port.io/build-your-software-catalog/custom-integration/
- MCP connectors de Port (Confluence bajo demanda): https://docs.port.io/agent-management/ai-registry/mcp-connectors/
- Confluence Cloud REST API v2: https://developer.atlassian.com/cloud/confluence/rest/v2/intro/
- API tokens de Atlassian: https://id.atlassian.com/manage-profile/security/api-tokens
- Framework Ocean (desarrollo de integraciones): https://ocean.port.io/
- Helm charts de Port: https://port-labs.github.io/helm-charts
