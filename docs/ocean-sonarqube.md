# Integración Ocean: SonarQube

La integración oficial **SonarQube** de Port (`integration.type: sonarqube`, chart `port-ocean`) importa la calidad y seguridad de tu código al catálogo: proyectos, issues y análisis de tu cuenta de SonarQube (SonarCloud/SonarQube Cloud) o de tu instancia self-hosted (SonarQube Server).

**Kinds soportados (según la documentación oficial):**

- `projects_ga` → blueprint `sonarQubeProject`
- `issues` → blueprint `sonarQubeIssue`
- `saas_analysis` → blueprint `sonarQubeAnalysis` (solo SonarCloud)
- `onprem_analysis` → blueprint `sonarQubeAnalysis` (solo self-hosted)
- `portfolios` → blueprint `sonarQubePortfolio`

Con `initializePortResources: true` la integración crea automáticamente estos blueprints y su mapping default.

## Prerrequisitos

- Cluster Kubernetes registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente.
- App-of-apps activa: `deployment/bootstrap/root.yaml` sincronizando `deployment/applicationsets/*.yaml` desde la rama `laboratory` de `https://github.com/marcos-developer-j/port-ocean-integrations`.
- Namespace `port-idp`.
- Credenciales de Port (región **US**): en [app.getport.io](https://app.getport.io) → botón `...` → **Credentials** → `Client ID` y `Client Secret`. Rol **Admin** en Port.
- Cuenta en SonarCloud con acceso a la organización, o usuario en tu SonarQube self-hosted con visibilidad de los proyectos a sincronizar.
- Si es self-hosted: la URL de SonarQube debe ser alcanzable desde el pod de la integración (misma red/cluster o expuesta).

## Paso 1 — Obtener credenciales (user token)

La integración se autentica con un **token de usuario** (`integration.secrets.sonarApiToken`). El proceso difiere entre SonarCloud y self-hosted.

### Opción A: SonarCloud (SaaS)

1. Inicia sesión en [sonarcloud.io](https://sonarcloud.io).
2. Clic en tu avatar (arriba a la derecha) → **My Account**.
3. Pestaña **Security**.
4. En **Generate Tokens**: escribe un nombre (p. ej. `port-ocean-laboratory`) y pulsa **Generate**.
5. Copia el token (no se vuelve a mostrar).
6. Necesitarás además el **Organization Key** (`sonarOrganizationId`): visible en la página de tu organización en SonarCloud (**Administration → Organization settings**, campo "Organization Key", o en la URL `sonarcloud.io/organizations/<key>`).

El token hereda los permisos del usuario: usa un usuario con permiso **Browse** sobre los proyectos a sincronizar (miembro normal de la organización es suficiente para lectura).

### Opción B: SonarQube self-hosted (SonarQube Server)

1. Inicia sesión en tu instancia (`https://sonarqube.miempresa.com`).
2. Avatar → **My Account** → pestaña **Security**.
3. En **Generate Tokens**: nombre `port-ocean-laboratory`, tipo **User Token** (NO "Global Analysis Token" ni "Project Analysis Token": esos son solo para escáneres y no sirven para leer la Web API), define expiración y pulsa **Generate**.
4. Copia el token (`squ_...`).
5. El usuario dueño del token necesita como mínimo el permiso **Browse** sobre los proyectos que quieras ingestar (Administration → Security → Global Permissions / Project Permissions). Un usuario de solo lectura dedicado es la opción recomendada.

**Parámetros exactos de la integración** (claves oficiales del chart):

| Tipo | Clave | Descripción |
|---|---|---|
| `integration.config` | `sonarUrl` | URL de la instancia (self-hosted); para SaaS es `https://sonarcloud.io` |
| `integration.config` | `sonarOrganizationId` | Organization key de SonarCloud. NO requerido en instancias on-premise |
| `integration.config` | `sonarIsOnPremise` | `true` si la instancia es self-hosted, `false` para SonarCloud |
| `integration.secrets` | `sonarApiToken` | Token de usuario de SonarQube |

## Paso 2 — Crear el Secret manual

`sonarApiToken` se inyecta como `OCEAN__INTEGRATION__CONFIG__SONAR_API_TOKEN` (patrón `OCEAN__INTEGRATION__CONFIG__<CLAVE_EN_SNAKE_UPPER>`).

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-sonarqube-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__SONAR_API_TOKEN='<SONAR_TOKEN>'
```

Verifica:

```bash
kubectl get secret ocean-sonarqube-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo `deployment/install/ocean-sonarqube/values.yaml` (variante SonarCloud):

```yaml
# Values de la integración Ocean SonarQube para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-sonarqube-credentials"
# creado a mano en el namespace port-idp.
port:
  baseUrl: https://api.us.getport.io

# Integración OFICIAL: NO se define imageRegistry/image/imagePullPolicy,
# el chart usa ghcr.io/port-labs por defecto.

# true = crea blueprints y mapping default automáticamente.
# Alternativa: false + gestionar blueprints con Terraform (provider port-labs).
initializePortResources: true
scheduledResyncInterval: 120   # minutos; valor usado en la doc oficial, adecuado para calidad de código

# No crear el Secret desde el chart: usar el Secret manual del namespace.
# Debe contener: OCEAN__PORT__CLIENT_ID, OCEAN__PORT__CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__SONAR_API_TOKEN
secret:
  create: false
  name: ocean-sonarqube-credentials

resources:
  requests:
    memory: "128Mi"
    cpu: "50m"
  limits:
    memory: "512Mi"
    cpu: "500m"

integration:
  identifier: sonarqube
  type: sonarqube
  eventListener:
    type: POLLING
  config:
    sonarOrganizationId: "mi-organizacion"   # Organization key de SonarCloud
```

Variante self-hosted (SonarQube Server): sustituye el bloque `config` por:

```yaml
  config:
    sonarUrl: "https://sonarqube.miempresa.com"   # URL de la instancia
    sonarIsOnPremise: true
    # sonarOrganizationId NO es necesario en on-premise
```

## Paso 4 — ApplicationSet

Archivo `deployment/applicationsets/22-ocean-sonarqube.yaml`:

```yaml
# Despliega la integración Ocean SonarQube en cada cluster del entorno laboratory.
# Multi-source: chart oficial port-ocean + values desde este repo ($values).
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-sonarqube
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
      name: 'port-ocean-sonarqube-{{.name}}'
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
            releaseName: sonarqube
            valueFiles:
              - $values/deployment/install/ocean-sonarqube/values.yaml
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

> Haz commit de `deployment/install/ocean-sonarqube/values.yaml` y `deployment/applicationsets/22-ocean-sonarqube.yaml` y push a la rama `laboratory`. La app-of-apps detecta el nuevo ApplicationSet y ArgoCD despliega la integración sin intervención manual.

```bash
git checkout laboratory
git add deployment/install/ocean-sonarqube/values.yaml deployment/applicationsets/22-ocean-sonarqube.yaml
git commit -m "feat: integración Ocean SonarQube en laboratory"
git push origin laboratory
```

## Paso 5 — Verificación

```bash
kubectl get applications -n argocd | grep port-ocean-sonarqube

kubectl get pods -n port-idp -l app.kubernetes.io/instance=sonarqube

kubectl logs -n port-idp deploy/sonarqube-port-ocean -f
```

Qué buscar en los logs:

- Autenticación correcta contra Port (sin `401` hacia `api.us.getport.io`).
- Resync por kind: `projects_ga`, `issues`, `saas_analysis`/`onprem_analysis` con entidades "upserted".
- Sin `401/403` hacia la API de SonarQube (token o permisos Browse insuficientes) ni errores de organización no encontrada.

Qué ver en Port:

- **Builder**: blueprints `sonarQubeProject`, `sonarQubeIssue`, `sonarQubeAnalysis` (y `sonarQubePortfolio` si aplica).
- **Catalog**: tus proyectos de Sonar con métricas y sus issues asociadas.
- **Data sources**: integración `sonarqube` con último resync correcto y mapping editable.

## Instalación alternativa (helm install directo)

Comando oficial de la documentación de Port (SonarCloud):

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install my-sonarqube-integration port-labs/port-ocean \
  --set port.clientId="PORT_CLIENT_ID" \
  --set port.clientSecret="PORT_CLIENT_SECRET" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=true \
  --set scheduledResyncInterval=120 \
  --set integration.identifier="my-sonarqube-integration" \
  --set integration.type="sonarqube" \
  --set integration.eventListener.type="POLLING" \
  --set integration.secrets.sonarApiToken="MY_API_TOKEN" \
  --set integration.config.sonarOrganizationId="MY_ORG_KEY"
```

(Para self-hosted añade `--set integration.config.sonarUrl="https://sonarqube.miempresa.com"` y `--set integration.config.sonarIsOnPremise=true`, y omite `sonarOrganizationId`.)

## Configuración avanzada

- **Mapping (port-app-config)**: editable en Port (**Data sources → sonarqube → Mapping**). Puedes filtrar proyectos con JQ en `selector.query`, mapear métricas concretas del quality gate, o relacionar `sonarQubeProject` con tu blueprint `service` (por ejemplo, por nombre de repositorio). Recuerda que los kinds de análisis difieren por despliegue: `saas_analysis` (SonarCloud) vs `onprem_analysis` (self-hosted).
- **Live events (webhooks)**: para actualizaciones en tiempo real define `liveEvents.baseUrl` en los values, apuntando a una URL de la integración que SonarQube pueda alcanzar. Si SonarQube y la integración están en el mismo cluster, basta un Service interno ClusterIP (p. ej. `http://sonarqube-port-ocean.port-idp.svc.cluster.local:8000`); no hace falta exposición pública. Sin `liveEvents.baseUrl`, el modo POLLING con `scheduledResyncInterval` cubre la sincronización periódica.
- **Blueprints con Terraform**: alternativa a `initializePortResources: true` → ponlo a `false` y gestiona blueprints/mapping con el provider Terraform `port-labs` (patrón de `integrations/terraform/blueprints/` en este repo).
- **Certificados autofirmados** (self-hosted): si tu SonarQube usa TLS con CA propia, añade la CA a la configuración de la integración según el README del chart port-ocean.

## Troubleshooting

| Síntoma | Causa | Fix |
|---|---|---|
| Pod en `CreateContainerConfigError` | Secret `ocean-sonarqube-credentials` inexistente o clave mal escrita | Recrear con `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__INTEGRATION__CONFIG__SONAR_API_TOKEN` exactas |
| `401 Unauthorized` hacia SonarQube | Token inválido, revocado o de tipo incorrecto (Analysis Token en vez de User Token) | Regenerar un **User Token** y actualizar el Secret |
| Proyectos vacíos o incompletos | Usuario sin permiso **Browse** sobre los proyectos | Conceder Browse al usuario del token (o hacerlo miembro de la organización en SonarCloud) |
| Error de organización / sin datos en SonarCloud | `sonarOrganizationId` incorrecto | Usar el **Organization Key** exacto (visible en la URL de la organización) |
| Self-hosted sin datos de análisis | Falta `sonarIsOnPremise: true` o `sonarUrl` incorrecta (la integración consulta el kind SaaS) | Definir `sonarUrl` + `sonarIsOnPremise: true`; el kind correcto es `onprem_analysis` |
| Timeout / `connection refused` hacia `sonarUrl` | Instancia no alcanzable desde el pod (red, NetworkPolicy, DNS) | Probar conectividad desde el pod (`kubectl exec ... curl`) y ajustar red o URL |
| Error TLS con instancia self-hosted | Certificado autofirmado | Añadir la CA a la configuración de la integración (README del chart) |
| `401` hacia `api.us.getport.io` | Credenciales de Port erróneas o `port.baseUrl` de otra región | Revisar Client ID/Secret y `baseUrl: https://api.us.getport.io` |
| No hay updates en tiempo real | `liveEvents.baseUrl` sin definir o URL no alcanzable por SonarQube | Definir la URL (interna si comparten cluster) o confiar en el POLLING |
| Application `OutOfSync` sin desplegarse | Labels del cluster no coinciden con el selector del ApplicationSet | Verificar `project: port`, `environment: laboratory` y presencia de `cloud` |

## Referencias

- SonarQube — página principal de la integración: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/code-quality-security/sonarqube/ (redirige a https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/code-quality-security/sonarqube/)
- SonarQube — ejemplos de mapping: https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/code-quality-security/sonarqube/examples/
- Ocean — despliegue con Helm: https://ocean.port.io/deployment/helm/
- Ocean — despliegue con ArgoCD (patrón multi-source): https://ocean.port.io/deployment/argocd/
- Chart port-ocean (README): https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md
- SonarQube — generación de tokens (doc de Sonar): https://docs.sonarsource.com/sonarqube-server/latest/user-guide/managing-tokens/
