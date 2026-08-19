# Integración Port Ocean — Veracode

Integración construida sobre el framework [Port Ocean](https://ocean.getport.io/) que exporta a Port los **perfiles de aplicación** y los **hallazgos de seguridad (findings)** de Veracode, usando las APIs REST de Veracode firmadas con HMAC.

## ¿Por qué una integración custom y no una no-code?

Veracode no usa API keys estáticas ni tokens Bearer: cada request debe ir firmada con **HMAC-SHA-256** siguiendo el esquema propietario `VERACODE-HMAC-SHA-256`. La firma se calcula a partir del `id` de credenciales, el host, la ruta (incluyendo query string), el método HTTP, un timestamp en milisegundos y un nonce aleatorio, por lo que **cambia en cada request** y no puede configurarse como una cabecera estática en una integración genérica/no-code. Por eso esta integración implementa una clase `httpx.Auth` propia (`hmac_auth.py`) y pasa la autenticación **por request** al cliente HTTP compartido de Ocean.

## Generar credenciales API en Veracode

1. Inicia sesión en la plataforma de Veracode.
2. Ve a tu perfil de usuario y abre **API Credentials** (Configuración de cuenta → API Credentials).
3. Pulsa **Generate API Credentials**. Obtendrás un **API ID** y un **API Secret Key** (ambos en formato hexadecimal).
4. Guarda el secret en un lugar seguro: solo se muestra una vez.
5. El usuario (o cuenta de servicio) debe tener permisos de API sobre las aplicaciones que quieras ingestar (se recomienda una cuenta de servicio con el rol *Results API*).

> Si tu organización usa una instancia regional (por ejemplo la región europea), ajusta la URL base de la API (`https://api.veracode.eu`, etc.).

## Kinds soportados

| Kind | Descripción | Endpoint |
|---|---|---|
| `application` | Perfiles de aplicación de Veracode | `GET /appsec/v1/applications` |
| `finding` | Hallazgos de seguridad por aplicación y tipo de escaneo | `GET /appsec/v2/applications/{guid}/findings` |

Cada `finding` se enriquece con la clave `__application` (`guid` y `name` de la aplicación padre) para poder construir el identificador y la relación en el mapping.

## Selector `scanTypes`

El kind `finding` soporta un selector custom `scanTypes` en el mapping (`port-app-config.yml`) para elegir qué tipos de escaneo se ingestan: `STATIC`, `DYNAMIC`, `SCA` y/o `MANUAL`. Por defecto: `STATIC` y `SCA`.

```yaml
resources:
  - kind: finding
    selector:
      query: "true"
      scanTypes:
        - "STATIC"
        - "SCA"
        # - "DYNAMIC"
        # - "MANUAL"
```

Si una aplicación devuelve `403`/`404` para un tipo de escaneo (por ejemplo, sin licencia SCA), la integración lo registra como warning y continúa con la siguiente.

## Configuración

| Variable de entorno | Configuración | Requerida | Descripción |
|---|---|---|---|
| `OCEAN__INTEGRATION__CONFIG__VERACODE_API_BASE` | `veracodeApiBase` | No (default `https://api.veracode.com`) | URL base de la API de Veracode (usar host regional si aplica) |
| `OCEAN__INTEGRATION__CONFIG__VERACODE_API_ID` | `veracodeApiId` | Sí | API ID de las credenciales de Veracode (hex) |
| `OCEAN__INTEGRATION__CONFIG__VERACODE_API_SECRET` | `veracodeApiSecret` | Sí | API Secret Key de las credenciales de Veracode (hex) |
| `OCEAN__PORT__CLIENT_ID` | — | Sí | Client ID de Port |
| `OCEAN__PORT__CLIENT_SECRET` | — | Sí | Client Secret de Port |
| `OCEAN__EVENT_LISTENER` | — | Sí | Por ejemplo `{"type": "POLLING"}` |
| `OCEAN__INITIALIZE_PORT_RESOURCES` | — | No | `true` crea blueprints y mapping por defecto al arrancar |

> **Nota (Terraform):** si los blueprints se gestionan con Terraform (u otra IaC), pon `OCEAN__INITIALIZE_PORT_RESOURCES=false` para que la integración no cree ni modifique los blueprints al arrancar.

## Ejecución local

```bash
pip install "port-ocean[cli]"
cd integrations/veracode
cp .env.example .env   # y rellena las credenciales
ocean sail
```

También puedes lanzar `debug.py` desde tu IDE para depurar con breakpoints.

## Docker

```bash
docker build -t veracode-ocean .
docker run --env-file .env veracode-ocean
```

## Despliegue con Helm

Usa el chart genérico `port-labs/port-ocean` con override de la imagen custom:

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm repo update

helm upgrade --install veracode port-labs/port-ocean \
  --set port.clientId=$PORT_CLIENT_ID \
  --set port.clientSecret=$PORT_CLIENT_SECRET \
  --set initializePortResources=true \
  --set scheduledResyncInterval=120 \
  --set integration.identifier=veracode \
  --set integration.type=veracode \
  --set integration.eventListener.type=POLLING \
  --set integration.config.veracodeApiBase=https://api.veracode.com \
  --set integration.secrets.veracodeApiId=$VERACODE_API_ID \
  --set integration.secrets.veracodeApiSecret=$VERACODE_API_SECRET \
  --set image.repository=<tu-registro>/veracode-ocean \
  --set image.tag=latest
```

## Intervalo de resincronización recomendado

Veracode **no ofrece webhooks de salida robustos**, por lo que la ingesta se basa en resyncs programados. Se recomienda configurar `scheduledResyncInterval` entre **1 y 4 horas** (60–240 minutos), según el volumen de aplicaciones/hallazgos y los rate limits de tu cuenta.

## Estructura del proyecto

```
veracode/
├── .port/
│   ├── spec.yaml
│   └── resources/
│       ├── blueprints.json
│       └── port-app-config.yml
├── client.py          # Cliente HTTP async con paginación
├── hmac_auth.py       # Firma HMAC-SHA-256 de Veracode para httpx
├── integration.py     # Selector custom scanTypes
├── main.py            # Handlers de resync
├── debug.py
├── Dockerfile
├── pyproject.toml
└── .env.example
```
