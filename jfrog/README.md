# Integración JFrog para Port (Ocean)

Integración del framework [Port Ocean](https://ocean.getport.io/) que exporta datos de la plataforma JFrog (Artifactory y Xray) hacia el catálogo de [Port](https://getport.io/).

## Descripción

Esta integración sincroniza los siguientes recursos de JFrog con Port y, además, soporta eventos en vivo mediante webhooks de JFrog Platform:

## Kinds soportados

| Kind             | Blueprint            | Origen (API JFrog)                              |
| ---------------- | -------------------- | ----------------------------------------------- |
| `project`        | `jfrogProject`       | `GET /access/api/v1/projects`                   |
| `repository`     | `jfrogRepository`    | `GET /artifactory/api/repositories`             |
| `build`          | `jfrogBuild`         | `GET /artifactory/api/build`                    |
| `artifact`       | `jfrogArtifact`      | `POST /artifactory/api/search/aql` (repos locales, paginado) |
| `xray_violation` | `jfrogXrayViolation` | `POST /xray/api/v1/violations` (paginado)       |

Notas:
- Si la instancia no tiene licencia de Projects (403/404), el kind `project` se omite con un warning.
- Si Xray no está disponible (400/403/404), el kind `xray_violation` se omite con un warning.
- Si no hay builds (404), el kind `build` se omite con un warning.

## Configuración

| Variable (spec)    | Variable de entorno                                  | Requerida | Descripción                                                                 |
| ------------------ | ---------------------------------------------------- | --------- | --------------------------------------------------------------------------- |
| `jfrogHostUrl`     | `OCEAN__INTEGRATION__CONFIG__JFROG_HOST_URL`         | Sí        | URL de la instancia de JFrog, por ejemplo `https://mycompany.jfrog.io`      |
| `jfrogAccessToken` | `OCEAN__INTEGRATION__CONFIG__JFROG_ACCESS_TOKEN`     | Sí        | Access token de JFrog con permisos de lectura (y lectura de Xray si aplica) |

Además, las variables estándar de Ocean (ver `.env.example`): `OCEAN__PORT__CLIENT_ID`, `OCEAN__PORT__CLIENT_SECRET`, `OCEAN__PORT__BASE_URL`, `OCEAN__EVENT_LISTENER`, `OCEAN__INTEGRATION__IDENTIFIER`, `OCEAN__INITIALIZE_PORT_RESOURCES`.

## Ejecución local

1. Instalar el CLI de Ocean:

   ```bash
   pip install "port-ocean[cli]"
   ```

2. Copiar `.env.example` a `.env` y completar las credenciales de Port y JFrog.

3. Desde la carpeta de la integración, ejecutar:

   ```bash
   ocean sail
   ```

   Alternativamente, para depurar con un IDE se puede ejecutar `python debug.py`.

## Docker

Construir y ejecutar la imagen:

```bash
docker build -t port-ocean-jfrog .
docker run --env-file .env -p 8000:8000 port-ocean-jfrog
```

## Despliegue con Helm

Se puede desplegar en Kubernetes con el chart genérico `port-labs/port-ocean`, sobreescribiendo la imagen con la de esta integración:

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm repo update

helm upgrade --install jfrog port-labs/port-ocean \
  --create-namespace --namespace port-ocean \
  --set port.clientId=$PORT_CLIENT_ID \
  --set port.clientSecret=$PORT_CLIENT_SECRET \
  --set initializePortResources=true \
  --set integration.identifier=jfrog \
  --set integration.type=jfrog \
  --set integration.eventListener.type=POLLING \
  --set integration.config.jfrogHostUrl=https://mycompany.jfrog.io \
  --set integration.secrets.jfrogAccessToken=$JFROG_ACCESS_TOKEN \
  --set image.repository=<mi-registry>/port-ocean-jfrog \
  --set image.tag=latest
```

## Webhooks de JFrog (eventos en vivo)

Para recibir eventos en vivo de artefactos y builds:

1. En JFrog Platform, ir a **Settings → Webhooks** (Administración → General → Webhooks).
2. Crear un webhook nuevo para el dominio **artifact** (eventos como `deployed`) y otro para el dominio **build** (eventos como `uploaded`).
3. En la URL del webhook, apuntar a la integración desplegada:

   ```
   https://<host-integracion>/integration/webhook
   ```

4. Guardar. JFrog enviará el payload con los campos `domain` y `data`, que la integración procesa y registra en Port automáticamente.

Nota: los campos del payload del webhook de **artifact** (`repo_key`, `path`, `name`, ...) pueden diferir levemente de los devueltos por la búsqueda AQL (por ejemplo, el `path` del webhook puede incluir el nombre del archivo o variar en su formato), por lo que un mismo artefacto podría generar identificadores ligeramente distintos entre el resync y el evento en vivo.

## Blueprints gestionados con Terraform

Si los blueprints de Port se gestionan con Terraform (u otra herramienta de IaC), configurar:

```
OCEAN__INITIALIZE_PORT_RESOURCES=false
```

De esta forma la integración no intentará crear/actualizar los blueprints ni el mapping por defecto al arrancar.
