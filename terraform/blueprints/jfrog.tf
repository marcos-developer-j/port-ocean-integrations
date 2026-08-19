# ---------------------------------------------------------------------------
# Blueprints de la integración Ocean JFrog.
# Equivalentes a integrations/jfrog/.port/resources/blueprints.json
# ---------------------------------------------------------------------------

resource "port_blueprint" "jfrog_project" {
  identifier = "jfrogProject"
  title      = "JFrog Project"
  icon       = "JfrogXray"

  properties = {
    string_props = {
      "description" = {
        title = "Description"
      }
    }
  }
}

resource "port_blueprint" "jfrog_repository" {
  identifier = "jfrogRepository"
  title      = "JFrog Repository"
  icon       = "JfrogXray"

  properties = {
    string_props = {
      "type" = {
        title = "Repository Type"
      }
      "packageType" = {
        title = "Package Type"
      }
      "url" = {
        title  = "Repository URL"
        format = "url"
      }
      "description" = {
        title = "Description"
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

resource "port_blueprint" "jfrog_build" {
  identifier = "jfrogBuild"
  title      = "JFrog Build"
  icon       = "JfrogXray"

  properties = {
    string_props = {
      "lastStarted" = {
        title  = "Last Started"
        format = "date-time"
      }
    }
  }
}

resource "port_blueprint" "jfrog_artifact" {
  identifier = "jfrogArtifact"
  title      = "JFrog Artifact"
  icon       = "JfrogXray"

  properties = {
    string_props = {
      "path" = {
        title = "Path"
      }
      "sha256" = {
        title = "SHA256"
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
    number_props = {
      "size" = {
        title = "Size"
      }
    }
  }

  relations = {
    "repository" = {
      title    = "Repository"
      target   = port_blueprint.jfrog_repository.identifier
      required = false
      many     = false
    }
  }
}

resource "port_blueprint" "jfrog_xray_violation" {
  identifier = "jfrogXrayViolation"
  title      = "JFrog Xray Violation"
  icon       = "JfrogXray"

  properties = {
    string_props = {
      "severity" = {
        title = "Severity"
      }
      "type" = {
        title = "Type"
      }
      "watchName" = {
        title = "Watch Name"
      }
      "description" = {
        title = "Description"
      }
      "created" = {
        title  = "Created"
        format = "date-time"
      }
      "detailsUrl" = {
        title  = "Details URL"
        format = "url"
      }
    }
    array_props = {
      "infectedComponents" = {
        title        = "Infected Components"
        string_items = {}
      }
    }
  }
}
