# Integración Ocean: AWS (multi-cuenta con AssumeRole)

> Integración **OFICIAL** del framework Ocean de Port. Verificada en el repositorio oficial
> [port-labs/ocean/integrations/aws](https://github.com/port-labs/ocean/tree/main/integrations/aws)
> (`.port/spec.yaml`) y en la documentación oficial de Port
> ([AWS on-premise](https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/aws/)).

**Nota sobre versiones (investigado en docs.port.io):** Port mantiene actualmente DOS integraciones AWS:

| Integración | `integration.type` | Despliegue | Estado |
|---|---|---|---|
| **AWS Self Hosted** ("AWS on-premise") | `aws` | Helm, Docker, CI/CD, Terraform (ECS) | Vigente para self-hosted. **Es la que usamos en este repo (Helm + ArgoCD).** |
| **AWS Hosted by Port** | `aws-v3` | Solo SaaS (hosted by Port); el spec oficial declara `disableDefaultInstallationMethods: true` y `saas.enabled: true` | Es la recomendada si quieres que Port hospede la integración; NO ofrece método Helm estándar documentado, por lo que no encaja en nuestro GitOps |

Este documento cubre la integración **`aws`** (self-hosted vía chart `port-ocean`), que es la vía oficial soportada para Kubernetes/Helm/ArgoCD, e incluye al final notas sobre `aws-v3` y la vía Terraform.

## Qué sincroniza (kinds y blueprints por defecto)

Kinds por defecto según el `spec.yaml` oficial de la integración `aws`:

| Kind (AWS Cloud Control / API) | Blueprint en Port | Contenido |
|---|---|---|
| `AWS::Organizations::Account` | `awsAccount` | Cuentas de la organización descubiertas |
| `AWS::S3::Bucket` | `cloudResource` | Buckets S3 (multi-región) |
| `AWS::EC2::Instance` | `cloudResource` | Instancias EC2 |
| `AWS::ECS::Cluster` | `cloudResource` | Clusters ECS |

Con `initializePortResources: true` los blueprints (`awsAccount`, `cloudResource`) y el mapping por defecto se crean automáticamente en Port en el primer arranque. La integración usa la **AWS Cloud Control API** (`cloudformation:ListResources` / `cloudformation:GetResource`), por lo que puedes añadir al mapping prácticamente cualquier tipo `AWS::*::*` soportado por Cloud Control.

## Qué necesitas

- Cluster Kubernetes con ArgoCD y el app-of-apps de este repo ya sincronizando (`deployment/bootstrap/root.yaml` → `deployment/applicationsets/*.yaml`).
- Cluster registrado en ArgoCD con labels `project: port`, `environment: laboratory` y label `cloud` presente (cualquier valor).
- Namespace destino `port-idp` (lo crea el ApplicationSet con `CreateNamespace=true`).
- Credenciales de Port (Client ID / Client Secret): Port UI → icono `...` (arriba derecha) → *Credentials*. Región US: `https://api.us.getport.io`.
- **AWS Organizations habilitado** (para multi-cuenta) y acceso administrativo a:
  - La cuenta "de integración" (donde viven las credenciales que usa el pod).
  - La cuenta **root/management** de la organización (para crear el rol de delegación).
  - Cada cuenta miembro que quieras sincronizar (o permisos para desplegar StackSets).
- AWS CLI v2 configurada (`aws sts get-caller-identity` debe funcionar).
- `kubectl` apuntando al cluster de laboratorio.

## Arquitectura multi-cuenta

Mecanismo: **cross-account AssumeRole**. El pod de la integración se autentica en la *cuenta de integración* (con Access Keys de un IAM User, o IRSA si el cluster corre en EKS). Desde ahí:

1. Asume el rol `organizationRoleArn` en la cuenta **root** de AWS Organizations para **listar las cuentas** de la organización.
2. Por cada cuenta miembro descubierta, asume un rol con nombre fijo `accountReadRoleName` (por defecto `AwsPortOceanIntegrationReadOnlyRole`) que debe existir **con el mismo nombre** en cada cuenta.
3. Consulta las regiones habilitadas de cada cuenta (`account:ListRegions`) y lee los recursos vía Cloud Control API.

```
                          ┌────────────────────────────────┐
                          │  Cuenta ROOT (management)      │
                          │  Rol: PortOceanOrgRole         │
                    ┌────▶│  organizations:List*/Describe* │
                    │     └────────────────────────────────┘
 ┌───────────────┐  │ sts:AssumeRole (organizationRoleArn)
 │ K8s (port-idp)│  │
 │ pod ocean-aws │──┤
 │ IAM User /    │  │ sts:AssumeRole (accountReadRoleName, mismo nombre en todas)
 │ IRSA          │  │     ┌────────────────────────────────┐
 └───────────────┘  ├────▶│ Cuenta miembro A               │
                    │     │ Rol: AwsPortOceanIntegration-  │
                    │     │      ReadOnlyRole (ReadOnly)   │
                    │     └────────────────────────────────┘
                    │     ┌────────────────────────────────┐
                    └────▶│ Cuenta miembro B               │
                          │ Rol: AwsPortOceanIntegration-  │
                          │      ReadOnlyRole (ReadOnly)   │
                          └────────────────────────────────┘
```

Parámetros que activan el modo multi-cuenta:

- `organizationRoleArn` — ARN del rol de delegación en la cuenta root.
- `accountReadRoleName` — **nombre** (no ARN) del rol de lectura replicado en cada cuenta miembro. Default oficial: `AwsPortOceanIntegrationReadOnlyRole`.

> Importante: las regiones se evalúan por cuenta; una región debe estar habilitada en cada cuenta concreta para producir resultados allí.

## Paso 1 — Preparar credenciales en AWS

### 1.1 IAM User de la integración (cuenta de integración)

```bash
# Variables
INTEGRATION_ACCOUNT_ID=111111111111
ROOT_ACCOUNT_ID=999999999999
READ_ROLE_NAME=AwsPortOceanIntegrationReadOnlyRole
ORG_ROLE_NAME=PortOceanOrgRole

# 1) Crear el usuario
aws iam create-user --user-name port-ocean-aws

# 2) Política del usuario/rol de integración: lectura + AssumeRole a los roles cross-account
cat > port-ocean-integration-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadLocalAccount",
      "Effect": "Allow",
      "Action": [
        "account:ListRegions",
        "cloudformation:ListResources",
        "cloudformation:GetResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AssumeCrossAccountRoles",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": [
        "arn:aws:iam::999999999999:role/PortOceanOrgRole",
        "arn:aws:iam::*:role/AwsPortOceanIntegrationReadOnlyRole"
      ]
    }
  ]
}
EOF

aws iam put-user-policy \
  --user-name port-ocean-aws \
  --policy-name PortOceanIntegrationPolicy \
  --policy-document file://port-ocean-integration-policy.json

# 3) Adjuntar además ReadOnlyAccess gestionada (recomendación de la doc oficial
#    para que la cuenta local también se sincronice completa)
aws iam attach-user-policy \
  --user-name port-ocean-aws \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

# 4) Generar Access Keys (guárdalas, solo se muestran una vez)
aws iam create-access-key --user-name port-ocean-aws
```

> Alternativa recomendada en EKS: en lugar de Access Keys, usar **IRSA** (IAM Role for Service Account) y en el chart `podServiceAccount.name` apuntando al ServiceAccount anotado con el rol. En ese caso NO se definen `awsAccessKeyId`/`awsSecretAccessKey`.

### 1.2 Rol de organización (cuenta ROOT/management)

Ejecutar con credenciales de la cuenta root:

```bash
# Trust policy: confía en el usuario/rol de la cuenta de integración
cat > org-role-trust.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${INTEGRATION_ACCOUNT_ID}:user/port-ocean-aws"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name ${ORG_ROLE_NAME} \
  --assume-role-policy-document file://org-role-trust.json

# Permisos: enumerar la organización y metadatos de cuentas
cat > org-role-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "organizations:Describe*",
        "organizations:List*",
        "account:GetAlternateContact",
        "account:GetContactInformation",
        "account:ListRegions"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name ${ORG_ROLE_NAME} \
  --policy-name PortOceanOrgReadPolicy \
  --policy-document file://org-role-policy.json
```

El ARN resultante (`arn:aws:iam::999999999999:role/PortOceanOrgRole`) es el valor de `organizationRoleArn`.

## Paso 2 — Configurar multi-cuenta (rol de lectura en CADA cuenta miembro)

En **cada** cuenta miembro debe existir un rol con el MISMO nombre (`accountReadRoleName`). Manualmente por cuenta:

```bash
# Ejecutar con credenciales de cada cuenta miembro
cat > read-role-trust.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${INTEGRATION_ACCOUNT_ID}:user/port-ocean-aws"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

aws iam create-role \
  --role-name ${READ_ROLE_NAME} \
  --assume-role-policy-document file://read-role-trust.json

# Lectura total (o restringe a tipos concretos para mínimo privilegio)
aws iam attach-role-policy \
  --role-name ${READ_ROLE_NAME} \
  --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess

# Permisos Cloud Control + regiones (necesarios aunque uses política restringida)
cat > read-role-extra.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "account:ListRegions",
        "cloudformation:ListResources",
        "cloudformation:GetResource"
      ],
      "Resource": "*"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name ${READ_ROLE_NAME} \
  --policy-name PortOceanCloudControlPolicy \
  --policy-document file://read-role-extra.json
```

### Despliegue masivo con CloudFormation StackSets (recomendado para muchas cuentas)

Desde la cuenta root, con StackSets service-managed (se auto-despliega a toda la OU/organización, incluidas cuentas futuras):

```bash
cat > port-read-role-template.yaml <<'EOF'
AWSTemplateFormatVersion: "2010-09-09"
Description: Rol de lectura Port Ocean para cuentas miembro
Parameters:
  IntegrationPrincipalArn:
    Type: String
Resources:
  PortOceanReadRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: AwsPortOceanIntegrationReadOnlyRole
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Ref IntegrationPrincipalArn
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/ReadOnlyAccess
      Policies:
        - PolicyName: PortOceanCloudControl
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: Allow
                Action:
                  - account:ListRegions
                  - cloudformation:ListResources
                  - cloudformation:GetResource
                Resource: "*"
EOF

aws cloudformation create-stack-set \
  --stack-set-name port-ocean-read-role \
  --template-body file://port-read-role-template.yaml \
  --parameters ParameterKey=IntegrationPrincipalArn,ParameterValue=arn:aws:iam::${INTEGRATION_ACCOUNT_ID}:user/port-ocean-aws \
  --permission-model SERVICE_MANAGED \
  --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false \
  --capabilities CAPABILITY_NAMED_IAM

aws cloudformation create-stack-instances \
  --stack-set-name port-ocean-read-role \
  --deployment-targets OrganizationalUnitIds=<OU_ID_RAIZ_O_LISTA> \
  --regions us-east-1
```

## Paso 3 — Crear el Secret en Kubernetes

Las credenciales NUNCA van al repo git. Convención del chart `port-ocean`: cada config sensible se inyecta como `OCEAN__INTEGRATION__CONFIG__<NOMBRE_EN_SNAKE_UPPER>`:

| Clave del spec (camelCase) | Variable de entorno |
|---|---|
| `awsAccessKeyId` | `OCEAN__INTEGRATION__CONFIG__AWS_ACCESS_KEY_ID` |
| `awsSecretAccessKey` | `OCEAN__INTEGRATION__CONFIG__AWS_SECRET_ACCESS_KEY` |
| `organizationRoleArn` | `OCEAN__INTEGRATION__CONFIG__ORGANIZATION_ROLE_ARN` |
| `accountReadRoleName` | `OCEAN__INTEGRATION__CONFIG__ACCOUNT_READ_ROLE_NAME` |
| `liveEventsApiKey` (opcional, solo live events) | `OCEAN__INTEGRATION__CONFIG__LIVE_EVENTS_API_KEY` |

```bash
kubectl create namespace port-idp --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic ocean-aws-credentials \
  --namespace port-idp \
  --from-literal=OCEAN__PORT__CLIENT_ID='<PORT_CLIENT_ID>' \
  --from-literal=OCEAN__PORT__CLIENT_SECRET='<PORT_CLIENT_SECRET>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__AWS_ACCESS_KEY_ID='<AWS_ACCESS_KEY_ID>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__AWS_SECRET_ACCESS_KEY='<AWS_SECRET_ACCESS_KEY>' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__ORGANIZATION_ROLE_ARN='arn:aws:iam::999999999999:role/PortOceanOrgRole' \
  --from-literal=OCEAN__INTEGRATION__CONFIG__ACCOUNT_READ_ROLE_NAME='AwsPortOceanIntegrationReadOnlyRole'
```

Verifica:

```bash
kubectl get secret ocean-aws-credentials -n port-idp -o jsonpath='{.data}' | tr ',' '\n'
```

> Si usas IRSA en EKS, omite las dos claves `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` y define `podServiceAccount.name` en los values.

## Paso 4 — Values del chart

Archivo: `deployment/install/ocean-aws/values.yaml` (rama `laboratory`).

```yaml
# Values de la integración Ocean AWS (oficial) para el entorno laboratory.
# SIN credenciales: el chart referencia el Secret manual "ocean-aws-credentials"
# creado a mano en el namespace port-idp.
port:
  baseUrl: https://api.us.getport.io

# Integración OFICIAL: crea blueprints y mapping por defecto en el primer arranque
initializePortResources: true

# Resync programado (minutos). AWS multi-cuenta puede tardar: no bajar de 60.
scheduledResyncInterval: 1440

# Imagen oficial de ghcr.io/port-labs (default del chart): NO definir
# imageRegistry custom ni imagePullPolicy Never.

# No crear el Secret desde el chart: usar el Secret manual del namespace.
# Debe contener: OCEAN__PORT__CLIENT_ID, OCEAN__PORT__CLIENT_SECRET,
# OCEAN__INTEGRATION__CONFIG__AWS_ACCESS_KEY_ID,
# OCEAN__INTEGRATION__CONFIG__AWS_SECRET_ACCESS_KEY,
# OCEAN__INTEGRATION__CONFIG__ORGANIZATION_ROLE_ARN,
# OCEAN__INTEGRATION__CONFIG__ACCOUNT_READ_ROLE_NAME
secret:
  create: false
  name: ocean-aws-credentials

resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "1Gi"
    cpu: "1000m"

integration:
  identifier: aws
  type: aws
  eventListener:
    type: POLLING
  # Todas las claves sensibles (spec oficial las marca sensitive) van en el
  # Secret manual; aquí no se declara integration.config con secretos.
  # Config NO sensible opcional:
  # config:
  #   maximumConcurrentAccounts: 10   # [DEPRECATED según spec oficial]
```

## Paso 5 — ApplicationSet

Archivo: `deployment/applicationsets/30-ocean-aws.yaml`.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: ocean-aws
  namespace: argocd
spec:
  goTemplate: true
  goTemplateOptions: ["missingkey=error"]
  generators:
    - clusters:
        selector:
          matchLabels:
            project: port
            environment: laboratory
          matchExpressions:
            - key: cloud
              operator: Exists
  template:
    metadata:
      name: 'port-ocean-aws-{{.name}}'
      annotations:
        argocd.argoproj.io/sync-wave: "0"
      finalizers:
        - resources-finalizer.argocd.argoproj.io
    spec:
      project: default
      sources:
        - repoURL: https://port-labs.github.io/helm-charts
          chart: port-ocean
          targetRevision: 0.23.4
          helm:
            releaseName: aws
            valueFiles:
              - $values/deployment/install/ocean-aws/values.yaml
        - repoURL: https://github.com/marcos-developer-j/port-ocean-integrations.git
          targetRevision: laboratory
          ref: values
      destination:
        server: '{{.server}}'
        namespace: port-idp
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
          - ApplyOutOfSyncOnly=true
```

## Paso 6 — Verificación

```bash
# Estado del pod
kubectl get pods -n port-idp -l app.kubernetes.io/instance=aws

# Logs en vivo
kubectl logs -n port-idp -l app.kubernetes.io/instance=aws -f --tail=200
```

Qué buscar en los logs:

- `Fetching AWS accounts` / descubrimiento de cuentas de Organizations: debe listar TODAS las cuentas miembro esperadas.
- Mensajes de AssumeRole exitoso por cuenta; si una cuenta falla verás `AccessDenied` con el ARN del rol que no pudo asumir.
- Resync por kind: `AWS::S3::Bucket`, `AWS::EC2::Instance`, `AWS::ECS::Cluster` con contadores de entidades upserted.
- `Resync finished successfully` al terminar.

En Port:

1. **Builder** → deben existir los blueprints `awsAccount` y `cloudResource`.
2. **Catalog** → entidades de cuentas y recursos con la propiedad de cuenta/región correcta (verifica que aparezcan recursos de MÁS de una cuenta: es la prueba del multi-account).
3. **Data sources** (ajustes) → la integración `aws` en verde, con timestamp del último resync.

## Instalación alternativa

### Terraform (módulo oficial `port-labs/integration-factory/ocean`, despliegue en ECS)

La vía Terraform oficial despliega la integración como servicio ECS (permite live events). Según el spec oficial: módulo `port-labs/integration-factory/ocean`, ejemplo `aws_container_app`, versión `>= 0.0.24`. Requiere Terraform >= 1.9.1 y AWS CLI 2 autenticada.

```hcl
module "ocean_aws" {
  source  = "port-labs/integration-factory/ocean//examples/aws_container_app"
  version = ">=0.0.24"

  port = {
    client_id     = var.port_client_id
    client_secret = var.port_client_secret
    base_url      = "https://api.us.getport.io"
  }

  integration = {
    type       = "aws"
    identifier = "aws"
    config = {
      # organization_role_arn / account_read_role_name según el ejemplo del módulo
      # (verificar nombres exactos de variables en el README del módulo)
    }
  }

  # Variables extra del ejemplo aws_container_app (según spec oficial):
  allow_incoming_requests = true
  create_default_sg       = false
  subnets                 = ["subnet-1", "subnet-2", "subnet-3"]
  vpc_id                  = "vpc-1"
  cluster_name            = "port-ocean-aws-exporter"
}
```

### AWS Hosted by Port (`aws-v3`)

Si prefieres no operar la integración: en Port UI → Data sources → AWS (new) → instalación guiada "Hosted by Port". Usa un rol `PortOceanReadRole` con `ReadOnlyAccess` y trust OIDC hacia Port; el multi-account se configura con descubrimiento vía AWS Organizations y OUs opcionales (`ouId`), `accountRoleArn` (con Organizations) o `accountRoleArns` (lista explícita de ARNs sin Organizations) y `externalId`. No requiere nada en tu cluster, pero queda fuera del GitOps de este repo.

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `AccessDenied` al llamar `sts:AssumeRole` sobre el rol de organización | Trust policy del rol root no incluye el principal correcto, o la política del usuario de integración no permite ese ARN | Revisa `aws iam get-role --role-name PortOceanOrgRole` (trust) y la policy `AssumeCrossAccountRoles` |
| Solo se sincroniza la cuenta de integración | `organizationRoleArn` no definido, o la integración hizo fallback a single-account | Verifica la env `OCEAN__INTEGRATION__CONFIG__ORGANIZATION_ROLE_ARN` dentro del pod: `kubectl exec -n port-idp deploy/aws-port-ocean-aws -- env \| grep OCEAN__INTEGRATION` (nombre del deploy puede variar; usa `kubectl get deploy -n port-idp`) |
| Una cuenta miembro concreta no aparece | El rol `AwsPortOceanIntegrationReadOnlyRole` no existe en esa cuenta o su trust no confía en el principal de integración | Despliega el rol (StackSet) y verifica el nombre EXACTO (es case-sensitive y debe ser idéntico en todas) |
| `UnrecognizedClientException` / `InvalidClientTokenId` | Access Keys mal copiadas o desactivadas | Regenera keys y recrea el Secret; reinicia el pod (`kubectl rollout restart deploy -n port-idp -l app.kubernetes.io/instance=aws`) |
| `ThrottlingException` / `Rate exceeded` en Cloud Control | Muchas cuentas/regiones en paralelo | Sube `scheduledResyncInterval`, reduce kinds en el mapping o limita regiones con `regionPolicy` en el mapping (verificar sintaxis exacta en la doc oficial) |
| Recursos de una región vacíos | Región no habilitada en ESA cuenta | `aws account list-regions` en la cuenta afectada; las regiones se evalúan por cuenta |
| Pod en CrashLoopBackOff nada más arrancar | Faltan claves del Secret (`OCEAN__PORT__CLIENT_ID`, etc.) o `secret.name` no coincide | `kubectl describe pod` + revisa que el Secret se llama exactamente `ocean-aws-credentials` |
| 401/403 contra api.us.getport.io | Credenciales de Port de otra región u organización | Confirma `port.baseUrl: https://api.us.getport.io` y las credenciales de la organización correcta |

## Referencias

- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/aws/ (overview AWS on-premise)
- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/aws/installations/installation/ (instalación Helm self-hosted)
- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/aws/installations/multi_account/ (multi-cuenta: organizationRoleArn / accountReadRoleName)
- https://docs.port.io/build-your-software-catalog/sync-data-to-catalog/cloud-providers/aws-v3/installation (AWS v3 hosted by Port)
- https://github.com/port-labs/ocean/tree/main/integrations/aws (código + `.port/spec.yaml` con las configuraciones exactas)
- https://github.com/port-labs/ocean/tree/main/integrations/aws-v3 (spec de aws-v3)
- https://github.com/port-labs/helm-charts/blob/main/charts/port-ocean/README.md (convención `OCEAN__*` del chart)
- https://github.com/port-labs/terraform-ocean-integration-factory (módulo Terraform oficial)
