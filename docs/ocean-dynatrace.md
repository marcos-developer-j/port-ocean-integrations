# Integración Ocean: Dynatrace

> Integración **OFICIAL** del framework Ocean de Port. Verificada en el repositorio oficial
> [port-labs/ocean/integrations/dynatrace](https://github.com/port-labs/ocean/tree/main/integrations/dynatrace)
> y en la documentación oficial de Port.

La integración de Dynatrace sincroniza recursos de observabilidad y APM hacia el catálogo de Port.

## Qué sincroniza (kinds y blueprints por defecto)

| Kind (Dynatrace) | Blueprint en Port | Contenido |
|---|---|---|
| `entity` | `dynatraceEntity` | Entidades monitorizadas. Por defecto solo tipos `APPLICATION` y `SERVICE` (configurable vía selector `entityTypes`) |
| `problem` | `dynatraceProblem` | Problemas detectados por Davis AI (severidad, estado, entidades impactadas, causa raíz) |
| `slo` | `dynatraceSlo` | SLOs con target, error budget, estado de evaluación y relación con entidades |
| `team` | `dynatraceTeam` | Equipos de ownership (Settings 2.0), con contactos y enlaces |

Con `initializePortResources: true` los cuatro blueprints y el mapping por defecto se crean automáticamente en Port en el primer arranque.

## Prerrequisitos

- Cluster Kubernetes con ArgoCD y el app-of-apps de este repo ya sincronizando (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente (cualquier valor).
- Namespace destino `port-idp` (lo crea el ApplicationSet con `CreateNamespace=true`).
- Credenciales de Port (Client ID / Client Secret): Port UI → icono `...` (arriba derecha) → *Credentials*. Región US: API `https://api.us.getport.io`.
- Un entorno Dynatrace (SaaS o Managed) y permisos para crear Access Tokens.
- `kubectl` apuntando al cluster de laboratorio.

## Paso 1 — Obtener credenciales (permisos mínimos)

### 1.1 URL del entorno (`dynatraceHostUrl`)

Formato exacto requerido por la integración:

```
https://<environment-id>.live.dynatrace.com
```

Ejemplo: `https://abc123.live.dynatrace.com`.

Importante: cuando navegas por la UI de Dynatrace la URL contiene `apps`
(`https://abc123.apps.dynatrace.com`); la integración necesita la URL de **API**, que usa `live`.
El `environment-id` es el mismo en ambas.

### 1.2 API Token (`dynatraceApiKey`)

1. Entra en tu entorno Dynatrace y abre la app de tokens clásicos:
   `https://<environment-id>.apps.dynatrace.com/ui/apps/dynatrace.classic.tokens/ui/access-tokens`
   (o busca "Access Tokens" en el buscador de la UI).
2. Pulsa **Generate new token**.
3. Nombre sugerido: `port-ocean-integration`.
4. Asigna SOLO estos scopes (mínimos, según la doc oficial de Port):

   | Scope (UI) | Scope (API) | Para qué |
   |---|---|---|
   | Data export | `DataExport` | Health-check previo a la ingesta |
   | Read entities | `entities.read` | kind `entity` |
   | Read problems | `problems.read` | kind `problem` |
   | Read SLO | `slo.read` | kind `slo` |
   | Read settings | `settings.read` | kind `team` (ownership vía Settings 2.0) |

5. Pulsa **Generate token** y copia el valor (formato `dt0c01.XXXX.YYYY`). Solo se muestra una vez.

No asignes scopes de escritura: la integración es un exporter de solo lectura.

## Paso 2 — Crear el Secret manual

Las credenciales NUNCA van al repo git. Se crea un Secret manual en `port-idp` y el chart lo
consume con `secret.create: false` + `secret.name`.

Convención de claves del chart `port-ocean`: cada `integration.secrets.<clave>` se inyecta como
variable de entorno `OCEAN__INTEGRATION__CONFIG__<CLAVE_EN_SNAKE_UPPER>`
(`dynatraceApiKey` → `OCEAN__INTEGRATION__CONFIG__DYNATRACE_API_KEY`).

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-dynatrace-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__DYNATRACE_API_KEY='dt0c01.XXXX.YYYY'
```

Verifica:

```bash
kubectl get secret ocean-dynatrace-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo: `deployment/install/ocean-dynatrace/values.yaml` (rama `laboratory`).

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
  name: ocean-dynatrace-credentials

resources:
  requests: {memory: "128Mi", cpu: "50m"}
  limits: {memory: "512Mi", cpu: "500m"}

integration:
  identifier: dynatrace
  type: dynatrace
  eventListener:
    type: POLLING
  config:
    # Unica clave de config NO sensible segun spec oficial
    dynatraceHostUrl: https://<environment-id>.live.dynatrace.com
```

Notas:
- NO se define `imageRegistry`, `image` ni `imagePullPolicy`: al ser integración oficial, el chart
  resuelve la imagen por defecto desde `ghcr.io/port-labs` a partir de `integration.type`.
- La clave sensible `dynatraceApiKey` NO aparece aquí: viaja por el Secret del Paso 2.
- Alternativa a `initializePortResources: true`: ponerlo a `false` y gestionar los blueprints
  `dynatraceEntity`, `dynatraceProblem`, `dynatraceSlo`, `dynatraceTeam` y el mapping con Terraform
  (provider `port-labs/port-labs`, ver `integrations/terraform/blueprints/` en este repo).

## Paso 4 — ApplicationSet

Archivo: `deployment/applicationsets/23-ocean-dynatrace.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-dynatrace
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
      name: 'port-ocean-dynatrace-{{.name}}'
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
            releaseName: dynatrace
            valueFiles:
              - $values/deployment/install/ocean-dynatrace/values.yaml
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

Commit y push a la rama de entorno:

```bash
git checkout laboratory
git add deployment/applicationsets/23-ocean-dynatrace.yaml deployment/install/ocean-dynatrace/values.yaml
git commit -m "feat(ocean): add dynatrace integration (official)"
git push origin laboratory
```

El app-of-apps (`deployment/bootstrap/root.yaml`) detectará el nuevo ApplicationSet y ArgoCD creará
la Application `port-ocean-dynatrace-<cluster>`.

## Paso 5 — Verificación

```bash
# Application en ArgoCD
kubectl get applications -n argocd | grep dynatrace

# Pod de la integracion
kubectl get pods -n port-idp -l app.kubernetes.io/instance=dynatrace

# Logs: debe autenticar contra Port y empezar el resync de entity/problem/slo/team
kubectl logs -n port-idp deployment/dynatrace-port-ocean -f
```

En Port UI:
1. *Builder* → deben existir los blueprints `dynatraceEntity`, `dynatraceProblem`, `dynatraceSlo`, `dynatraceTeam`.
2. *Data sources* → integración `dynatrace` en estado `Active` con timestamp del último resync.
3. *Catalog* → entities pobladas tras el primer resync completo.

Smoke test de credenciales (opcional, fuera del cluster):

```bash
curl -s -H "Authorization: Api-Token dt0c01.XXXX.YYYY" \
  "https://<environment-id>.live.dynatrace.com/api/v2/entities?entitySelector=type(%22SERVICE%22)&pageSize=1"
```

## Instalación alternativa (helm install directo)

Comando oficial de la pestaña Helm de la documentación de Port (sin GitOps):

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install dynatrace port-labs/port-ocean \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=true \
  --set sendRawDataExamples=true \
  --set scheduledResyncInterval=120 \
  --set integration.identifier="dynatrace" \
  --set integration.type="dynatrace" \
  --set integration.eventListener.type="POLLING" \
  --set integration.secrets.dynatraceApiKey="dt0c01.XXXX.YYYY" \
  --set integration.config.dynatraceHostUrl="https://<environment-id>.live.dynatrace.com"
```

Nota: con `--set integration.secrets.*` el chart crea él mismo el Secret (equivale a
`secret.create: true`). En este repo usamos el patrón de Secret manual para no exponer credenciales
ni en git ni en el historial de shell de CI.

## Configuración avanzada

- **Más tipos de entidad**: edita el mapping en Port (*Data sources* → `dynatrace` → *Mapping*) y
  amplía el selector del kind `entity`:

  ```yaml
  - kind: entity
    selector:
      query: "true"
      entityTypes: ["APPLICATION", "SERVICE", "HOST", "KUBERNETES_CLUSTER", "SYNTHETIC_TEST"]
      entityFields: "firstSeenTms,lastSeenTms,tags"
  ```

- **SLOs con entidades relacionadas**: el kind `slo` soporta `attachRelatedEntities: true`
  (activado por defecto en el mapping oficial) para poblar la relación `entities`.
- **Filtrado con JQ**: cualquier selector admite `query` con expresión JQ, por ejemplo
  `query: '.severityLevel == "AVAILABILITY"'` en `problem`.
- **Intervalo de resync**: ajusta `scheduledResyncInterval` (minutos). Para entornos grandes de
  Dynatrace sube memoria/CPU en `resources`.
- **Event listener**: este repo usa `POLLING`. La integración también soporta listener `KAFKA` y
  webhooks en tiempo real si el pod es accesible desde Internet (`liveEvents.baseUrl`), no aplicable
  al laboratorio actual.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| Pod en `CrashLoopBackOff` y log `401 Unauthorized` contra Dynatrace | Token inválido/expirado o sin scopes | Regenera el token con los 5 scopes del Paso 1 y actualiza el Secret; reinicia el pod |
| `403 Forbidden` en `/api/v2/settings/objects` | Falta scope `settings.read` (kind `team`) | Añade el scope o elimina el kind `team` del mapping |
| Log `Connection error` / DNS | `dynatraceHostUrl` con formato `apps` en vez de `live`, o typo | Usa `https://<environment-id>.live.dynatrace.com` |
| Pod arranca pero no aparecen blueprints | `initializePortResources: false` sin blueprints previos | Ponlo a `true` o crea blueprints/mapping vía Terraform o UI |
| Application `OutOfSync` sobre el Secret | El chart intenta crear el Secret | Confirma `secret.create: false` y `secret.name: ocean-dynatrace-credentials` en values |
| `CreateContainerConfigError` | El Secret no existe en `port-idp` o falta una clave | Revisa el Paso 2; las claves deben llamarse exactamente `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__DYNATRACE_API_KEY` |
| Resync lento / OOMKilled | Muchos `entityTypes` o entorno grande | Sube `resources.limits.memory`, reduce tipos de entidad o el `entityFields` |
| Entities no borradas al desaparecer en Dynatrace | Comportamiento del mapping | El mapping oficial usa `deleteDependentEntities: true` y `createMissingRelatedEntities: true`; revisa que no lo hayas sobreescrito |

## Referencias

- Documentación oficial de la integración: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/apm-alerting/dynatrace/
- Código y spec oficial (claves exactas de config/secrets): https://github.com/port-labs/ocean/tree/main/integrations/dynatrace (archivo `.port/spec.yaml`)
- Mapping por defecto: https://github.com/port-labs/ocean/blob/main/integrations/dynatrace/.port/resources/port-app-config.yaml
- Autenticación Dynatrace (creación de tokens): https://docs.dynatrace.com/docs/dynatrace-api/basics/dynatrace-api-authentication
- Helm charts de Port: https://port-labs.github.io/helm-charts
- Framework Ocean: https://ocean.port.io/
