# Integración Orca Security para Port (Ocean)

Integración del framework [Port Ocean](https://ocean.getport.io) que exporta datos de **Orca Security** hacia tu catálogo de [Port](https://getport.io): activos cloud y alertas de vulnerabilidades/riesgos, con soporte de webhooks para ingesta de alertas en tiempo real.

## Kinds soportados

| Kind    | Descripción                                             | Blueprint   |
| ------- | ------------------------------------------------------- | ----------- |
| `asset` | Activos cloud descubiertos por Orca (`/api/assets`)     | `orcaAsset` |
| `alert` | Alertas de seguridad y vulnerabilidades (`/api/alerts`) | `orcaAlert` |

## Configuración

| Parámetro (spec)          | Variable de entorno                              | Requerido | Default                      | Descripción                                    |
| ------------------------- | ------------------------------------------------ | --------- | ---------------------------- | ---------------------------------------------- |
| `orcaApiUrl`              | `OCEAN__INTEGRATION__CONFIG__ORCA_API_URL`       | No        | `https://api.orcasecurity.io` | URL base de la API de Orca (según región)     |
| `orcaApiToken`            | `OCEAN__INTEGRATION__CONFIG__ORCA_API_TOKEN`     | Sí        | —                            | Token de API de Orca Security (sensible)       |

### URLs regionales de Orca

| Región | URL base                        |
| ------ | ------------------------------- |
| US     | `https://api.orcasecurity.io`   |
| EU     | `https://api.eu.orcasecurity.io` |

> El token de API se genera en Orca: **Settings → Users & Permissions → API Tokens** (o equivalente según tu versión de la consola). La integración envía el header `Authorization: Token <token>`.

## Ejecución local

1. Copia `.env.example` a `.env` y completa las credenciales de Port y de Orca.
2. Instala el CLI de Ocean y levanta la integración:

```bash
pip install "port-ocean[cli]"
ocean sail
```

También puedes ejecutar `python debug.py` para lanzar la integración en modo debug.

## Docker

```bash
docker build -t port-ocean-orca .
docker run --env-file .env -p 8000:8000 port-ocean-orca
```

## Helm (Kubernetes)

Usa el chart oficial `port-labs/port-ocean` haciendo override de la imagen:

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm repo update

helm upgrade --install orca port-labs/port-ocean \
  --set port.clientId=$PORT_CLIENT_ID \
  --set port.clientSecret=$PORT_CLIENT_SECRET \
  --set initializePortResources=true \
  --set integration.identifier=orca \
  --set integration.type=orca \
  --set integration.eventListener.type=POLLING \
  --set integration.config.orcaApiUrl="https://api.orcasecurity.io" \
  --set integration.secrets.orcaApiToken=$ORCA_API_TOKEN \
  --set image.repository=<tu-registro>/port-ocean-orca \
  --set image.tag=latest
```

## Webhook de alertas en tiempo real

Además del resync periódico, la integración expone el endpoint `POST /integration/webhook` para recibir alertas de Orca en tiempo real.

### Configurar el webhook en Orca

1. En la consola de Orca ve a **Settings → Connections → Integrations → Webhooks** y pulsa **Configure/Create**.
2. Configura la URL apuntando a tu integración desplegada:

   ```
   https://<host-integracion>/integration/webhook
   ```

3. Deja el campo **API Key** vacío.
4. Guarda la integración.

### Probar el webhook

1. En Orca, abre **Alerts** y selecciona una alerta.
2. Pulsa **Take Action → Notifications → Send to webhook**.
3. Elige el webhook configurado y envía; la alerta debería aparecer/actualizarse en Port en segundos.

## Blueprints y Terraform

Por defecto (`OCEAN__INITIALIZE_PORT_RESOURCES=true`) la integración crea automáticamente los blueprints `orcaAsset` y `orcaAlert` y el mapping por defecto en Port.

> **Nota:** si los blueprints los gestionas con **Terraform** (u otra herramienta de IaC), establece `OCEAN__INITIALIZE_PORT_RESOURCES=false` para evitar conflictos.

## Estructura del proyecto

```
integrations/orca/
├── main.py                          # Handlers de resync y webhook
├── client.py                        # Cliente HTTP async de la API de Orca
├── debug.py                         # Ejecución local en modo debug
├── pyproject.toml
├── Dockerfile
├── .env.example
└── .port/
    ├── spec.yaml                    # Especificación de la integración
    └── resources/
        ├── blueprints.json          # Blueprints por defecto
        └── port-app-config.yml      # Mapping por defecto
```
