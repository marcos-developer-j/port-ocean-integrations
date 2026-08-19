# docs/ — Tutoriales de integraciones Port Ocean

Tutoriales detallados de implementación (prerrequisitos, credenciales, Secret manual,
values, ApplicationSet, verificación y troubleshooting) para integraciones **oficiales**
de Port Ocean, siguiendo el patrón GitOps de este repo:

- Chart `port-ocean` **0.23.4** desde `https://port-labs.github.io/helm-charts`
- ApplicationSets multi-source en `deployment/applicationsets/` (cluster generator)
- Values versionados en `deployment/install/ocean-<x>/values.yaml` (rama `laboratory`)
- Credenciales SIEMPRE fuera de git: Secret manual `ocean-<x>-credentials` en `port-idp`
- Port región **US**: `port.baseUrl: https://api.us.getport.io`
- Integraciones oficiales: `initializePortResources: true` e imagen default de `ghcr.io/port-labs`

## Índice

| Doc | Integración | Tipo | ApplicationSet propuesto |
|---|---|---|---|
| [ocean-github.md](ocean-github.md) | GitHub (github-ocean) | Oficial | `20-ocean-github.yaml` |
| [ocean-argocd.md](ocean-argocd.md) | ArgoCD | Oficial | `21-ocean-argocd.yaml` |
| [ocean-sonarqube.md](ocean-sonarqube.md) | SonarQube / SonarCloud | Oficial | `22-ocean-sonarqube.yaml` |
| [ocean-dynatrace.md](ocean-dynatrace.md) | Dynatrace | Oficial | `23-ocean-dynatrace.yaml` |
| [ocean-servicenow.md](ocean-servicenow.md) | ServiceNow | Oficial | `24-ocean-servicenow.yaml` |
| [ocean-grafana.md](ocean-grafana.md) | Grafana | **No oficial** → vía Ocean `custom` / webhook | `25-ocean-grafana.yaml` |
| [ocean-confluence.md](ocean-confluence.md) | Confluence | **No oficial** → vía Ocean `custom` + visión docs→README | `26-ocean-confluence.yaml` |
| [ocean-aws.md](ocean-aws.md) | AWS — **multi-cuenta** (AssumeRole cross-account) | Oficial | `30-ocean-aws.yaml` |
| [ocean-azure.md](ocean-azure.md) | Azure — **multi-suscripción** (Service Principal + RBAC) | Oficial | `31-ocean-azure.yaml` |
| [ocean-gcp.md](ocean-gcp.md) | GCP — **multi-proyecto** (SA a nivel de organización) | Oficial | `32-ocean-gcp.yaml` |
| [gcp-artifact-registry.md](gcp-artifact-registry.md) | Migración de imágenes custom a GCP Artifact Registry | Infraestructura | — |

## Cómo usar un tutorial

Cada doc es autocontenido. El flujo general para activar una integración es:

1. Leer el doc y cumplir los **prerrequisitos** (cuentas, permisos, tokens).
2. Crear el **Secret manual** en `port-idp` con las claves `OCEAN__*` indicadas.
3. Copiar el `values.yaml` propuesto a `deployment/install/ocean-<x>/values.yaml`.
4. Copiar el ApplicationSet propuesto a `deployment/applicationsets/NN-ocean-<x>.yaml`.
5. Commit + push a la rama `laboratory` → la app-of-apps despliega todo automáticamente.
6. Verificar con los comandos de la sección de verificación de cada doc.

## Convención de numeración de ApplicationSets

| Rango | Uso |
|---|---|
| `00` | Infraestructura (namespace) |
| `10-13` | Integraciones custom de este repo (jfrog, orca, veracode, github-projects) |
| `20-26` | Integraciones oficiales de herramientas (GitHub, ArgoCD, SonarQube, Dynatrace, ServiceNow, Grafana, Confluence) |
| `30-32` | Nubes (AWS, Azure, GCP) |

## Notas importantes

- **Grafana y Confluence** no tienen integración Ocean oficial (verificado contra
  `github.com/port-labs/ocean/tree/main/integrations`): los docs implementan la
  alternativa real con `integration.type: custom` y documentan las demás opciones.
- Las integraciones de nubes están documentadas en modo **multi-cuenta** desde el
  inicio (AWS AssumeRole, Azure Management Group, GCP org-level bindings), con la
  variante mono-cuenta indicada en cada doc.
- Los parámetros no confirmados en la documentación oficial están marcados como
  "(verificar en la doc oficial)" — revisar antes de aplicar en producción.
