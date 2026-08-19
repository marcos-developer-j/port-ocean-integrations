# Blueprints de las integraciones Ocean — Terraform

Configuración Terraform standalone que crea en Port los **11 blueprints** que usan las integraciones Ocean de este repo (`integrations/`). Es el equivalente en HCL de los `blueprints.json` de cada integración, para que **Terraform sea la única fuente de verdad** del modelo de datos.

| Archivo | Blueprints | Relaciones internas |
|---|---|---|
| `jfrog.tf` | `jfrogProject`, `jfrogRepository`, `jfrogBuild`, `jfrogArtifact`, `jfrogXrayViolation` | `jfrogArtifact` → `jfrogRepository` |
| `orca.tf` | `orcaAsset`, `orcaAlert` | `orcaAlert` → `orcaAsset` |
| `veracode.tf` | `veracodeApplication`, `veracodeFinding` | `veracodeFinding` → `veracodeApplication` |
| `github_projects.tf` | `githubProject`, `githubProjectItem` | `githubProjectItem` → `githubProject` |

## Prerrequisitos

- Terraform `>= 1.5.0`
- Credenciales de Port (Client ID / Client Secret): en la app de Port ir a `...` (arriba a la derecha) → **Credentials** → **Generate API token**
- Conocer la región de tu organización Port:
  - EU: `https://api.getport.io` (default)
  - US: `https://api.us.getport.io`

## Paso 1 — Configurar credenciales

Opción recomendada, por variables de entorno (no quedan en disco ni en el state plan):

```bash
# Linux/macOS
export PORT_CLIENT_ID="<tu-client-id>"
export PORT_CLIENT_SECRET="<tu-client-secret>"

# Windows PowerShell
$env:PORT_CLIENT_ID = "<tu-client-id>"
$env:PORT_CLIENT_SECRET = "<tu-client-secret>"
```

Alternativa con tfvars (crear `terraform.tfvars`, **no commitear**):

```hcl
port_client_id     = "<tu-client-id>"
port_client_secret = "<tu-client-secret>"
# port_base_url    = "https://api.us.getport.io"   # solo si tu org es US
```

## Paso 2 — Init y plan

```bash
cd integrations/terraform/blueprints
terraform init
terraform plan
```

El plan debe mostrar **11 recursos a crear** (`port_blueprint.*`). Revisar que no haya conflictos con blueprints existentes.

## Paso 3 — ¿Los blueprints ya existen en Port?

Si alguna integración ya corrió con `initializePortResources=true` (o los creaste a mano), los blueprints ya existen y `terraform apply` fallaría con conflicto. En ese caso **importarlos** en lugar de crearlos:

```bash
terraform import port_blueprint.jfrog_project        jfrogProject
terraform import port_blueprint.jfrog_repository     jfrogRepository
terraform import port_blueprint.jfrog_build          jfrogBuild
terraform import port_blueprint.jfrog_artifact       jfrogArtifact
terraform import port_blueprint.jfrog_xray_violation jfrogXrayViolation
terraform import port_blueprint.orca_asset           orcaAsset
terraform import port_blueprint.orca_alert           orcaAlert
terraform import port_blueprint.veracode_application veracodeApplication
terraform import port_blueprint.veracode_finding     veracodeFinding
terraform import port_blueprint.github_project       githubProject
terraform import port_blueprint.github_project_item  githubProjectItem
```

Importar solo los que existan; después `terraform plan` mostrará las diferencias entre lo que hay en Port y este HCL.

## Paso 4 — Apply

```bash
terraform apply
```

Verificar en Port: **Builder** → deben aparecer los 11 blueprints con sus propiedades y relaciones.

## Paso 5 — Ejecutar las integraciones sin que toquen los blueprints

Para que las integraciones Ocean **no** creen/modifiquen blueprints por su cuenta (y Terraform siga siendo la fuente de verdad):

- Local / Docker: `OCEAN__INITIALIZE_PORT_RESOURCES=false` en el `.env`
- Helm: `--set initializePortResources=false`

## Relaciones opcionales hacia `service` (scorecards)

Por defecto están **desactivadas**. Para habilitar la relación opcional `service` en `jfrogRepository`, `orcaAlert` y `veracodeApplication` (necesaria para scorecards de seguridad unificados sobre el blueprint central de servicios):

```bash
terraform apply -var="enable_service_relations=true"
```

o en `terraform.tfvars`:

```hcl
enable_service_relations     = true
service_blueprint_identifier = "test_service"   # default; cambiar si tu blueprint de servicios usa otro identifier
```

> Requisito: el blueprint de servicios (`test_service`, gestionado en `../../../Port/modules/catalog/blueprints`) debe existir en Port **antes** de aplicar con este flag, porque las relaciones apuntan a su identifier. Como este root es independiente del de `Port/`, no hay dependencia de Terraform entre ambos: solo asegúrate del orden de apply.

Una vez habilitadas, poblar la relación en los mappings JQ (`.port/resources/port-app-config.yml` de cada integración) o vía automations en Port, y crear el scorecard (ejemplo de HCL en `../../IMPLEMENTACION.md`, sección 10).

## Notas

- **Orden de creación**: las relaciones internas usan referencias (`port_blueprint.X.identifier`), así que Terraform resuelve el orden solo (ej. `jfrogRepository` antes que `jfrogArtifact`).
- **State**: este root usa state local (`terraform.tfstate`). Para trabajo en equipo, configurar un backend remoto (S3, Terraform Cloud, etc.) igual que en el root de `Port/`.
- **No borrar a la ligera**: `terraform destroy` elimina los blueprints y con ellos **todas sus entities** en el catálogo.
- **Cambios de schema**: si modificas propiedades aquí, actualiza también el `blueprints.json` de la integración correspondiente para mantenerlos alineados (solo sirven como referencia/bootstrap, pero conviene que no diverjan).
- Guía completa de implementación de las integraciones (credenciales, Docker, Helm, webhooks, troubleshooting): [`../../IMPLEMENTACION.md`](../../IMPLEMENTACION.md).
