# Port Ocean Confluence Integration

Integración custom de Port Ocean para sincronizar espacios y páginas de Confluence Cloud,
con conversión automática del contenido HTML a **Markdown** (la "visión" de convertir docs
de Confluence en READMEs).

## Qué sincroniza

| Kind | Blueprint | Descripción |
|------|-----------|-------------|
| `space` | `confluenceSpace` | Espacios de Confluence (global y personal) |
| `page` | `confluencePage` | Páginas con contenido convertido a Markdown |

## Características especiales

### Conversión HTML → Markdown

El campo `markdown` de cada página contiene el contenido convertido automáticamente:

- Headers (`<h1>`-`<h6>`) → `#` - `######`
- Listas → `- item`
- Código → `` `inline` `` y bloques con triple backtick
- Enlaces e imágenes
- Macros de Confluence (code, info, warning, note, tip, panel)
- Tablas (si markdownify está instalado)

Esto permite usar el contenido de Confluence como documentación en el catálogo de Port
o exportarlo como README.

## Prerequisitos

1. **Confluence Cloud** (no Server/Data Center — usa API v2)
2. **API Token de Atlassian**:
   - Ir a https://id.atlassian.com/manage-profile/security/api-tokens
   - Crear un token
   - El usuario debe tener permisos de lectura en los espacios a sincronizar

## Configuración

### Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `OCEAN__INTEGRATION__CONFIG__CONFLUENCE_BASE_URL` | URL del sitio, ej. `https://tuempresa.atlassian.net` |
| `OCEAN__INTEGRATION__CONFIG__CONFLUENCE_USERNAME` | Email de la cuenta Atlassian |
| `OCEAN__INTEGRATION__CONFIG__CONFLUENCE_API_TOKEN` | API Token (secreto) |
| `OCEAN__INTEGRATION__CONFIG__PAGE_SIZE` | Opcional: items por página (default: 50) |

### Secret de Kubernetes

```bash
kubectl create secret generic ocean-confluence-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__CONFLUENCE_BASE_URL='https://tuempresa.atlassian.net' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__CONFLUENCE_USERNAME='tu-email@empresa.com' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__CONFLUENCE_API_TOKEN='<ATLASSIAN_API_TOKEN>'
```

## Desarrollo local

```bash
# Copiar y configurar variables
cp .env.example .env
# Editar .env con tus credenciales

# Instalar dependencias
pip install port-ocean[cli] markdownify

# Ejecutar
ocean sail
```

## Build de imagen Docker

```bash
cd integrations/confluence
docker build -t port-ocean-confluence:local .

# Cargar en kind
kind load docker-image port-ocean-confluence:local --name port-ocean
```

## Blueprints

Los blueprints se crean automáticamente si `initializePortResources: true`, o se pueden
aplicar manualmente desde `.port/resources/blueprints.json`:

```bash
# Con Terraform (recomendado)
cd terraform/blueprints
terraform apply

# O vía API
curl -X POST "https://api.us.getport.io/v1/blueprints" \
  -H "Authorization: Bearer $PORT_TOKEN" \
  -H "Content-Type: application/json" \
  -d @.port/resources/blueprints.json
```

## Mapping

El mapping en `.port/resources/port-app-config.yml` define cómo se transforman los datos
de Confluence a entidades de Port. Se sube a Port automáticamente o vía:

```bash
curl -X PATCH "https://api.us.getport.io/v1/integration/confluence" \
  -H "Authorization: Bearer $PORT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": <contenido de port-app-config.yml en JSON>}'
```

## Limitaciones conocidas

- Solo Confluence Cloud (API v2). Server/Data Center usa API v1 diferente.
- La conversión de tablas complejas puede no ser perfecta.
- Macros personalizados no se convierten (se elimina el tag, se mantiene contenido).
- Imágenes: se genera la referencia markdown pero no se descargan los archivos.
