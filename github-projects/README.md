# Integración Port Ocean: GitHub Projects V2

Integración del framework [Port Ocean](https://ocean.getport.io/) que exporta a Port los **GitHub Projects V2** de una organización y sus **items** (issues, pull requests y draft issues), usando la **API GraphQL de GitHub**.

## ¿Por qué existe esta integración?

La integración oficial de GitHub para Ocean cubre repositorios, issues, pull requests, workflows, etc., pero **no soporta GitHub Projects V2** (los "nuevos" projects basados en la API GraphQL `projectsV2`). Esta integración complementa a la oficial exportando los tableros de proyecto y sus items para poder modelar la planificación (estados, iteraciones, campos personalizados como "Status") dentro de Port.

## Kinds soportados

| Kind           | Blueprint por defecto | Descripción                                                            |
| -------------- | --------------------- | ---------------------------------------------------------------------- |
| `project`      | `githubProject`       | Projects V2 de la organización (título, URL, estado, creador, fechas). |
| `project-item` | `githubProjectItem`   | Items de cada project: Issue, PullRequest o DraftIssue, enriquecidos con el campo `Status` y el project padre (`__project`). |

## Permisos del token de GitHub

Se necesita un token con acceso de lectura a los projects de la organización:

- **PAT clásico**: scopes `read:project` y `read:org`.
- **PAT fine-grained**: permiso de organización **Projects: Read** (Organization projects read). Debe estar autorizado para la organización que se quiere sincronizar.

## Configuración

| Parámetro (spec)     | Variable de entorno                                      | Requerido | Default                          | Descripción                                                  |
| -------------------- | -------------------------------------------------------- | --------- | -------------------------------- | ------------------------------------------------------------ |
| `githubToken`        | `OCEAN__INTEGRATION__CONFIG__GITHUB_TOKEN`               | Sí        | —                                | Token de GitHub con acceso de lectura a projects.            |
| `githubOrganization` | `OCEAN__INTEGRATION__CONFIG__GITHUB_ORGANIZATION`        | Sí        | —                                | Login de la organización de GitHub a sincronizar.            |
| `githubGraphqlUrl`   | `OCEAN__INTEGRATION__CONFIG__GITHUB_GRAPHQL_URL`         | No        | `https://api.github.com/graphql` | URL de la API GraphQL (cambiar para GitHub Enterprise Server). |

Además, las variables estándar de Ocean (`OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__EVENT_LISTENER`, etc.). Ver `.env.example`.

> Nota: los nombres camelCase del `spec.yaml` (por ejemplo `githubGraphqlUrl`) se acceden en snake_case dentro del código (`ocean.integration_config["github_graphql_url"]`).

> Si los blueprints los gestiona **Terraform** (u otro IaC), poner `OCEAN__INITIALIZE_PORT_RESOURCES=false` para que la integración no cree/actualice blueprints ni el mapping por defecto.

## Relación con la integración oficial de GitHub

Los items de tipo `ISSUE` y `PULL_REQUEST` exponen en `content` el **node id global de GitHub** (`content.id`), el mismo identificador que usa la API GraphQL para issues y pull requests. Si en tu organización tienes desplegada la integración GitHub oficial de Ocean y sus entidades de issue/PR usan ese mismo node id (o un identificador derivable de él) como `identifier`, puedes:

1. Añadir en Port una relación opcional en el blueprint `githubProjectItem` (por ejemplo `issue` → blueprint de issues de la integración oficial).
2. Mapearla en el `port-app-config.yml` de esta integración con `relations.issue: .content.id` (ajustando al formato de identifier que use tu blueprint de issues).

Al ser una relación `required: false`, los draft issues y los items sin contenido enlazado no fallarán.

## Ejecución local

```bash
pip install "port-ocean[cli]"
cd integrations/github-projects
copy .env.example .env   # y rellenar los valores (en Linux/macOS: cp)
ocean sail
```

También se puede depurar con `python debug.py` (usa el mismo arranque de Ocean).

## Docker

```bash
docker build -t github-projects-ocean .
docker run --env-file .env github-projects-ocean
```

## Despliegue con Helm

Se usa el chart genérico `port-ocean` de Port con override de imagen:

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm repo update

helm upgrade --install github-projects port-labs/port-ocean \
  --set port.clientId=<PORT_CLIENT_ID> \
  --set port.clientSecret=<PORT_CLIENT_SECRET> \
  --set initializePortResources=true \
  --set integration.identifier=github-projects \
  --set integration.type=github-projects \
  --set integration.eventListener.type=POLLING \
  --set integration.secrets.githubToken=<TOKEN> \
  --set integration.config.githubOrganization=<ORG> \
  --set image.repository=<REGISTRY>/github-projects-ocean \
  --set image.tag=<TAG>
```

(La imagen debe construirse a partir del `Dockerfile` de esta carpeta y publicarse en un registry accesible por el clúster.)

## Live events (limitación)

Esta integración funciona por **resync programado** (event listener `POLLING` o scheduled resyncs). Para recibir eventos en tiempo real haría falta una **GitHub App** con webhooks del evento `projects_v2_item`, algo que no está incluido en esta integración. Con el polling periódico los datos se mantienen sincronizados con la frecuencia configurada.
