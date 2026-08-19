# Integración Ocean: ServiceNow

> Integración **OFICIAL** del framework Ocean de Port. Verificada en el repositorio oficial
> [port-labs/ocean/integrations/servicenow](https://github.com/port-labs/ocean/tree/main/integrations/servicenow)
> y en la documentación oficial de Port.

La integración de ServiceNow sincroniza tablas de tu instancia ServiceNow hacia el catálogo de Port
usando la Table API. Cualquier tabla adicional puede añadirse al mapping.

## Qué sincroniza (kinds y blueprints por defecto)

| Kind (tabla ServiceNow) | Blueprint en Port | Contenido |
|---|---|---|
| `sys_user_group` | `servicenowGroup` | Grupos de usuarios (descripción, activo, creado por/en) |
| `sc_catalog` | `servicenowCatalog` | Catálogos de servicio |
| `incident` | `servicenowIncident` | Incidentes (número, estado, categoría, severidad, urgencia, prioridad, asignado a) |

Con `initializePortResources: true` los tres blueprints y el mapping por defecto se crean
automáticamente. La documentación oficial muestra además cómo añadir tablas extra (por ejemplo
`release_project`, `sn_vul_vulnerable_item` o cualquier tabla custom) editando el mapping.

## Prerrequisitos

- Cluster Kubernetes con ArgoCD y el app-of-apps de este repo sincronizando
  (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- Namespace destino `port-idp`.
- Credenciales de Port (Client ID / Client Secret). Región US: `https://api.us.getport.io`.
- Instancia ServiceNow accesible (ej. `https://dev12345.service-now.com`) y capacidad de crear un
  usuario de servicio o un endpoint OAuth.
- `kubectl` apuntando al cluster de laboratorio.

## Paso 1 — Obtener credenciales (permisos mínimos)

La integración soporta dos métodos de autenticación (spec oficial). Elige UNO:

### Opción A — Basic Auth (usuario/contraseña)

1. En ServiceNow: **User Administration → Users → New**.
2. Crea un usuario de servicio dedicado, p. ej. `svc-port-ocean` (marca *Web service access only*
   si tu versión lo permite, para impedir login por UI).
3. Permisos MÍNIMOS: la integración solo hace **lecturas vía Table API** sobre las tablas mapeadas.
   Concede acceso de lectura (ACL) a `incident`, `sys_user_group` y `sc_catalog`:
   - La vía más simple es asignar el rol `itil` (lectura de incidents) o, mejor,
     crear un rol custom de solo lectura con ACLs `read` sobre esas tres tablas.
   - No asignes `admin`. No se requiere ningún permiso de escritura para la sincronización.
4. Guarda usuario y contraseña.

### Opción B — OAuth 2.0 Client Credentials (recomendada por la doc oficial)

1. En ServiceNow: **System OAuth → Application Registry → New**.
2. Selecciona **Create an OAuth API endpoint for external clients**.
3. Nombre: `port-ocean`. En *Accessible from* selecciona **All application scopes**.
4. Guarda y copia el **Client ID** y el **Client Secret** autogenerados.
5. Asocia el grant de client credentials a un usuario de servicio con los mismos permisos de solo
   lectura de la Opción A (el token hereda los ACL de ese usuario).

Nota: crear el Application Registry requiere permisos de administración de OAuth
(rol de administrador del sistema); pídelo al equipo de plataforma ServiceNow si no lo tienes.
Para los *live events* opcionales (Paso avanzado), el usuario necesita además permisos para crear
Business Rules.

## Paso 2 — Crear el Secret manual

Convención del chart: cada `integration.secrets.<clave>` se inyecta como
`OCEAN__INTEGRATION__CONFIG__<CLAVE_EN_SNAKE_UPPER>`.

Con Basic Auth (Opción A):

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-servicenow-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__SERVICENOW_USERNAME='svc-port-ocean' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__SERVICENOW_PASSWORD='<PASSWORD>'
```

Con OAuth (Opción B), en su lugar:

```bash
kubectl create secret generic ocean-servicenow-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__SERVICENOW_CLIENT_ID='<SN_CLIENT_ID>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__SERVICENOW_CLIENT_SECRET='<SN_CLIENT_SECRET>'
```

Verifica:

```bash
kubectl get secret ocean-servicenow-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo: `deployment/install/ocean-servicenow/values.yaml` (rama `laboratory`).

```yaml
port:
  baseUrl: https://api.us.getport.io

# Crea blueprints y mapping por defecto automaticamente en el primer arranque
initializePortResources: true

# Resync programado (minutos)
scheduledResyncInterval: 120

# Credenciales fuera de git: Secret manual creado en el Paso 2
secret:
  create: false
  name: ocean-servicenow-credentials

resources:
  requests: {memory: "128Mi", cpu: "50m"}
  limits: {memory: "512Mi", cpu: "500m"}

integration:
  identifier: servicenow
  type: servicenow
  eventListener:
    type: POLLING
  config:
    # Claves de config NO sensibles segun spec oficial
    servicenowUrl: https://<tu-instancia>.service-now.com
    # Live events via Business Rules (requiere pod accesible desde ServiceNow); en laboratorio: false
    enableTablesLiveEventsWebhooks: false
```

Notas:
- NO se define `imageRegistry`, `image` ni `imagePullPolicy`: integración oficial, imagen por
  defecto de `ghcr.io/port-labs` resuelta por `integration.type`.
- Las credenciales (`servicenowUsername`/`servicenowPassword` o
  `servicenowClientId`/`servicenowClientSecret`) NO aparecen aquí: viajan en el Secret.
- Alternativa a `initializePortResources: true`: `false` + gestionar blueprints
  `servicenowGroup`, `servicenowCatalog`, `servicenowIncident` y el mapping con Terraform
  (ver `integrations/terraform/blueprints/` en este repo).

## Paso 4 — ApplicationSet

Archivo: `deployment/applicationsets/24-ocean-servicenow.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-servicenow
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
      name: 'port-ocean-servicenow-{{.name}}'
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
            releaseName: servicenow
            valueFiles:
              - $values/deployment/install/ocean-servicenow/values.yaml
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
git add deployment/applicationsets/24-ocean-servicenow.yaml deployment/install/ocean-servicenow/values.yaml
git commit -m "feat(ocean): add servicenow integration (official)"
git push origin laboratory
```

## Paso 5 — Verificación

```bash
kubectl get applications -n argocd | grep servicenow
kubectl get pods -n port-idp -l app.kubernetes.io/instance=servicenow
kubectl logs -n port-idp deployment/servicenow-port-ocean -f
```

En Port UI:
1. *Builder* → blueprints `servicenowGroup`, `servicenowCatalog`, `servicenowIncident`.
2. *Data sources* → integración `servicenow` en `Active` con último resync.
3. *Catalog* → incidents/grupos/catálogos poblados.

Smoke test de credenciales (Basic Auth):

```bash
curl -s -u 'svc-port-ocean:<PASSWORD>' \
  "https://<tu-instancia>.service-now.com/api/now/table/incident?sysparm_limit=1"
```

## Instalación alternativa (helm install directo)

Comando oficial de la pestaña Helm de la documentación de Port (Basic Auth):

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install servicenow port-labs/port-ocean \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=true \
  --set sendRawDataExamples=true \
  --set scheduledResyncInterval=120 \
  --set integration.identifier="servicenow" \
  --set integration.type="servicenow" \
  --set integration.eventListener.type="POLLING" \
  --set integration.config.servicenowUrl="https://<tu-instancia>.service-now.com" \
  --set integration.secrets.servicenowUsername="svc-port-ocean" \
  --set integration.secrets.servicenowPassword="<PASSWORD>"
```

Para OAuth sustituye las dos últimas líneas por:

```bash
  --set integration.secrets.servicenowClientId="<SN_CLIENT_ID>" \
  --set integration.secrets.servicenowClientSecret="<SN_CLIENT_SECRET>"
```

## Configuración avanzada

- **Tablas adicionales**: cualquier tabla de ServiceNow puede ingerirse añadiendo un kind al mapping
  (*Data sources* → `servicenow` → *Mapping*). Ejemplo para cambios:

  ```yaml
  - kind: change_request
    selector:
      query: 'true'
      apiQueryParams:
        sysparmDisplayValue: 'true'
        sysparmExcludeReferenceLink: 'false'
    port:
      entity:
        mappings:
          identifier: .sys_id
          title: .short_description
          blueprint: '"servicenowChange"'
  ```

  Recuerda crear antes el blueprint destino y dar permisos de lectura de esa tabla al usuario.
- **Filtrado con sysparmQuery**: el selector soporta `apiQueryParams.sysparmQuery` con la sintaxis
  de encoded queries de ServiceNow (ej. `active=true^priority=1`).
- **Live events (tiempo real)**: `integration.config.enableTablesLiveEventsWebhooks: true` hace que
  la integración cree Business Rules en ServiceNow que reenvían eventos al pod. Requiere:
  - `liveEvents.baseUrl` del chart apuntando a una URL pública del pod,
  - opcionalmente `integration.config.liveEventTables` (lista) para limitar tablas,
  - `integration.secrets.webhookSecret` (→ `OCEAN__INTEGRATION__CONFIG__WEBHOOK_SECRET` en el
    Secret) para autenticar las peticiones entrantes,
  - permisos de creación de Business Rules para el usuario de la integración.
  En el laboratorio actual (sin ingress público) se mantiene `false` y se depende del POLLING.
- **Intervalo de resync**: ajusta `scheduledResyncInterval` según volumen de incidents.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `401 Unauthorized` en logs | Usuario/contraseña incorrectos o cuenta bloqueada | Verifica credenciales; revisa *Web service access only* y estado del usuario |
| `403 Forbidden` al leer una tabla | ACL insuficiente para esa tabla | Concede rol/ACL de lectura sobre la tabla al usuario de servicio |
| Respuestas vacías (`result: []`) con 200 | ACL filtra filas silenciosamente | ServiceNow devuelve 200 con menos filas si el ACL restringe; valida con el smoke test del Paso 5 |
| Error OAuth `invalid_client` | Client ID/Secret mal copiados o registry inactivo | Regenera en System OAuth → Application Registry y actualiza el Secret |
| Pod `CreateContainerConfigError` | Secret ausente o claves mal nombradas | Claves exactas: `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__SERVICENOW_USERNAME`, `OCEAN__INTEGRATION__CONFIG__SERVICENOW_PASSWORD` |
| No se crean Business Rules | Falta permiso o `liveEvents.baseUrl` sin definir | Revisa permisos del usuario y la URL pública; en laboratorio deja live events desactivados |
| Blueprints no aparecen | `initializePortResources: false` | Ponlo a `true` o crea blueprints vía Terraform/UI |
| Resync lento / timeouts | Tablas enormes sin filtros | Añade `sysparmQuery` para filtrar (ej. solo incidents activos) y sube `resources` |

## Referencias

- Documentación oficial de la integración: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/incident-management/servicenow/
- Código y spec oficial (claves exactas de config/secrets): https://github.com/port-labs/ocean/tree/main/integrations/servicenow (archivo `.port/spec.yaml`)
- Mapping por defecto: https://github.com/port-labs/ocean/blob/main/integrations/servicenow/.port/resources/port-app-config.yaml
- Creación de credenciales en ServiceNow: https://developer.servicenow.com/dev.do#!/learn/learning-plans/washingtondc/servicenow_application_developer/app_store_learnv2_rest_washingtondc_creating_credentials
- OAuth client credentials en ServiceNow: https://www.servicenow.com/docs/bundle/zurich-platform-security/page/integrate/machine-identity/task/configure-an-oauth-client-credential-grant.html
- Helm charts de Port: https://port-labs.github.io/helm-charts
- Framework Ocean: https://ocean.port.io/
