# Integración Ocean: GitHub

La integración **GitHub (Ocean)** (`integration.type: github-ocean`) es la integración oficial de nueva generación de Port para GitHub, construida sobre el framework Ocean y desplegable en modo self-hosted con el chart `port-ocean`. Sincroniza recursos de GitHub hacia el catálogo de software de Port.

**Kinds soportados (según la documentación oficial):** `organization`, `repository`, `pull-request`, `issue`, `file`, `folder`, `user`, `team`, `workflow`, `workflow-run`, `branch`, `environment`, `deployment`, `deployment-status`, `release`, `tag`, `dependabot-alert`, `code-scanning-alert`, `secret-scanning-alert`.

**Blueprints default que crea** (con `initializePortResources: true`): `githubOrganization`, `githubRepository`, `githubPullRequest`, `githubIssue`, `githubUser`, `githubTeam`, `githubWorkflow`, `githubWorkflowRun`, `githubBranch`, `githubRepoEnvironment`, `githubDeployment`, `githubDeploymentStatus`, `githubRelease`, `githubTag`, `githubDependabotAlert` y los blueprints de alertas de code scanning y secret scanning.

> **Importante — no confundir con el "GitHub app exporter" clásico.** Port tiene dos integraciones de GitHub:
>
> 1. **GitHub App (hosted by Port)**: la app clásica que se instala desde el marketplace de GitHub y corre en la infraestructura de Port. Es la opción más rápida si no necesitas self-hosted (no requiere cluster ni credenciales propias). Documentada en la sección "GitHub" de docs.port.io.
> 2. **GitHub (Ocean), self-hosted**: la que documenta este tutorial. Corre en TU cluster con el chart `port-ocean`, se autentica con un PAT o una GitHub App propia, y te da control total de permisos, red y ciclo de vida. Es la que encaja con nuestro modelo GitOps.
>
> Si vienes del exporter clásico y ya tienes blueprints/datos de GitHub en Port, revisa la guía de migración oficial y usa `createPortResourcesOrigin: Empty` en los values para NO crear los blueprints default y evitar conflictos (ver "Configuración avanzada").

## Prerrequisitos

- Cluster Kubernetes registrado en ArgoCD con las labels `project: port`, `environment: laboratory` y la label `cloud` presente (cluster generator del ApplicationSet).
- App-of-apps activa: `deployment/bootstrap/root.yaml` sincronizando `deployment/applicationsets/*.yaml` desde la rama `laboratory` del repo `https://github.com/marcos-developer-j/port-ocean-integrations`.
- Namespace `port-idp` (lo crea el ApplicationSet `00-namespace.yaml` o la syncOption `CreateNamespace=true`).
- Credenciales de Port (organización en región **US**): en [app.getport.io](https://app.getport.io), clic en el botón `...` (arriba a la derecha) → **Credentials** → copia `Client ID` y `Client Secret`. Tu usuario de Port debe tener rol **Admin**.
- Cuenta de GitHub con permisos para crear tokens de acceso (o para crear una GitHub App en la organización).
- `kubectl` con acceso al cluster destino.

## Paso 1 — Obtener credenciales

La integración soporta dos métodos de autenticación self-hosted: **Personal Access Token (PAT)** (fine-grained o classic) y **GitHub App propia**. Para un laboratorio, el PAT es lo más sencillo.

### Opción A: Personal Access Token (recomendada para empezar)

**PAT classic** (necesario si quieres sincronizar VARIAS organizaciones; los fine-grained no soportan multi-organización según la doc oficial):

1. En GitHub, clic en tu avatar (arriba a la derecha) → **Settings**.
2. Menú lateral, al fondo: **Developer settings**.
3. **Personal access tokens** → **Tokens (classic)** → **Generate new token** → **Generate new token (classic)**.
4. `Note`: por ejemplo `port-ocean-github-laboratory`. `Expiration`: define una caducidad y anota la fecha de rotación.
5. Scopes mínimos para la sincronización de lectura:
   - `repo` (lectura de repositorios, PRs, issues, workflows, releases, etc.; imprescindible si hay repos privados).
   - `read:org` (lectura de miembros, teams y metadatos de la organización).
   - `admin:org_hook` SOLO si más adelante activas live events con creación automática de webhooks de organización (la doc oficial indica que el PAT debe poder crear organization webhooks). En modo POLLING no lo necesitas.
6. **Generate token** y copia el valor (`ghp_...`). No podrás volver a verlo.
7. Si tu organización usa SSO (SAML), pulsa **Configure SSO** junto al token y autorízalo para la organización.

**PAT fine-grained** (más granular; solo una organización como "Resource owner"):

1. **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. `Resource owner`: selecciona tu organización. `Repository access`: **All repositories** (o la selección que quieras sincronizar).
3. Concede permisos de **solo lectura (Read-only)** sobre los recursos que vayas a sincronizar (repositorios: Contents, Metadata, Pull requests, Issues, Actions, Deployments, Environments, Dependabot alerts, Code/Secret scanning alerts; organización: Members). La doc oficial no publica una tabla cerrada de permisos fine-grained: concede lectura solo de los kinds que uses y amplía si ves errores 403 en los logs.
4. Genera el token (`github_pat_...`) y cópialo. Si la organización requiere aprobación de fine-grained PATs, un owner deberá aprobarlo.

### Opción B: GitHub App propia (recomendada por Port para producción)

Según la doc oficial, la GitHub App ofrece mayor cuota de rate limit (resyncs más rápidos) y control fino de permisos, pero solo soporta UNA organización a la vez (se indica con `githubOrganization`).

1. En GitHub: **Settings** de la organización → **Developer settings** → **GitHub Apps** → **New GitHub App**.
2. Nombre (p. ej. `port-ocean-laboratory`), Homepage URL cualquiera. Desactiva Webhook si vas a usar solo POLLING.
3. Permisos: concede **Read-only** sobre los recursos a sincronizar (mismos ámbitos que en el PAT fine-grained).
4. Crea la App, apunta el **App ID**, y en la sección **Private keys** genera y descarga la clave privada `.pem`.
5. Instala la App en la organización (**Install App**) sobre todos los repos o una selección.
6. La clave privada se pasa al chart **codificada en base64**:
   ```bash
   base64 -w0 port-ocean-laboratory.private-key.pem
   ```

**Parámetros exactos según el método** (claves oficiales del chart):

| Método | integration.config.* | integration.secrets.* |
|---|---|---|
| PAT | `githubOrganization` (u `organizations` para multi-org) | `githubToken` |
| GitHub App | `githubAppId`, `githubOrganization` | `githubAppPrivateKey` (base64) |

Para GitHub Enterprise Server existe además `integration.config.githubHost` (URL del API de tu GHES).

## Paso 2 — Crear el Secret manual

Las credenciales NUNCA van a git. Se crean a mano en el namespace `port-idp`, y el chart las consume con `secret.create: false` + `secret.name`. Cada `integration.secrets.<clave>` se convierte en una variable `OCEAN__INTEGRATION__CONFIG__<CLAVE_EN_SNAKE_UPPER>` (`githubToken` → `GITHUB_TOKEN`).

Con PAT:

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-github-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__GITHUB_TOKEN='<GITHUB_PAT>'
```

Con GitHub App (en lugar del token):

```bash
kubectl create secret generic ocean-github-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__GITHUB_APP_PRIVATE_KEY='<PRIVATE_KEY_BASE64>'
```

Verifica:

```bash
kubectl get secret ocean-github-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

## Paso 3 — Values

Archivo `deployment/install/ocean-github/values.yaml` (variante PAT):

```yaml
# Values de la integración Ocean GitHub (github-ocean) para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-github-credentials"
# creado a mano en el namespace port-idp.
port:
  baseUrl: https://api.us.getport.io

# Integración OFICIAL: NO se define imageRegistry/image/imagePullPolicy,
# el chart usa ghcr.io/port-labs por defecto.

# true = crea blueprints y mapping default automáticamente.
# Alternativa: false + gestionar blueprints con Terraform (provider port-labs).
# Si migras desde el GitHub app exporter clásico, usa createPortResourcesOrigin: Empty (ver doc).
initializePortResources: true
scheduledResyncInterval: 360   # minutos; GitHub tiene rate limits, un resync cada 6 h es razonable

# No crear el Secret desde el chart: usar el Secret manual del namespace.
# Debe contener: OCEAN__PORT__CLIENT_ID, OCEAN__PORT__CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__GITHUB_TOKEN
secret:
  create: false
  name: ocean-github-credentials

resources:
  requests:
    memory: "128Mi"
    cpu: "50m"
  limits:
    memory: "512Mi"
    cpu: "500m"

integration:
  identifier: github
  type: github-ocean
  eventListener:
    type: POLLING
  config:
    githubOrganization: "mi-organizacion"   # ajustar a la organización real
    # organizations: '["org1","org2"]'      # multi-org (requiere PAT classic o GitHub App >= 6.5.0)
    # githubHost: "https://ghe.miempresa.com/api/v3"  # solo GitHub Enterprise Server
```

Variante GitHub App: sustituye la clave del Secret por `OCEAN__INTEGRATION__CONFIG__GITHUB_APP_PRIVATE_KEY` y añade en `integration.config` el `githubAppId`:

```yaml
integration:
  identifier: github
  type: github-ocean
  eventListener:
    type: POLLING
  config:
    githubAppId: "123456"
    githubOrganization: "mi-organizacion"
```

## Paso 4 — ApplicationSet

Archivo `deployment/applicationsets/20-ocean-github.yaml`:

```yaml
# Despliega la integración Ocean GitHub (github-ocean) en cada cluster del entorno laboratory.
# Multi-source: chart oficial port-ocean + values desde este repo ($values).
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-github
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
      name: 'port-ocean-github-{{.name}}'
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
            releaseName: github
            valueFiles:
              - $values/deployment/install/ocean-github/values.yaml
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

> Haz commit de los dos archivos (`deployment/install/ocean-github/values.yaml` y `deployment/applicationsets/20-ocean-github.yaml`) y push a la rama `laboratory`. La app-of-apps (`deployment/bootstrap/root.yaml`) detecta el nuevo ApplicationSet y ArgoCD despliega la integración solo, sin pasos manuales adicionales.

```bash
git checkout laboratory
git add deployment/install/ocean-github/values.yaml deployment/applicationsets/20-ocean-github.yaml
git commit -m "feat: integración Ocean GitHub (github-ocean) en laboratory"
git push origin laboratory
```

## Paso 5 — Verificación

```bash
# La Application generada por el ApplicationSet debe estar Synced/Healthy
kubectl get applications -n argocd | grep port-ocean-github

# Pod de la integración en marcha
kubectl get pods -n port-idp -l app.kubernetes.io/instance=github

# Logs del resync
kubectl logs -n port-idp deploy/github-port-ocean -f
```

Qué buscar en los logs:

- Autenticación correcta contra la API de Port (sin errores 401 hacia `api.us.getport.io`).
- Inicio del resync: líneas por kind (`repository`, `pull-request`, ...) con recuento de entidades "upserted".
- Ausencia de `401/403` hacia `api.github.com` (indicarían scopes insuficientes del token).

Qué ver en Port:

- **Builder**: blueprints `githubRepository`, `githubPullRequest`, etc. creados.
- **Catalog**: entidades de repositorios y pull requests de tu organización.
- **Settings/Builder → Data sources**: la integración `github` aparece con estado y fecha del último resync, y desde ahí se edita el mapping.

## Instalación alternativa (helm install directo)

Si no quieres GitOps, el comando oficial (patrón de la doc de Port/Ocean) con PAT es:

```bash
helm repo add --force-update port-labs https://port-labs.github.io/helm-charts

helm upgrade --install github port-labs/port-ocean \
  --create-namespace --namespace port-idp \
  --set port.clientId="<PORT_CLIENT_ID>" \
  --set port.clientSecret="<PORT_CLIENT_SECRET>" \
  --set port.baseUrl="https://api.us.getport.io" \
  --set initializePortResources=true \
  --set scheduledResyncInterval=360 \
  --set integration.identifier="github" \
  --set integration.type="github-ocean" \
  --set integration.eventListener.type="POLLING" \
  --set integration.config.githubOrganization="mi-organizacion" \
  --set integration.secrets.githubToken="<GITHUB_PAT>"
```

(Para GitHub App: `--set integration.config.githubAppId=...` y `--set integration.secrets.githubAppPrivateKey=<BASE64>` en lugar del token.)

## Configuración avanzada

- **Mapping (port-app-config)**: con `initializePortResources: true` se instala el mapping default. Se edita en Port: **Data sources → github → Mapping**, con la sintaxis `resources: - kind: ... selector.query (JQ) ... port.entity.mappings`. También existe `repoManagedMapping: true` para cargar el mapping desde un archivo `port-app-config.yml` versionado en GitHub (GitOps del mapping).
- **`createPortResourcesOrigin: Empty`**: obligatorio en values si ya tienes blueprints del exporter GitHub clásico y no quieres que la instalación self-hosted cree los default (evita conflictos; ver guía de migración oficial).
- **`repositoryType`**: filtra qué repos ingesta la API (`all`, `public`, `private`, `forks`, `sources`).
- **Live events (webhooks)**: la integración puede autoconfigurar webhooks en GitHub para eventos en tiempo real. Requiere: (1) URL pública de la integración vía `liveEvents.baseUrl` en los values (Ingress/LoadBalancer accesible desde github.com), y (2) que el PAT pueda crear organization webhooks (o que la GitHub App tenga webhook configurado). Sin esto, el modo POLLING con `scheduledResyncInterval` es suficiente.
- **Self-service actions vía GitHub Ocean**: en self-hosted el procesador de acciones está deshabilitado por defecto; se activa con `actionsProcessor.enabled=true` y `ocean.baseUrl=<URL_PUBLICA>` (y requiere machine tokens de Port).
- **Blueprints con Terraform**: alternativa a `initializePortResources: true` → ponlo a `false` y define blueprints/mapping con el provider Terraform `port-labs` (como se hace en `integrations/terraform/blueprints/` de este repo).

## Troubleshooting

| Síntoma | Causa | Fix |
|---|---|---|
| Pod en `CreateContainerConfigError` | El Secret `ocean-github-credentials` no existe en `port-idp` o le falta una clave | Recrear el Secret con las 3 claves `OCEAN__*` exactas y reiniciar el pod |
| Logs con `401 Unauthorized` hacia `api.us.getport.io` | `OCEAN__PORT__CLIENT_ID/SECRET` incorrectos o región equivocada | Verificar credenciales en Port (`...` → Credentials) y `port.baseUrl: https://api.us.getport.io` |
| Logs con `401 Bad credentials` hacia GitHub | PAT caducado, revocado o mal copiado | Regenerar el PAT y actualizar el Secret (`kubectl delete secret` + `create`), reiniciar pod |
| Logs con `403` / recursos vacíos (teams, alerts...) | Scopes/permisos insuficientes (`read:org` ausente, fine-grained sin ese permiso) o SSO sin autorizar | Ampliar scopes del token y autorizar SSO en la organización |
| No aparecen repos privados | PAT fine-grained sin acceso a esos repos o classic sin scope `repo` | Ajustar `Repository access` del token / añadir scope `repo` |
| Solo sincroniza una organización | Fine-grained PAT o GitHub App (limitados a 1 org) | Usar PAT classic + `organizations: '["org1","org2"]'` |
| `403 rate limit exceeded` | Resync demasiado frecuente con PAT en org grande | Aumentar `scheduledResyncInterval` o migrar a GitHub App (mayor cuota) |
| Blueprints duplicados/conflicto tras migración | `initializePortResources: true` con datos del exporter clásico ya existentes | Usar `createPortResourcesOrigin: Empty` y seguir la guía de migración |
| Application `OutOfSync` sin desplegarse | Labels del cluster no coinciden con el selector | Verificar labels `project: port`, `environment: laboratory` y `cloud` en el Secret de cluster de ArgoCD |

## Referencias

- GitHub (Ocean) — página principal: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/git/github-ocean/ (redirige a https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/git/github-ocean/)
- GitHub (Ocean) — instalación: https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/git/github-ocean/installation/
- GitHub (Ocean) — guía de migración desde el exporter clásico: https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/git/github-ocean/migration/migration-steps/
- GitHub (Ocean) — ejemplos de mapping: https://docs.port.io/context-lake/ingestion/ingest-data-into-port/native-integrations/git/github-ocean/examples/
- GitHub App clásica (hosted by Port, alternativa): https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/git/github/
- Ocean — despliegue con Helm: https://ocean.port.io/deployment/helm/
- Ocean — despliegue con ArgoCD: https://ocean.port.io/deployment/argocd/
- Chart port-ocean (README): https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md
