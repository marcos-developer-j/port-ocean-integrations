# Ingress para Webhooks de integraciones Ocean

Este folder contiene **ejemplos** de cómo exponer las integraciones Ocean para recibir
webhooks en tiempo real. **NO se aplican automáticamente** — son referencias para
adaptar a tu entorno.

## Arquitectura

```
Internet (GitHub, SonarQube, Dynatrace, etc.)
         │
         ▼
┌─────────────────┐
│ Túnel a internet│  ngrok / cloudflared / IP pública
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Ingress NGINX   │  Enruta por path: /webhook/github → svc github
└────────┬────────┘
         │
    ┌────┴────┬─────────┬─────────┐
    ▼         ▼         ▼         ▼
 github    argocd   sonarqube   ...
  :8000     :8000     :8000
```

## Paso 1 — Instalar Ingress Controller

### Opción A: kind (desarrollo local)

```bash
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml

# Esperar a que esté listo
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s
```

### Opción B: Helm (cualquier cluster)

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace
```

## Paso 2 — Aplicar el Ingress

```bash
kubectl apply -f ingress-ocean-webhooks.yaml
```

Esto crea rutas:
- `/webhook/github` → Service `github-port-ocean:8000`
- `/webhook/argocd` → Service `argocd-port-ocean:8000`
- `/webhook/sonarqube` → Service `sonarqube-port-ocean:8000`
- etc.

## Paso 3 — Exponer a Internet

Los servicios externos (GitHub, SonarQube, etc.) necesitan enviar webhooks a una URL pública.

### Opción A: ngrok (desarrollo/pruebas)

```bash
# Instalar ngrok: https://ngrok.com/download
ngrok http 80

# Salida:
# Forwarding: https://abc123.ngrok.io -> http://localhost:80
```

Tu URL pública es `https://abc123.ngrok.io`. Los webhooks irían a:
- `https://abc123.ngrok.io/webhook/github`
- `https://abc123.ngrok.io/webhook/sonarqube`

### Opción B: cloudflared (Cloudflare Tunnel, gratis)

```bash
# Instalar: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/
cloudflared tunnel --url http://localhost:80
```

### Opción C: LoadBalancer real (nube)

Si tu cluster tiene un LoadBalancer (GKE, EKS, AKS), el Ingress Controller
obtiene una IP pública automáticamente:

```bash
kubectl get svc -n ingress-nginx ingress-nginx-controller
# EXTERNAL-IP será tu IP pública
```

## Paso 4 — Actualizar los Values de las integraciones

Cambia `eventListener.type` de `POLLING` a `WEBHOOK` y agrega `appHost`:

```yaml
# deployment/install/ocean-github/values.yaml
integration:
  identifier: github
  type: github-ocean
  eventListener:
    type: WEBHOOK    # <- cambiar de POLLING
  config:
    githubOrganization: "mi-org"
    appHost: "https://abc123.ngrok.io/webhook/github"  # <- agregar
```

Commit, push, y ArgoCD actualizará la integración.

## Paso 5 — Configurar webhooks en los servicios externos

Cada servicio tiene su propia forma de configurar webhooks:

### GitHub
1. Organización → Settings → Webhooks → Add webhook
2. Payload URL: `https://abc123.ngrok.io/webhook/github`
3. Content type: `application/json`
4. Events: según lo que quieras sincronizar (push, PR, issues, etc.)

### SonarQube
1. Administration → Configuration → Webhooks
2. URL: `https://abc123.ngrok.io/webhook/sonarqube`

### ArgoCD
ArgoCD notifica a la integración automáticamente si configuras `appHost`.

### Dynatrace
1. Settings → Integration → Problem notifications
2. Webhook URL: `https://abc123.ngrok.io/webhook/dynatrace`

## Integraciones que soportan webhooks

| Integración | eventListener.type | Webhooks automáticos |
|-------------|-------------------|----------------------|
| GitHub | `WEBHOOK` | Sí (con permisos `admin:org_hook`) |
| ArgoCD | `WEBHOOK` | Sí (usa API de ArgoCD) |
| SonarQube | `WEBHOOK` | No (configurar manualmente) |
| Dynatrace | `WEBHOOK` | No (configurar manualmente) |
| ServiceNow | `WEBHOOK` | No (crear Business Rule) |
| Confluence | `POLLING` | No soporta webhooks |
| Grafana | `POLLING` | Solo alertas (vía webhook de Port) |
| AWS/Azure/GCP | `POLLING` | Usar EventBridge/Event Grid/Pub-Sub (fuera de Ocean) |

## Notas importantes

1. **POLLING sigue funcionando**: Aunque uses webhooks, el resync periódico
   (`scheduledResyncInterval`) sigue activo como backup.

2. **Seguridad**: En producción, configura:
   - TLS en el Ingress (cert-manager)
   - Webhook secrets para validar firmas (GitHub, etc.)
   - Network policies

3. **kind y puertos**: El Ingress NGINX para kind usa `hostPort` 80/443.
   Si esos puertos están ocupados, el pod no arrancará.

4. **ngrok gratis**: El dominio cambia cada vez que reinicias. Para un
   dominio fijo, necesitas ngrok de pago o cloudflared con dominio propio.
