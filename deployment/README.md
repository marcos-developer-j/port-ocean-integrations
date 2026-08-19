# Deployment GitOps: kind + ArgoCD + ApplicationSets

Despliegue de las 4 integraciones Ocean siguiendo el patrón **app-of-apps → ApplicationSets con cluster generator → Applications multi-source**, con el chart oficial [`port-labs/port-ocean`](https://artifacthub.io/packages/helm/port-labs/port-ocean) (pinned a `0.23.4`) y values versionados en la rama de entorno **`laboratory`**.

```
deployment/
├── kind/cluster.yaml                       # Config del cluster kind local (nombre: port-ocean)
├── scripts/build-and-load.sh               # Build de imágenes Docker + carga en kind
├── bootstrap/
│   ├── root.yaml                           # App-of-apps: lo ÚNICO que se aplica a mano
│   └── cluster-laboratory.yaml             # Registro del cluster local en ArgoCD (con labels)
├── applicationsets/
│   ├── 00-namespace.yaml                   # Namespace port-idp (prune: false → protege Secrets manuales)
│   ├── 10-ocean-jfrog.yaml
│   ├── 11-ocean-orca.yaml
│   ├── 12-ocean-veracode.yaml
│   └── 13-ocean-github-projects.yaml
├── config/clusters.yaml                    # Inventario de clusters + labels requeridos por entorno
├── install/
│   ├── namespace/namespace.yaml            # Namespace port-idp
│   ├── ocean-jfrog/values.yaml             # Values por integración (SIN credenciales)
│   ├── ocean-orca/values.yaml
│   ├── ocean-veracode/values.yaml
│   └── ocean-github-projects/values.yaml
└── README.md
```

## Cómo funciona

1. **`bootstrap/root.yaml`** (app-of-apps) apunta a este repo, rama `laboratory`, path `deployment/` con `include: applicationsets/*.yaml` → ArgoCD aplica los ApplicationSets automáticamente.
2. Cada **ApplicationSet** usa un **cluster generator**: genera una Application por cada cluster registrado en ArgoCD cuyo Secret tenga los labels `project: port`, `environment: laboratory` y `cloud` (cualquier valor). Los labels requeridos están documentados en [`config/clusters.yaml`](config/clusters.yaml).
3. Las Applications generadas son **multi-source**: el chart `port-ocean 0.23.4` del repo Helm de port-labs + los values de `install/ocean-<x>/values.yaml` de este repo (`ref: values` → `$values/...`), rama `laboratory`.
4. **Credenciales**: los values usan `secret.create: false` + `secret.name` → el chart referencia (`envFrom`) un **Secret manual** que se crea una sola vez en `port-idp`. El ApplicationSet del namespace sincroniza **sin prune**, así que ArgoCD nunca borra esos Secrets.
5. `initializePortResources: false`: los blueprints los gestiona Terraform ([`../terraform/blueprints/`](../terraform/blueprints)) — aplicarlos **antes** del primer sync.
6. `eventListener: POLLING` + `scheduledResyncInterval` (60 GitHub Projects, 120 JFrog/Orca, 180 Veracode).
7. Rama por entorno: `laboratory` es la rama de este entorno. Para otro entorno se replica el ApplicationSet con otro selector/branch (y en `main` el namespace no se auto-sincroniza, ver `templatePatch`).

## Prerrequisitos

- Docker, [kind](https://kind.sigs.k8s.io/) `>= 0.20`, kubectl
- Credenciales de Port + de las herramientas a integrar (ver [`../IMPLEMENTACION.md`](../IMPLEMENTACION.md))

## Paso 1 — Cluster kind + ArgoCD

```bash
cd deployment
kind create cluster --config kind/cluster.yaml
kubectl create namespace argocd
kubectl apply -n argocd --server-side -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl wait --for=condition=available deployment --all -n argocd --timeout=300s

# Password inicial de "admin" + UI:
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
kubectl port-forward svc/argocd-server -n argocd 8080:443   # → https://localhost:8080
```

> Nota: `--server-side` es necesario porque los CRDs de ArgoCD superan el límite de annotations del apply client-side.

## Paso 2 — Construir y cargar las imágenes

Los values usan imágenes locales (`port-ocean-<integracion>:local`, `imagePullPolicy: Never`):

```bash
./scripts/build-and-load.sh                              # las 4
./scripts/build-and-load.sh port-ocean github-projects   # solo una
```

## Paso 3 — Rama de entorno `laboratory`

Los ApplicationSets y el root apuntan a la rama `laboratory` de este repo. Asegúrate de que exista y esté al día:

```bash
git push origin main
git push origin main:laboratory
```

Los ajustes de entorno (URLs, organización de GitHub, intervalos) se editan en `install/ocean-<x>/values.yaml` **en la rama `laboratory`**.

## Paso 4 — Crear los Secrets manuales

Una sola vez por cluster, en el namespace `port-idp` (crearlo si aún no existe: `kubectl create namespace port-idp`). Las claves siguen el formato de env vars de Ocean (`OCEAN__...`):

```bash
# Comunes a todas: OCEAN__PORT__CLIENT_ID / OCEAN__PORT__CLIENT_SECRET

kubectl -n port-idp create secret generic ocean-jfrog-credentials \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__JFROG_ACCESS_TOKEN='<JFROG_ACCESS_TOKEN>'

kubectl -n port-idp create secret generic ocean-orca-credentials \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__ORCA_API_TOKEN='<ORCA_API_TOKEN>'

kubectl -n port-idp create secret generic ocean-veracode-credentials \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__VERACODE_API_ID='<VERACODE_API_ID>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__VERACODE_API_SECRET='<VERACODE_API_SECRET>'

kubectl -n port-idp create secret generic ocean-github-projects-credentials \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__GITHUB_TOKEN='<GITHUB_TOKEN>'
```

Solo hace falta crear los Secrets de las integraciones que vayas a desplegar. Como el namespace se sincroniza con `prune: false`, ArgoCD nunca los borra.

## Paso 5 — Bootstrap

```bash
# 1. Registrar el cluster local con los labels que exige el cluster generator:
kubectl apply -f bootstrap/cluster-laboratory.yaml

# 2. Aplicar el app-of-apps (lo único que se aplica a mano):
kubectl apply -f bootstrap/root.yaml
```

A partir de aquí ArgoCD hace todo: root → ApplicationSets → Applications `port-namespace-in-cluster`, `port-ocean-<x>-in-cluster` → recursos en `port-idp`.

## Paso 6 — Verificar

```bash
kubectl get applicationsets -n argocd
kubectl get applications -n argocd
kubectl get pods -n port-idp
kubectl logs -n port-idp deploy/<releaseName>-port-ocean-deployment -f   # buscar "Resync finished successfully"
```

En la UI de ArgoCD: la app root, los 5 ApplicationSets y las apps generadas deben quedar `Synced` / `Healthy`.

## Ciclo de desarrollo

```bash
# Cambiar código en ../<integracion>/ y luego:
./scripts/build-and-load.sh port-ocean <integracion>
kubectl rollout restart deploy/<releaseName>-port-ocean-deployment -n port-idp
```

Cambios de configuración (values, ApplicationSets): commit + push a `laboratory` → ArgoCD sincroniza solo.

## Limpieza

```bash
kubectl delete -f bootstrap/root.yaml    # el finalizer limpia apps y recursos
kind delete cluster --name port-ocean    # borra todo el cluster
```

## Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| ApplicationSet no genera apps | Cluster sin registrar o labels incompletos | `kubectl get secret -n argocd -l argocd.argoproj.io/secret-type=cluster --show-labels`; aplicar `bootstrap/cluster-laboratory.yaml` |
| Pod en `CreateContainerConfigError` | Falta el Secret manual `ocean-<x>-credentials` | Crearlo (Paso 4) |
| Pod en `ErrImageNeverPull` | Imagen no cargada en kind | `./scripts/build-and-load.sh` y reiniciar el pod |
| App `Degraded`, pod en CrashLoop | Credenciales inválidas o config errónea en values | `kubectl logs`, corregir Secret o values (push a `laboratory`) |
| Root `OutOfSync` tras editar applicationsets | Cambios sin push a `laboratory` | Commit + push a la rama `laboratory` |
| ArgoCD no descarga el chart | Sin salida a internet desde el cluster | Verificar conectividad de Docker/kind |
