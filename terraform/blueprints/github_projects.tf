# ---------------------------------------------------------------------------
# Blueprints de la integración Ocean GitHub Projects (Projects V2).
# Equivalentes a integrations/github-projects/.port/resources/blueprints.json
# ---------------------------------------------------------------------------

resource "port_blueprint" "github_project" {
  identifier = "githubProject"
  title      = "GitHub Project"
  icon       = "Github"

  properties = {
    string_props = {
      "url" = {
        title  = "URL"
        format = "url"
      }
      "creator" = {
        title = "Creator"
      }
      "shortDescription" = {
        title = "Short Description"
      }
      "createdAt" = {
        title  = "Created At"
        format = "date-time"
      }
      "updatedAt" = {
        title  = "Updated At"
        format = "date-time"
      }
    }
    number_props = {
      "number" = {
        title = "Number"
      }
    }
    boolean_props = {
      "closed" = {
        title = "Closed"
      }
      "public" = {
        title = "Public"
      }
    }
  }
}

resource "port_blueprint" "github_project_item" {
  identifier = "githubProjectItem"
  title      = "GitHub Project Item"
  icon       = "Github"

  properties = {
    string_props = {
      "type" = {
        title = "Type"
      }
      "status" = {
        title = "Status"
      }
      "url" = {
        title  = "URL"
        format = "url"
      }
      "state" = {
        title = "State"
      }
      "repository" = {
        title = "Repository"
      }
      "createdAt" = {
        title  = "Created At"
        format = "date-time"
      }
      "updatedAt" = {
        title  = "Updated At"
        format = "date-time"
      }
    }
    boolean_props = {
      "archived" = {
        title = "Archived"
      }
    }
  }

  relations = {
    "project" = {
      title    = "Project"
      target   = port_blueprint.github_project.identifier
      required = false
      many     = false
    }
  }
}
