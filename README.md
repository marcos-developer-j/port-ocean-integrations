# Integraciones Ocean para Port

Integraciones custom construidas sobre el framework [Port Ocean](https://ocean.port.io/) para sincronizar datos de herramientas externas al catálogo de Port.

> **Guía completa de implementación paso a paso: [IMPLEMENTACION.md](./IMPLEMENTACION.md)** — credenciales, Terraform, Docker, Helm, webhooks, scorecards y troubleshooting.

| Integración | Carpeta | Kinds | Live events | Auth |
|---|---|---|---|---|
| JFrog | [`jfrog/`](./jfrog) | `project`, `repository`, `build`, `artifact`, `xray_violation` | Webhook (artifact/build) | Bearer token |
| Orca Security | [`orca/`](./orca) | `asset`, `alert` | Webhook (alertas) | Token API |
| Veracode | [`veracode/`](./veracode) | `application`, `finding` | No (resync programado) | HMAC-SHA-256 |
| GitHub Projects | [`github-projects/`](./github-projects) | `project`, `project-item` | No (resync programado) | PAT (GraphQL) |

## Estructura de cada integración

```
<integracion>/
├── main.py                          # Handlers de resync (+ webhook si aplica)
├── client.py                        # Cliente HTTP async (httpx via Ocean)
├── pyproject.toml                   # Dependencias (poetry)
├── Dockerfile                       # Imagen para deploy
├── debug.py                         # Entry point para debugging local
├── .env.example                     # Variables de entorno de ejemplo
├── README.md                        # Documentación específica
└── .port/
    ├── spec.yaml                    # Definición de kinds y configuraciones
    └── resources/
        ├── blueprints.json          # Blueprints por defecto
        └── port-app-config.yml      # Mappings JQ (datos crudos → entities)
```

## Ejecución local

```bash
cd <integracion>
pip install "port-ocean[cli]"
cp .env.example .env        # completar credenciales
ocean sail
```

## Docker

```bash
cd <integracion>
docker build -t port-ocean-<integracion>:latest .
docker run --env-file .env -p 8000:8000 port-ocean-<integracion>:latest
```

## Kubernetes (Helm)

Se usa el chart genérico [`port-labs/port-ocean`](https://artifacthub.io/packages/helm/port-labs/port-ocean) con override de imagen (la imagen se construye desde el `Dockerfile` de cada integración y se publica en un registry propio):

```bash
helm repo add port-labs https://port-labs.github.io/helm-charts
helm upgrade --install <integracion> port-labs/port-ocean \
  --set port.clientId=$PORT_CLIENT_ID \
  --set port.clientSecret=$PORT_CLIENT_SECRET \
  --set initializePortResources=false \
  --set scheduledResyncInterval=120 \
  --set integration.identifier=<integracion> \
  --set integration.type=<integracion> \
  --set integration.eventListener.type=POLLING \
  --set image.repository=<registry>/port-ocean-<integracion> \
  --set image.tag=latest \
  --set-string integration.config.<clave>=<valor> \
  --set-string integration.secrets.<claveSensible>=<valor>
```

Para las integraciones con webhook (JFrog, Orca) exponer el servicio (ingress) y configurar en la herramienta origen la URL `https://<host>/integration/webhook`.

## Blueprints gestionados por Terraform

Los 11 blueprints de las integraciones están definidos en HCL en [`terraform/blueprints/`](./terraform/blueprints) (con su propio README de implementación). Terraform es la fuente de verdad:

1. Aplicar `terraform/blueprints/` para crear los blueprints (`jfrogRepository`, `orcaAlert`, `veracodeFinding`, `githubProject`, etc.) o importarlos si ya existen.
2. Ejecutar las integraciones con `OCEAN__INITIALIZE_PORT_RESOURCES=false` (o `initializePortResources=false` en Helm) para que no creen/modifiquen blueprints por su cuenta.
3. Habilitar `enable_service_relations=true` para agregar relaciones opcionales hacia el blueprint central `service` y habilitar scorecards de seguridad unificados (ej. "sin findings críticos de Veracode", "sin alertas hazardous de Orca").

## Notas por integración

- **JFrog**: requiere access token con permisos de lectura (y de Xray si se ingestan violaciones). El resync de `artifact` recorre solo repositorios locales vía AQL.
- **Orca**: la URL del API es regional (`https://api.orcasecurity.io`, `https://api.eu.orcasecurity.io`, ...). El webhook complementa el resync con alertas en tiempo real.
- **Veracode**: la API exige firma HMAC por request (por eso es integración con código y no no-code). Sin webhooks de salida: usar `scheduledResyncInterval` de 60-240 min.
- **GitHub Projects**: existe porque la integración GitHub oficial de Port no soporta Projects V2. Token clásico con scopes `read:project` + `read:org` (o fine-grained con lectura de Organization projects).
