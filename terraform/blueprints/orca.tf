# ---------------------------------------------------------------------------
# Blueprints de la integración Ocean Orca Security.
# Equivalentes a integrations/orca/.port/resources/blueprints.json
# ---------------------------------------------------------------------------

resource "port_blueprint" "orca_asset" {
  identifier = "orcaAsset"
  title      = "Orca Asset"
  icon       = "Cloud"

  properties = {
    string_props = {
      "name" = {
        title = "Name"
      }
      "type" = {
        title = "Type"
      }
      "category" = {
        title = "Category"
      }
      "cloudProvider" = {
        title = "Cloud Provider"
      }
      "accountName" = {
        title = "Account Name"
      }
    }
  }
}

resource "port_blueprint" "orca_alert" {
  identifier = "orcaAlert"
  title      = "Orca Alert"
  icon       = "Alert"

  properties = {
    string_props = {
      "severity" = {
        title = "Severity"
      }
      "status" = {
        title = "Status"
      }
      "category" = {
        title = "Category"
      }
      "type" = {
        title = "Type"
      }
      "description" = {
        title = "Description"
      }
      "recommendation" = {
        title = "Recommendation"
      }
      "createdAt" = {
        title  = "Created At"
        format = "date-time"
      }
      "lastSeen" = {
        title  = "Last Seen"
        format = "date-time"
      }
    }
    number_props = {
      "score" = {
        title = "Score"
      }
    }
  }

  relations = merge(
    {
      "asset" = {
        title    = "Asset"
        target   = port_blueprint.orca_asset.identifier
        required = false
        many     = false
      }
    },
    # Relación opcional hacia el blueprint central de servicios (scorecards)
    var.enable_service_relations ? {
      "service" = {
        title    = "Service"
        target   = var.service_blueprint_identifier
        required = false
        many     = false
      }
    } : {}
  )
}
