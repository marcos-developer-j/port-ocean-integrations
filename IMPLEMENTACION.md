# Guía de implementación paso a paso

Guía completa para poner en producción las 4 integraciones Ocean (JFrog, Orca, Veracode, GitHub Projects) de este repositorio, integrándolas con el proyecto Terraform existente (`../Port`).

## Índice

1. [Prerrequisitos](#1-prerrequisitos)
2. [Credenciales de Port](#2-credenciales-de-port)
3. [Credenciales por herramienta](#3-credenciales-por-herramienta)
4. [Prueba local de cada integración](#4-prueba-local-de-cada-integración)
5. [Migrar blueprints a Terraform](#5-migrar-blueprints-a-terraform)
6. [Build y publicación de imágenes Docker](#6-build-y-publicación-de-imágenes-docker)
7. [Despliegue en Kubernetes con Helm](#7-despliegue-en-kubernetes-con-helm)
8. [Configuración de webhooks (tiempo real)](#8-configuración-de-webhooks-tiempo-real)
9. [Verificación](#9-verificación)
10. [Relaciones con `service` y scorecards](#10-relaciones-con-service-y-scorecards)
11. [Troubleshooting](#11-troubleshooting)
12. [Mantenimiento](#12-mantenimiento)

---

## 1. Prerrequisitos

| Herramienta | Versión | Uso |
|---|---|---|
| Python | >= 3.12 y < 3.14 | Ejecutar las integraciones localmente |
| pip / poetry | reciente | Instalar `port-ocean[cli]` |
| Docker | reciente | Construir imágenes para deploy |
| Helm | >= 3 | Deploy en Kubernetes |
| Terraform | >= 1.5.0 | Ya usado en `../Port` |
| kubectl | según cluster | Operar el cluster destino |

Accesos necesarios:

- Admin (o rol con permisos de credenciales) en la organización de Port.
- Cuenta con permisos de lectura en JFrog, Orca, Veracode y la organización de GitHub.
- Un registry de contenedores (GHCR, ECR, ACR, Artifactory Docker, etc.).
- Un cluster de Kubernetes con salida a internet (o a las instancias self-hosted de las herramientas).

> Importante: nunca commitear archivos `.env`. Este directorio incluye un `.gitignore` que los excluye.

## 2. Credenciales de Port

1. Entrar a [app.getport.io](https://app.getport.io) (o `app.us.port.io` si tu organización está en la región US).
2. Click en el ícono `...` (arriba a la derecha) → **Credentials**.
3. Copiar **Client ID** y **Client Secret**.
4. La URL del API depende de la región:
   - EU (default): `https://api.getport.io`
   - US: `https://api.us.port.io`

Son las mismas credenciales que usa el provider de Terraform (`PORT_CLIENT_ID` / `PORT_CLIENT_SECRET`), puedes reutilizarlas o crear credenciales dedicadas.

## 3. Credenciales por herramienta

### 3.1 JFrog — Access Token

1. Entrar a la plataforma JFrog como admin: `https://<tu-empresa>.jfrog.io`.
2. **Administration** → **User Management** → **Access Tokens** → **Generate Token**.
3. Configurar:
   - **Token scope**: Admin (o un usuario con lectura de repositorios, builds y, si aplica, Xray).
   - **Expiration**: según tu política (recordar rotarlo).
4. Guardar el token generado (solo se muestra una vez).

Permisos mínimos requeridos por kind:

| Kind | Permiso |
|---|---|
| `repository`, `artifact` | Lectura de Artifactory |
| `build` | Lectura de builds |
| `project` | Lectura de Projects (requiere licencia con Projects; si no existe, la integración lo omite con warning) |
| `xray_violation` | Lectura de Xray (si no está disponible, se omite con warning) |

### 3.2 Orca — API Token

1. Entrar a la consola de Orca Security.
2. **Settings** (abajo a la derecha) → sección de **API** → crear un **API Token** con un rol de solo lectura (viewer).
3. Guardar el token.
4. Identificar la URL regional de tu tenant:
   - `https://api.orcasecurity.io` (US)
   - `https://api.eu.orcasecurity.io` (EU)
   - Otras regiones: ver la URL con la que accedes a la consola.

### 3.3 Veracode — API Credentials (HMAC)

1. Entrar a la plataforma Veracode con un usuario que tenga el rol **Results API** (los usuarios "API service account" son lo recomendado).
2. Menú del usuario (arriba a la derecha) → **API Credentials** → **Generate API Credentials**.
3. Guardar el **API ID** y el **API Secret Key** (hexadecimales; solo se muestran una vez).
4. Región del API:
   - Commercial (default): `https://api.veracode.com`
   - EU: `https://api.veracode.eu`
   - US Federal: `https://api.veracode.us`

> Las credenciales expiran (por defecto al año). Documentar la fecha y programar la rotación.

### 3.4 GitHub — Personal Access Token

Opción A — PAT clásico:
1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token**.
2. Scopes: `read:project` y `read:org`.
3. Si la organización usa SSO/SAML: click en **Configure SSO** sobre el token y autorizarlo para la organización.

Opción B — Fine-grained token:
1. **Fine-grained tokens** → **Generate new token**.
2. **Resource owner**: la organización.
3. **Organization permissions** → **Projects: Read-only**.
4. Puede requerir aprobación del owner de la organización.

> Recomendación para producción: usar un *service account* de GitHub (no un token personal) para que la integración no dependa de una persona.

## 4. Prueba local de cada integración

Repetir estos pasos para cada carpeta (`jfrog/`, `orca/`, `veracode/`, `github-projects/`):

```bash
cd integrations/<integracion>

# 1. Entorno virtual e instalación
python -m venv .venv
.venv\Scripts\activate          # Windows (en Linux/Mac: source .venv/bin/activate)
pip install "port-ocean[cli]"

# 2. Configuración
copy .env.example .env          # Windows (cp en Linux/Mac)
# Editar .env con las credenciales reales de Port y de la herramienta

# 3. Ejecutar
ocean sail
```

Qué esperar en la primera ejecución:

1. Ocean se registra como *data source* en Port (aparece en **Builder → Data sources**).
2. Con `OCEAN__INITIALIZE_PORT_RESOURCES=true` crea los blueprints de `.port/resources/blueprints.json` y el mapping de `port-app-config.yml` (para la primera prueba está bien; en producción con Terraform ver [sección 5](#5-migrar-blueprints-a-terraform)).
3. Ejecuta el resync inicial: en los logs se ven los lotes de cada kind (`Yielding N ...`).
4. Las entities aparecen en el catálogo de Port.

Variables de entorno útiles para debugging:

```bash
OCEAN__LOG_LEVEL=DEBUG          # logs detallados
```

Prueba puntual del webhook local (JFrog / Orca) sin exponer el servicio:

```bash
# La integración escucha en http://localhost:8000
curl -X POST http://localhost:8000/integration/webhook -H "Content-Type: application/json" -d "{...payload de prueba...}"
```

## 5. Migrar blueprints a Terraform

Objetivo: que `../Port/modules/catalog/blueprints` sea la única fuente de verdad y las integraciones **no** creen/modifiquen blueprints.

### 5.1 Crear el archivo de blueprints de integraciones

Crear `Port/modules/catalog/blueprints/integrations.tf` traduciendo cada blueprint de los `blueprints.json` a HCL del provider `port-labs/port-labs ~> 2.0`.

Reglas de conversión JSON → HCL:

| En `blueprints.json` | En HCL |
|---|---|
| `"type": "string"` | entrada en `string_props` |
| `"type": "string", "format": "date-time"` | `string_props` con `format = "date-time"` |
| `"type": "string", "format": "url"` | `string_props` con `format = "url"` |
| `"type": "number"` | entrada en `number_props` |
| `"type": "boolean"` | entrada en `boolean_props` |
| `"type": "array"` (items string) | entrada en `array_props` con `string_items = {}` |
| `"relations"` | bloque `relations` con `target = port_blueprint.<recurso>.identifier` |

Ejemplo completo (Veracode; aplicar el mismo patrón para los demás):

```hcl
resource "port_blueprint" "veracode_application" {
  identifier = "veracodeApplication"
  title      = "Veracode Application"
  icon       = "Lock"

  properties = {
    string_props = {
      "name"                = { title = "Name" }
      "businessCriticality" = { title = "Business Criticality" }
      "policyCompliance"    = { title = "Policy Compliance" }
      "created"             = { title = "Created", format = "date-time" }
      "modified"            = { title = "Modified", format = "date-time" }
    }
    array_props = {
      "teams" = {
        title        = "Teams"
        string_items = {}
      }
    }
  }
}

resource "port_blueprint" "veracode_finding" {
  identifier = "veracodeFinding"
  title      = "Veracode Finding"
  icon       = "Lock"

  properties = {
    string_props = {
      "scanType"         = { title = "Scan Type" }
      "cweName"          = { title = "CWE Name" }
      "status"           = { title = "Status" }
      "resolutionStatus" = { title = "Resolution Status" }
      "description"      = { title = "Description" }
      "filePath"         = { title = "File Path" }
      "firstFound"       = { title = "First Found", format = "date-time" }
      "lastSeen"         = { title = "Last Seen", format = "date-time" }
    }
    number_props = {
      "severity" = { title = "Severity" }
      "cweId"    = { title = "CWE ID" }
    }
    boolean_props = {
      "violatesPolicy" = { title = "Violates Policy" }
    }
  }

  relations = {
    "application" = {
      title    = "Application"
      target   = port_blueprint.veracode_application.identifier
      required = false
      many     = false
    }
  }
}
```

Blueprints a traducir (identifiers exactos, deben coincidir con los mappings):

| Integración | Blueprints |
|---|---|
| JFrog | `jfrogProject`, `jfrogRepository`, `jfrogBuild`, `jfrogArtifact` (relación `repository`→`jfrogRepository`), `jfrogXrayViolation` |
| Orca | `orcaAsset`, `orcaAlert` (relación `asset`→`orcaAsset`) |
| Veracode | `veracodeApplication`, `veracodeFinding` (relación `application`→`veracodeApplication`) |
| GitHub Projects | `githubProject`, `githubProjectItem` (relación `project`→`githubProject`) |

> El detalle completo de propiedades y tipos está en `<integracion>/.port/resources/blueprints.json` de cada carpeta.

### 5.2 Aplicar

```bash
cd Port
terraform plan     # revisar que solo se crean los blueprints nuevos
terraform apply
```

Caso especial — si ya corriste una integración con `OCEAN__INITIALIZE_PORT_RESOURCES=true` (los blueprints ya existen en Port), importarlos al state en lugar de recrearlos:

```bash
terraform import 'module.blueprints.port_blueprint.veracode_application' veracodeApplication
terraform import 'module.blueprints.port_blueprint.veracode_finding' veracodeFinding
# ...repetir por cada blueprint existente
```

### 5.3 Desactivar la creación de recursos en las integraciones

A partir de aquí, en **todas** las integraciones:

- Local / Docker: `OCEAN__INITIALIZE_PORT_RESOURCES=false` en el `.env`.
- Helm: `initializePortResources: false` en el values.

Con esto las integraciones solo hacen upsert de entities; nunca tocan blueprints ni el mapping ya configurado.

## 6. Build y publicación de imágenes Docker

Por cada integración:

```bash
cd integrations/<integracion>

docker build -t <registry>/port-ocean-<integracion>:0.1.0 .
docker push <registry>/port-ocean-<integracion>:0.1.0
```

Recomendaciones:

- Versionar las tags igual que `version` en `pyproject.toml` (no usar solo `latest`).
- Automatizar con CI (ej. GitHub Actions con trigger por cambios en `integrations/<integracion>/**`).
- Si el registry es el propio Artifactory de JFrog, crear un repositorio Docker local `port-ocean`.

## 7. Despliegue en Kubernetes con Helm

Se usa el chart genérico [`port-labs/port-ocean`](https://artifacthub.io/packages/helm/port-labs/port-ocean) con la imagen propia de cada integración.

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm repo update
```

Crear un `values-<integracion>.yaml` por integración (NO commitear los secrets; usar `--set` desde el pipeline, SOPS, o external-secrets). Ejemplo Veracode:

```yaml
# values-veracode.yaml
port:
  baseUrl: https://api.getport.io        # o https://api.us.port.io

initializePortResources: false           # blueprints gestionados por Terraform
scheduledResyncInterval: 180             # minutos (Veracode no tiene webhooks)

integration:
  identifier: veracode
  type: veracode
  eventListener:
    type: POLLING
  config:
    veracodeApiBase: https://api.veracode.com

image:
  repository: <registry>/port-ocean-veracode
  tag: "0.1.0"

resources:
  requests:
    cpu: 100m
    memory: 256Mi
  limits:
    memory: 512Mi
```

Instalación (los secrets por CLI o secret manager):

```bash
helm upgrade --install veracode port-labs/port-ocean \
  -n port-ocean --create-namespace \
  -f values-veracode.yaml \
  --set port.clientId=$PORT_CLIENT_ID \
  --set port.clientSecret=$PORT_CLIENT_SECRET \
  --set-string integration.secrets.veracodeApiId=$VERACODE_API_ID \
  --set-string integration.secrets.veracodeApiSecret=$VERACODE_API_SECRET
```

Config y secrets equivalentes por integración:

| Integración | `integration.config` | `integration.secrets` | `scheduledResyncInterval` sugerido |
|---|---|---|---|
| jfrog | `jfrogHostUrl` | `jfrogAccessToken` | 60–120 min (webhook cubre tiempo real) |
| orca | `orcaApiUrl` | `orcaApiToken` | 120–240 min (webhook cubre tiempo real) |
| veracode | `veracodeApiBase` | `veracodeApiId`, `veracodeApiSecret` | 60–240 min |
| github-projects | `githubOrganization`, `githubGraphqlUrl` | `githubToken` | 30–60 min |

Para JFrog y Orca (webhooks entrantes) además hay que exponer el servicio:

```yaml
# añadir al values de jfrog y orca
ingress:
  enabled: true
  className: nginx                       # según tu cluster
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt   # si usas cert-manager
  hosts:
    - host: ocean-jfrog.tu-dominio.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: ocean-jfrog-tls
      hosts:
        - ocean-jfrog.tu-dominio.com
```

> Si el chart de tu versión no incluye ingress, crear el `Ingress` aparte apuntando al `Service` del release en el puerto 8000. Solo se necesita exponer `/integration/webhook`; ideal restringir por IP de origen (JFrog Cloud / Orca) en el ingress.

## 8. Configuración de webhooks (tiempo real)

### 8.1 JFrog

1. Plataforma JFrog → **Administration** → **General** → **Webhooks** → **New Webhook**.
2. **URL**: `https://ocean-jfrog.tu-dominio.com/integration/webhook`
3. Crear dos webhooks (o uno por evento):
   - **Domain: Artifact** → evento **deployed**.
   - **Domain: Build** → evento **uploaded**.
4. Guardar y usar **Test** para validar (revisar logs del pod: debería registrarse el evento).

### 8.2 Orca

1. Consola de Orca → **Settings** → **Connections** → **Integrations** → **Webhooks** → **Configure** → **Create**.
2. **URL**: `https://ocean-orca.tu-dominio.com/integration/webhook`
3. Dejar el campo **API Key** vacío.
4. Crear una **Automation** (Automations → New) que envíe alertas al webhook según filtros (ej. severidad >= high), o probar manualmente: **Alerts** → abrir una alerta → **Take Action** → **Notifications** → **Send to webhook**.
5. Verificar que la entity de la alerta aparece/actualiza en Port.

### 8.3 Veracode y GitHub Projects

No usan webhooks en esta implementación; el dato se refresca con `scheduledResyncInterval`. Si más adelante se necesita tiempo real en GitHub Projects, se requiere una GitHub App con eventos `projects_v2` / `projects_v2_item` (ampliación futura de `github-projects/main.py`).

## 9. Verificación

Checklist por integración:

1. **Data source registrado**: Port → **Builder** → **Data sources** → aparece la integración con su identifier.
2. **Resync exitoso**: en la misma pantalla, el último sync muestra estado success y conteo de entities por kind.
3. **Entities en catálogo**: revisar el catálogo (o crear una page para cada blueprint) y validar contra la herramienta origen:
   - JFrog: nº de repositorios == `GET /artifactory/api/repositories`.
   - Orca: nº de alertas ~= total del dashboard de Orca (según filtros).
   - Veracode: nº de applications == perfil de apps en Veracode.
   - GitHub Projects: nº de proyectos == vista de Projects de la organización.
4. **Logs sin errores**: `kubectl logs -n port-ocean deploy/<release>` sin errores repetidos (warnings de Xray/Projects ausentes son esperables).
5. **Webhook operativo** (JFrog/Orca): forzar un evento y ver la entity actualizada en segundos.

## 10. Relaciones con `service` y scorecards

Para explotar los datos (scorecards, dashboards), conectar los blueprints de integración con el blueprint central `service` (identifier actual: `test_service`).

### 10.1 Relación en Terraform

Ejemplo — un `service` conoce su aplicación de Veracode y su repo de JFrog:

```hcl
# En Port/modules/catalog/blueprints/blueprints.tf, dentro de port_blueprint.service:
  relations = {
    "environments" = { ... }   # existente

    "veracode_application" = {
      title    = "Veracode Application"
      target   = port_blueprint.veracode_application.identifier
      required = false
      many     = false
    }
    "jfrog_repository" = {
      title    = "JFrog Repository"
      target   = port_blueprint.jfrog_repository.identifier
      required = false
      many     = true
    }
  }
```

El poblado de esas relaciones puede ser manual, por convención de nombres en los mappings JQ, o vía automations de Port.

### 10.2 Mirror + scorecard de seguridad

Con las relaciones creadas se pueden agregar mirror/aggregation properties en `service` (ej. `policyCompliance` de Veracode) y un scorecard en `Port/modules/catalog/blueprints/scorecards.tf`:

```hcl
resource "port_scorecard" "service_security" {
  identifier = "security-readiness"
  title      = "Security Readiness"
  blueprint  = port_blueprint.service.identifier

  rules = [
    {
      identifier = "veracode-policy-pass"
      title      = "Pasa la política de Veracode"
      level      = "Gold"
      query = {
        combinator = "and"
        conditions = [jsonencode({
          property = "veracode_policy_compliance"   # mirror property
          operator = "="
          value    = "PASSED"
        })]
      }
    }
  ]
}
```

## 11. Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `401` contra el API de Port | Credenciales o región equivocada | Verificar Client ID/Secret y `OCEAN__PORT__BASE_URL` (EU vs US) |
| Veracode `401 Unauthorized` | Firma HMAC inválida | Verificar que ID/secret son los hex exactos; revisar reloj del sistema (la firma usa timestamp; NTP desincronizado la invalida); confirmar región (`api.veracode.com` vs `.eu`) |
| GitHub GraphQL `INSUFFICIENT_SCOPES` | Token sin `read:project` | Regenerar el token con los scopes correctos y autorizar SSO si aplica |
| GitHub `organization` es `null` | Org incorrecta o token sin acceso | Verificar `githubOrganization` (login exacto) y autorización SSO |
| JFrog resync de artifacts muy lento | Demasiados repos/artefactos vía AQL | Reducir alcance: filtrar repos en `client.py`, subir el intervalo de resync, o quitar el kind `artifact` del mapping |
| Orca `429 Too Many Requests` | Rate limit del API | Bajar `limit` en `client.py` y/o aumentar el intervalo de resync |
| Entities no aparecen pero no hay errores | Mapping JQ no matchea el payload real | Port → Data sources → abrir la integración → probar el JQ contra el payload de ejemplo; ajustar mapping |
| Blueprints duplicados/conflictivos | Se corrió con `initializePortResources=true` teniendo Terraform | Poner `false`, borrar los duplicados en Port o importarlos al state (sección 5.2) |
| El webhook no llega | Ingress/DNS/TLS o firewall | `curl -X POST https://<host>/integration/webhook` desde fuera; revisar logs del ingress y del pod |

Logs detallados: `OCEAN__LOG_LEVEL=DEBUG` (env) o `--set logLevel=DEBUG` en Helm.

## 12. Mantenimiento

- **Mapping**: tras la instalación, el mapping vivo se edita en Port (**Data sources** → integración). Los `port-app-config.yml` del repo son el default inicial: mantenerlos sincronizados con lo que se edite en la UI (o tratarlos como única fuente y reaplicar).
- **Rotación de credenciales**: JFrog token, Orca token, Veracode credentials (expiran ~1 año) y GitHub PAT. Documentar fechas y renovar vía secret manager + `helm upgrade`.
- **Actualización de Ocean**: rebuild periódico de las imágenes para tomar nuevas versiones de `port-ocean` (revisar [releases](https://github.com/port-labs/ocean/releases) por breaking changes).
- **Nuevos kinds**: agregar método en `client.py`, handler en `main.py`, kind en `.port/spec.yaml`, blueprint en Terraform y mapping en `port-app-config.yml`.
- **Monitoreo**: los data sources en Port muestran métricas de sync (duración, entities, errores). Alertar sobre pods en CrashLoopBackOff y sobre syncs fallidos.
- **GitHub Projects → futuro**: si Port agrega soporte nativo de Projects V2 a su integración GitHub (revisar changelog), evaluar migrar y retirar esta integración custom.
