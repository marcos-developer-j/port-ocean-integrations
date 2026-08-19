# ---------------------------------------------------------------------------
# Blueprints de la integración Ocean Veracode.
# Equivalentes a integrations/veracode/.port/resources/blueprints.json
# ---------------------------------------------------------------------------

resource "port_blueprint" "veracode_application" {
  identifier = "veracodeApplication"
  title      = "Veracode Application"
  icon       = "Lock"

  properties = {
    string_props = {
      "name" = {
        title = "Name"
      }
      "businessCriticality" = {
        title = "Business Criticality"
      }
      "policyCompliance" = {
        title = "Policy Compliance"
      }
      "created" = {
        title  = "Created"
        format = "date-time"
      }
      "modified" = {
        title  = "Modified"
        format = "date-time"
      }
    }
    array_props = {
      "teams" = {
        title        = "Teams"
        string_items = {}
      }
    }
  }

  # Relación opcional hacia el blueprint central de servicios (scorecards)
  relations = var.enable_service_relations ? {
    "service" = {
      title    = "Service"
      target   = var.service_blueprint_identifier
      required = false
      many     = false
    }
  } : {}
}

resource "port_blueprint" "veracode_finding" {
  identifier = "veracodeFinding"
  title      = "Veracode Finding"
  icon       = "Lock"

  properties = {
    string_props = {
      "scanType" = {
        title = "Scan Type"
      }
      "cweName" = {
        title = "CWE Name"
      }
      "status" = {
        title = "Status"
      }
      "resolutionStatus" = {
        title = "Resolution Status"
      }
      "firstFound" = {
        title  = "First Found"
        format = "date-time"
      }
      "lastSeen" = {
        title  = "Last Seen"
        format = "date-time"
      }
      "description" = {
        title = "Description"
      }
      "filePath" = {
        title = "File Path"
      }
    }
    number_props = {
      "severity" = {
        title = "Severity"
      }
      "cweId" = {
        title = "CWE ID"
      }
    }
    boolean_props = {
      "violatesPolicy" = {
        title = "Violates Policy"
      }
    }
  }

  relations = {
    "application" = {
      title    = "Application"
      target   = port_blueprint.veracode_application.identifier
      required = false
      many     = false
    }
  }
}
