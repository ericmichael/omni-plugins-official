targetScope = 'subscription'

@description('Optional policy definition id to assign at subscription scope, such as a built-in diagnostic-settings or private-endpoint policy.')
param policyDefinitionId string = ''

@description('Optional Log Analytics workspace id used as a policy assignment parameter when the selected policy supports it.')
param logAnalyticsWorkspaceResourceId string = ''

resource defenderAppServices 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'AppServices'
  properties: { pricingTier: 'Standard' }
}

resource defenderStorage 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'StorageAccounts'
  properties: { pricingTier: 'Standard' }
}

resource defenderKeyVault 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'KeyVaults'
  properties: { pricingTier: 'Standard' }
}

resource defenderContainers 'Microsoft.Security/pricings@2024-01-01' = {
  name: 'Containers'
  properties: { pricingTier: 'Standard' }
}

resource policyAssignment 'Microsoft.Authorization/policyAssignments@2022-06-01' = if (!empty(policyDefinitionId)) {
  name: 'hipaa-baseline-policy'
  location: deployment().location
  properties: {
    displayName: 'HIPAA baseline policy assignment'
    policyDefinitionId: policyDefinitionId
    enforcementMode: 'Default'
    parameters: empty(logAnalyticsWorkspaceResourceId) ? {} : {
      logAnalytics: { value: logAnalyticsWorkspaceResourceId }
    }
  }
}

output defenderPlans array = [
  defenderAppServices.name
  defenderStorage.name
  defenderKeyVault.name
  defenderContainers.name
]
