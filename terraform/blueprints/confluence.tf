# ---------------------------------------------------------------------------
# Blueprints de la integración Ocean Confluence (custom desarrollada).
# Equivalentes a integrations/confluence/.port/resources/blueprints.json
# ---------------------------------------------------------------------------

resource "port_blueprint" "confluence_space" {
  identifier = "confluenceSpace"
  title      = "Confluence Space"
  icon       = "Confluence"

  properties = {
    string_props = {
      "key" = {
        title       = "Key"
        description = "Clave única del espacio"
        required    = true
      }
      "type" = {
        title       = "Type"
        description = "Tipo de espacio (global o personal)"
        enum        = ["global", "personal"]
      }
      "status" = {
        title       = "Status"
        description = "Estado del espacio"
        enum        = ["current", "archived"]
      }
      "description" = {
        title       = "Description"
        description = "Descripción del espacio"
      }
      "homepageId" = {
        title       = "Homepage ID"
        description = "ID de la página principal"
      }
      "url" = {
        title       = "URL"
        format      = "url"
        description = "URL del espacio en Confluence"
      }
    }
  }
}

resource "port_blueprint" "confluence_page" {
  identifier = "confluencePage"
  title      = "Confluence Page"
  icon       = "Confluence"

  properties = {
    string_props = {
      "status" = {
        title       = "Status"
        description = "Estado de la página"
        enum        = ["current", "trashed", "deleted", "historical", "draft"]
      }
      "parentId" = {
        title       = "Parent ID"
        description = "ID de la página padre"
      }
      "parentType" = {
        title       = "Parent Type"
        description = "Tipo del padre (page o space)"
      }
      "authorId" = {
        title       = "Author ID"
        description = "ID del autor original"
      }
      "ownerId" = {
        title       = "Owner ID"
        description = "ID del propietario actual"
      }
      "createdAt" = {
        title       = "Created At"
        format      = "date-time"
        description = "Fecha de creación"
      }
      "url" = {
        title       = "URL"
        format      = "url"
        description = "URL de la página en Confluence"
      }
      "markdown" = {
        title       = "Markdown Content"
        description = "Contenido de la página convertido a Markdown (README)"
      }
    }
    number_props = {
      "position" = {
        title       = "Position"
        description = "Posición en el árbol de páginas"
      }
      "version" = {
        title       = "Version"
        description = "Número de versión actual"
      }
    }
  }

  relations = {
    "space" = {
      title    = "Space"
      target   = port_blueprint.confluence_space.identifier
      required = false
      many     = false
    }
  }
}
