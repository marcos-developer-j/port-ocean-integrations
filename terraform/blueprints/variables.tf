variable "port_client_id" {
  description = "Port Client ID (o usar env var PORT_CLIENT_ID)"
  type        = string
  default     = null
}

variable "port_client_secret" {
  description = "Port Client Secret (o usar env var PORT_CLIENT_SECRET)"
  type        = string
  default     = null
  sensitive   = true
}

variable "port_base_url" {
  description = "URL base del API de Port (EU: https://api.getport.io, US: https://api.us.getport.io)"
  type        = string
  default     = "https://api.getport.io"
}

variable "service_blueprint_identifier" {
  description = "Identifier del blueprint central de servicios, usado para las relaciones opcionales hacia `service`"
  type        = string
  default     = "test_service"
}

variable "enable_service_relations" {
  description = "Si es true, agrega relaciones opcionales hacia el blueprint de servicios (debe existir previamente en Port)"
  type        = bool
  default     = false
}
