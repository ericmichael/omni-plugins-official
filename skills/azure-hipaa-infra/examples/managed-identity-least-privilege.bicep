targetScope = 'resourceGroup'

param location string = resourceGroup().location
param namePrefix string
param acrResourceId string
param targetResourceGroupId string = resourceGroup().id

var suffix = uniqueString(resourceGroup().id)
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-app-mi'
  location: location
}

resource appOperatorRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(targetResourceGroupId, '${namePrefix}-app-operator')
  properties: {
    roleName: '${namePrefix}-app-operator-${suffix}'
    description: 'Least-privilege runtime role for application-managed Azure resources.'
    assignableScopes: [targetResourceGroupId]
    permissions: [
      {
        actions: [
          'Microsoft.Resources/subscriptions/resourceGroups/read'
          'Microsoft.Insights/metricDefinitions/read'
          'Microsoft.Insights/metrics/read'
        ]
        dataActions: []
      }
    ]
  }
}

resource appOperatorAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(targetResourceGroupId, identity.id, appOperatorRole.id)
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: appOperatorRole.id
  }
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: last(split(acrResourceId, '/'))
}

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acrResourceId, identity.id, acrPullRoleId)
  scope: acr
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

output managedIdentityId string = identity.id
output managedIdentityClientId string = identity.properties.clientId
