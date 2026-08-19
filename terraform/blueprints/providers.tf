terraform {
  required_version = ">= 1.5.0"

  required_providers {
    port = {
      source  = "port-labs/port-labs"
      version = "~> 2.0"
    }
  }
}

# Credenciales: se recomienda usar variables de entorno en lugar de tfvars:
#   PORT_CLIENT_ID / PORT_CLIENT_SECRET
provider "port" {
  client_id = var.port_client_id
  secret    = var.port_client_secret
  base_url  = var.port_base_url
}
