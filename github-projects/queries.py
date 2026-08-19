PROJECTS_QUERY = """
query ($org: String!, $cursor: String) {
  organization(login: $org) {
    projectsV2(first: 50, after: $cursor) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        id
        number
        title
        shortDescription
        url
        closed
        public
        createdAt
        updatedAt
        creator {
          login
        }
      }
    }
  }
}
"""

PROJECT_ITEMS_QUERY = """
query ($projectId: ID!, $cursor: String) {
  node(id: $projectId) {
    ... on ProjectV2 {
      items(first: 100, after: $cursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          id
          type
          isArchived
          createdAt
          updatedAt
          fieldValues(first: 20) {
            nodes {
              ... on ProjectV2ItemFieldSingleSelectValue {
                name
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
              ... on ProjectV2ItemFieldTextValue {
                text
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
              ... on ProjectV2ItemFieldNumberValue {
                number
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
              ... on ProjectV2ItemFieldDateValue {
                date
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
              ... on ProjectV2ItemFieldIterationValue {
                title
                field {
                  ... on ProjectV2FieldCommon {
                    name
                  }
                }
              }
            }
          }
          content {
            ... on Issue {
              id
              number
              title
              url
              state
              repository {
                nameWithOwner
              }
            }
            ... on PullRequest {
              id
              number
              title
              url
              state
              repository {
                nameWithOwner
              }
            }
            ... on DraftIssue {
              id
              title
            }
          }
        }
      }
    }
  }
}
"""
