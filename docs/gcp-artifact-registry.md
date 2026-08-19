# Alojar las imágenes custom en GCP Artifact Registry

> **Estado**: documentación pendiente de implementar. Hoy las imágenes custom
> (`port-ocean-jfrog`, `port-ocean-orca`, `port-ocean-veracode`,
> `port-ocean-github-projects`) se construyen localmente con
> `scripts/build-and-load.sh` y se cargan en el cluster kind con
> `kind load docker-image` (por eso `imagePullPolicy: Never`).
> Este documento describe los pasos exactos para migrar ese flujo a
> **GCP Artifact Registry** y dejar el ciclo 100% GitOps.

## Qué se gana con la migración

- Se elimina el paso manual `build-and-load.sh` + `kind load` por cada cambio.
- Cualquier cluster (kind, GKE, EKS, on-prem) puede hacer pull de la misma imagen.
- Tags versionados (`:0.1.0`, `:sha-abc123`) en lugar de `:local`, con trazabilidad real.
- ArgoCD despliega una nueva versión solo cambiando el tag en `install/ocean-<x>/values.yaml`.

## Prerequisitos

- Proyecto de GCP con facturación habilitada (`PROJECT_ID`).
- `gcloud` CLI instalado y autenticado (`gcloud auth login`).
- API de Artifact Registry habilitada.
- Permisos: `roles/artifactregistry.admin` (o al menos `writer`) para quien hace push.
- Docker local funcionando (para build y push).

## Paso 1 — Crear el repositorio en Artifact Registry

```bash
export PROJECT_ID="mi-proyecto-gcp"
export REGION="us-central1"          # elegir la región más cercana
export REPO="port-ocean"

gcloud services enable artifactregistry.googleapis.com --project "$PROJECT_ID"

gcloud artifacts repositories create "$REPO" \
  --repository-format=docker \
  --location="$REGION" \
  --description="Imágenes custom de integraciones Port Ocean" \
  --project="$PROJECT_ID"
```

El registry resultante es: `us-central1-docker.pkg.dev/mi-proyecto-gcp/port-ocean`

## Paso 2 — Autenticar Docker contra Artifact Registry

```bash
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
```

Esto agrega un `credHelper` en `~/.docker/config.json` para ese dominio.

## Paso 3 — Build, tag y push de las 4 imágenes

Desde `integrations/`:

```bash
export AR="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
export TAG="0.1.0"    # versionar: nunca usar :local ni :latest

for i in jfrog orca veracode github-projects; do
  docker build -t "${AR}/port-ocean-${i}:${TAG}" "./${i}"
  docker push "${AR}/port-ocean-${i}:${TAG}"
done
```

> Alternativa sin Docker local: `gcloud builds submit --tag "${AR}/port-ocean-${i}:${TAG}" ./${i}`
> (usa Cloud Build; requiere `cloudbuild.googleapis.com` habilitada).

## Paso 4 — Cambios en los values de deployment

En cada `deployment/install/ocean-<x>/values.yaml` cambiar el bloque de imagen.

Antes (flujo kind local):

```yaml
imageRegistry: docker.io/library
image: "port-ocean-jfrog:local"
imagePullPolicy: Never
```

Después (Artifact Registry):

```yaml
imageRegistry: us-central1-docker.pkg.dev/mi-proyecto-gcp/port-ocean
image: "port-ocean-jfrog:0.1.0"
imagePullPolicy: IfNotPresent

# Solo necesario en clusters FUERA de GCP (kind, on-prem, otras nubes):
imagePullSecrets:
  - name: gcp-artifact-registry
```

El chart `port-ocean` 0.23.4 ya soporta `imagePullSecrets` (lista vacía por defecto),
así que no hace falta ningún cambio en el chart ni en los ApplicationSets:
solo commit + push a la rama `laboratory` y ArgoCD sincroniza.

## Paso 5 — Pull secret (clusters fuera de GCP, ej. kind)

Artifact Registry es privado por defecto. Para que kubelet pueda hacer pull
desde un cluster que no es GKE se necesita una Service Account de GCP con
permiso de lectura y un Secret de tipo `docker-registry`:

```bash
# 1. Crear la SA de solo lectura
gcloud iam service-accounts create ar-reader \
  --display-name="Artifact Registry reader (pull de imágenes)" \
  --project="$PROJECT_ID"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:ar-reader@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"

# 2. Generar la key JSON (guardarla fuera del repo, ej. deployment/secrets-local/)
gcloud iam service-accounts keys create ar-reader-key.json \
  --iam-account="ar-reader@${PROJECT_ID}.iam.gserviceaccount.com"

# 3. Crear el pull secret en el namespace port-idp
kubectl create secret docker-registry gcp-artifact-registry \
  --namespace port-idp \
  --docker-server="${REGION}-docker.pkg.dev" \
  --docker-username=_json_key \
  --docker-password="$(cat ar-reader-key.json)" \
  --docker-email=unused@example.com
```

Notas:

- El usuario es literalmente `_json_key` y el password es el **contenido completo**
  del JSON de la key.
- Este Secret es manual, igual que los `ocean-<x>-credentials`: el ApplicationSet
  del namespace tiene `prune: false`, así que ArgoCD no lo borra.
- **Nunca** commitear `ar-reader-key.json` (usar `deployment/secrets-local/`,
  que ya está en `.gitignore`).
- Las keys de SA no expiran pero conviene rotarlas; alternativa de corta duración:
  `--docker-username=oauth2accesstoken --docker-password="$(gcloud auth print-access-token)"`
  (expira en ~1h, solo útil para pruebas puntuales).

## Paso 6 — Caso GKE (sin pull secret)

Si el cluster es GKE en el mismo proyecto (o con permisos cruzados), **no hace
falta pull secret**: basta con dar `roles/artifactregistry.reader` a la service
account de los nodos (por defecto la Compute Engine default SA) o, mejor,
usar Workload Identity Federation. En ese caso se omite el bloque
`imagePullSecrets` en los values.

```bash
# SA de nodos de GKE (ejemplo con la default)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')-compute@developer.gserviceaccount.com" \
  --role="roles/artifactregistry.reader"
```

## Paso 7 — Verificación

```bash
# El pod debe hacer pull desde AR (ya no ErrImageNeverPull / imagen local)
kubectl -n port-idp get pods
kubectl -n port-idp describe pod -l app.kubernetes.io/instance=jfrog | grep -A3 "Events:"

# Confirmar la imagen en uso
kubectl -n port-idp get deploy -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
```

## Ciclo de desarrollo resultante

1. Cambio de código en `integrations/<x>/`.
2. `docker build` + `docker push` con un tag nuevo (ej. `0.1.1`).
3. Actualizar el tag en `deployment/install/ocean-<x>/values.yaml`.
4. Commit + push a `laboratory`.
5. ArgoCD detecta el cambio y hace rollout automático. Fin.

(Opcional a futuro: un workflow de GitHub Actions con
[Workload Identity Federation](https://github.com/google-github-actions/auth)
que haga build+push y bump del tag automáticamente en cada merge.)

## Resumen de cambios por archivo

| Archivo | Cambio |
|---|---|
| `deployment/install/ocean-jfrog/values.yaml` | `imageRegistry`, `image` con tag versionado, `imagePullPolicy: IfNotPresent`, `imagePullSecrets` |
| `deployment/install/ocean-orca/values.yaml` | ídem |
| `deployment/install/ocean-veracode/values.yaml` | ídem |
| `deployment/install/ocean-github-projects/values.yaml` | ídem |
| Secret `gcp-artifact-registry` (namespace `port-idp`) | nuevo, manual (solo clusters fuera de GCP) |
| ApplicationSets / bootstrap | **sin cambios** |
